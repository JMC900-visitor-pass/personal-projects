#include "EmulatorBridge.h"
#include <mgba/flags.h>
#include <mgba/core/core.h>
#include <mgba/core/cheats.h>
#include <mgba/core/blip_buf.h>
#include <mgba/core/serialize.h>
#include <mgba/internal/defines.h>
#include <mgba/internal/gb/gb.h>
#include <mgba/internal/gba/gba.h>
#include <mgba-util/vfs.h>
#include <errno.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

#define AUDIO_CAPACITY 8192
#define VIDEO_CAPACITY (256 * 224)
struct StudioCore {
    struct mCore *engine;
    uint32_t pixels[VIDEO_CAPACITY];
    unsigned width, height;
    char title[64];
    pthread_mutex_t audioMutex;
    float audio[AUDIO_CAPACITY * 2];
    size_t readIndex, writeIndex, audioCount;
    struct mCheatDevice *cheatDevice;
    struct mCheatSet *cheatSet;
    bool cheatEnabled;
};
static _Thread_local char lastError[512];

const char *studio_last_error(void) { return lastError; }
const char *studio_runtime_error(StudioCore *core) { (void)core; return ""; }
const char *studio_core_name(StudioCore *core) { (void)core; return "mGBA 0.10.5"; }
static void fail(const char *action, const char *detail) {
    snprintf(lastError, sizeof(lastError), "%s%s%s", action,
             detail && *detail ? ": " : "", detail ? detail : "");
}
static bool make_directory(const char *path) {
    if (!path || !*path || strlen(path) >= PATH_MAX) return false;
    char buffer[PATH_MAX];
    snprintf(buffer, sizeof(buffer), "%s", path);
    for (char *p = buffer + 1; *p; ++p) {
        if (*p != '/') continue;
        *p = 0;
        if (mkdir(buffer, 0700) && errno != EEXIST) return false;
        *p = '/';
    }
    if (mkdir(buffer, 0700) && errno != EEXIST) return false;
    struct stat st;
    return !stat(buffer, &st) && S_ISDIR(st.st_mode);
}
static void configure_audio(StudioCore *s) {
    for (int i = 0; i < 2; ++i)
        blip_set_rates(s->engine->getAudioChannel(s->engine, i),
                       s->engine->frequency(s->engine), 48000);
}
StudioCore *studio_create(const char *rom_path, const char *save_directory) {
    lastError[0] = 0;
    if (!rom_path || !*rom_path) { fail("No ROM was selected", NULL); return NULL; }
    if (!make_directory(save_directory)) {
        fail("Cannot create the game's save directory", strerror(errno)); return NULL;
    }
    struct mCore *engine = mCoreFind(rom_path);
    if (!engine) { fail("Cannot read this ROM; choose a valid GBA, GB, or GBC file", rom_path); return NULL; }
    StudioCore *s = calloc(1, sizeof(*s));
    if (!s) { free(engine); fail("Not enough memory to start emulation", NULL); return NULL; }
    pthread_mutex_init(&s->audioMutex, NULL);
    s->engine = engine;
    if (!engine->init(engine)) {
        free(engine); pthread_mutex_destroy(&s->audioMutex); free(s);
        fail("mGBA could not initialize the emulator", NULL); return NULL;
    }
    mCoreInitConfig(engine, "mgba-studio");
    mCoreConfigSetDefaultIntValue(&engine->config, "useBios", 0);
    mCoreConfigSetDefaultIntValue(&engine->config, "skipBios", 1);
    mCoreConfigSetDefaultIntValue(&engine->config, "volume", 256);
    mCoreConfigSetDefaultIntValue(&engine->config, "audioBuffers", 4096);
    mCoreConfigSetDefaultIntValue(&engine->config, "sampleRate", 48000);
    mCoreConfigSetDefaultIntValue(&engine->config, "sgb.borders", 0);
    // Deliberately avoid loading the original mGBA application's configuration.
    mCoreLoadForeignConfig(engine, &engine->config);
    if (!mCoreLoadFile(engine, rom_path)) {
        fail("mGBA could not load the ROM", rom_path); studio_destroy(s); return NULL;
    }
    char savePath[PATH_MAX];
    if (snprintf(savePath, sizeof(savePath), "%s/battery.sav", save_directory) >= (int)sizeof(savePath)) {
        fail("The game's save path is too long", NULL); studio_destroy(s); return NULL;
    }
    if (!mCoreLoadSaveFile(engine, savePath, false)) {
        fail("Cannot open the game's battery save", strerror(errno)); studio_destroy(s); return NULL;
    }
    engine->desiredVideoDimensions(engine, &s->width, &s->height);
    if (!s->width || !s->height || s->width * s->height > VIDEO_CAPACITY) {
        fail("Unsupported emulated display size", NULL); studio_destroy(s); return NULL;
    }
    engine->setVideoBuffer(engine, s->pixels, s->width);
    engine->reset(engine);
    configure_audio(s);
    engine->getGameTitle(engine, s->title);
    s->title[sizeof(s->title) - 1] = 0;
    for (size_t i = 0; i < VIDEO_CAPACITY; ++i) s->pixels[i] |= 0xFF000000;
    return s;
}

