#ifndef EMULATOR_BRIDGE_H
#define EMULATOR_BRIDGE_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef struct StudioCore StudioCore;
#ifdef __cplusplus
extern "C" {
#endif
/* Main-thread lifecycle/frame calls; audio reads may run on the audio thread. */
StudioCore *studio_create(const char *rom_path, const char *save_directory);
const char *studio_last_error(void);
const char *studio_runtime_error(StudioCore *core);
const char *studio_core_name(StudioCore *core);
void studio_destroy(StudioCore *core);
void studio_run_frame(StudioCore *core);
void studio_reset(StudioCore *core);
void studio_set_keys(StudioCore *core, uint32_t keys);
/* mGBA key bits: A=0 B=1 Select=2 Start=3 Right=4 Left=5 Up=6 Down=7 R=8 L=9. */
const uint32_t *studio_pixels(StudioCore *core);
unsigned studio_width(StudioCore *core);
unsigned studio_height(StudioCore *core);
double studio_fps(StudioCore *core);
/* Pixels are little-endian RGBA8. Audio is interleaved stereo float at 48000 Hz. */
size_t studio_read_audio(StudioCore *core, float *interleaved, size_t frames);
void studio_clear_audio(StudioCore *core);
bool studio_save_state(StudioCore *core, const char *path);
bool studio_load_state(StudioCore *core, const char *path);
void studio_flush_save(StudioCore *core);
bool studio_restore_battery(StudioCore *core, const char *path);
const char *studio_title(StudioCore *core);
/* Cheats — mGBA's per-ROM cheat device. A code is added to a single "Crispy GB"
 * set and applied every frame. `type` selects the code dialect
 * (0 auto-detect, 1 Code Breaker, 2 GameShark, 3 ProActionReplay, 4 VBA). */
bool studio_cheat_ensure_set(StudioCore *core, const char *name);
bool studio_cheat_add(StudioCore *core, const char *code, int type);
unsigned studio_cheat_count(StudioCore *core);
void studio_cheat_clear(StudioCore *core);
bool studio_cheat_set_enabled(StudioCore *core, bool enabled);
#ifdef __cplusplus
}
#endif
#endif