void studio_flush_save(StudioCore *s) {
    if (!s || !s->engine) return;
    // Force mGBA's normal save synchronizer, including RTC trailers and masked
    // save-state writeback, even when closing before its 15-frame debounce.
    uint32_t frame = s->engine->frameCounter(s->engine);
    if (s->engine->platform(s->engine) == mPLATFORM_GB) {
        struct GB *gb = s->engine->board;
        if (!gb->sramVf) return;
        gb->sramDirty = mSAVEDATA_DIRT_SEEN;
        gb->sramDirtAge = frame - mSAVEDATA_CLEANUP_THRESHOLD - 1;
        GBSramClean(gb, frame);
    } else {
        struct GBA *gba = s->engine->board;
        gba->memory.savedata.dirty = mSAVEDATA_DIRT_SEEN;
        gba->memory.savedata.dirtAge = frame - mSAVEDATA_CLEANUP_THRESHOLD - 1;
        GBASavedataClean(&gba->memory.savedata, frame);
    }
}
void studio_destroy(StudioCore *s) {
    if (!s) return;
    if (s->engine) {
        studio_flush_save(s);
        mCoreConfigDeinit(&s->engine->config);
        s->engine->deinit(s->engine);
    }
    pthread_mutex_destroy(&s->audioMutex);
    free(s);
}
void studio_run_frame(StudioCore *s) {
    if (!s) return;
    s->engine->runFrame(s->engine);
    // Apply cheats each frame so assign/if-condition code stays in effect and
    // survives resets. Refreshing an empty or disabled set is a no-op.
    if (s->cheatSet && s->cheatEnabled && s->cheatDevice) mCheatRefresh(s->cheatDevice, s->cheatSet);
    for (size_t i = 0; i < s->width * s->height; ++i) s->pixels[i] |= 0xFF000000;
    short samples[4096 * 2];
    blip_t *left = s->engine->getAudioChannel(s->engine, 0);
    blip_t *right = s->engine->getAudioChannel(s->engine, 1);
    int count = blip_samples_avail(left);
    if (count > blip_samples_avail(right)) count = blip_samples_avail(right);
    if (count > 4096) count = 4096;
    blip_read_samples(left, samples, count, 1);
    blip_read_samples(right, samples + 1, count, 1);
    pthread_mutex_lock(&s->audioMutex);
    for (int i = 0; i < count; ++i) {
        if (s->audioCount == AUDIO_CAPACITY) {
            s->readIndex = (s->readIndex + 1) % AUDIO_CAPACITY;
            --s->audioCount;
        }
        s->audio[s->writeIndex * 2] = samples[i * 2] / 32768.0f;
        s->audio[s->writeIndex * 2 + 1] = samples[i * 2 + 1] / 32768.0f;
        s->writeIndex = (s->writeIndex + 1) % AUDIO_CAPACITY;
        ++s->audioCount;
    }
    pthread_mutex_unlock(&s->audioMutex);
}
void studio_reset(StudioCore *s) {
    if (!s) return;
    studio_flush_save(s);
    s->engine->reset(s->engine);
    s->engine->setKeys(s->engine, 0);
    configure_audio(s);
    studio_clear_audio(s);
}
void studio_set_keys(StudioCore *s, uint32_t keys) { if (s) s->engine->setKeys(s->engine, keys & 0x3FF); }
const uint32_t *studio_pixels(StudioCore *s) { return s ? s->pixels : NULL; }
unsigned studio_width(StudioCore *s) { return s ? s->width : 0; }
unsigned studio_height(StudioCore *s) { return s ? s->height : 0; }
double studio_fps(StudioCore *s) { return s ? (double)s->engine->frequency(s->engine) / s->engine->frameCycles(s->engine) : 59.7275; }
const char *studio_title(StudioCore *s) { return s ? s->title : ""; }
size_t studio_read_audio(StudioCore *s, float *interleaved, size_t frames) {
    if (!interleaved) return 0;
    memset(interleaved, 0, frames * 2 * sizeof(float));
    if (!s) return 0;
    pthread_mutex_lock(&s->audioMutex);
    size_t count = frames < s->audioCount ? frames : s->audioCount;
    for (size_t i = 0; i < count; ++i) {
        interleaved[i * 2] = s->audio[s->readIndex * 2];
        interleaved[i * 2 + 1] = s->audio[s->readIndex * 2 + 1];
        s->readIndex = (s->readIndex + 1) % AUDIO_CAPACITY;
    }
    s->audioCount -= count;
    pthread_mutex_unlock(&s->audioMutex);
    return count;
}
void studio_clear_audio(StudioCore *s) {
    if (!s) return;
    pthread_mutex_lock(&s->audioMutex);
    s->readIndex = s->writeIndex = s->audioCount = 0;
    pthread_mutex_unlock(&s->audioMutex);
}
bool studio_save_state(StudioCore *s, const char *path) {
    if (!s || !path) { fail("No running game to save", NULL); return false; }
    char temporary[PATH_MAX];
    if (snprintf(temporary, sizeof(temporary), "%s.tmp", path) >= (int)sizeof(temporary)) {
        fail("Save-state path is too long", NULL); return false;
    }
    struct VFile *vf = VFileOpen(temporary, O_CREAT | O_TRUNC | O_RDWR);
    if (!vf) { fail("Cannot create save state", strerror(errno)); return false; }
    bool ok = mCoreSaveStateNamed(s->engine, vf, SAVESTATE_SAVEDATA | SAVESTATE_RTC | SAVESTATE_METADATA);
    if (ok && vf->sync) ok = vf->sync(vf, NULL, 0);
    ok = vf->close(vf) && ok;
    if (ok) ok = rename(temporary, path) == 0;
    if (!ok) { unlink(temporary); fail("Could not write save state", strerror(errno)); }
    return ok;
}
bool studio_load_state(StudioCore *s, const char *path) {
    if (!s || !path) { fail("No running game to load", NULL); return false; }
    struct VFile *vf = VFileOpen(path, O_RDONLY);
    if (!vf) { fail("Cannot open save state", strerror(errno)); return false; }
    bool ok = mCoreLoadStateNamed(s->engine, vf, SAVESTATE_SAVEDATA | SAVESTATE_RTC);
    vf->close(vf);
    if (!ok) fail("Save state is invalid or belongs to another ROM", NULL);
    else { configure_audio(s); studio_clear_audio(s); }
    return ok;
}

bool studio_restore_battery(StudioCore *s, const char *path) {
    if (!s || !path) return false;
    struct VFile *vf = VFileOpen(path, O_RDONLY);
    if (!vf) { fail("No battery checkpoint available", strerror(errno)); return false; }
    ssize_t size = vf->size(vf);
    if (size <= 0 || size > 1024 * 1024) { vf->close(vf); fail("Invalid battery checkpoint", NULL); return false; }
    void *bytes = malloc(size);
    bool ok = bytes && vf->read(vf, bytes, size) == size;
    vf->close(vf);
    if (ok) ok = s->engine->savedataRestore(s->engine, bytes, size, true);
    free(bytes);
    if (!ok) { fail("Could not restore battery checkpoint", NULL); return false; }
    s->engine->reset(s->engine); configure_audio(s); studio_clear_audio(s);
    return true;
}
