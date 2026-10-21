#include "EmulatorBridge.h"
#include "crispy/core.hpp"
#include <filesystem>
#include <fstream>
#include <iterator>
#include <memory>
#include <string>
#include <cstring>
#include <stdexcept>
#include <cstdio>
#include <fcntl.h>
#include <unistd.h>

struct StudioCore {
    std::unique_ptr<crispy::Core> engine;
    std::filesystem::path saves;
    std::string title, fault;
};
namespace {
thread_local std::string error;
void fail(const std::exception& exception) {error=exception.what();}
std::vector<uint8_t> readFile(const std::filesystem::path& path,size_t limit=34*1024*1024) {
    auto size=std::filesystem::file_size(path);if (size>limit) throw std::runtime_error("File is too large");
    std::ifstream input(path,std::ios::binary);if (!input) throw std::runtime_error("Cannot open "+path.string());
    std::vector<uint8_t> result(size);if (size && !input.read(reinterpret_cast<char*>(result.data()),size)) throw std::runtime_error("Could not read "+path.string());return result;
}
void atomicWrite(const std::filesystem::path& path,std::span<const uint8_t> data) {
    auto temporary=path;temporary+=".tmp";
    int fd=open(temporary.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0600);if (fd<0) throw std::runtime_error("Cannot create "+temporary.string());
    size_t position=0;bool good=true;
    while (position<data.size()) {auto n=write(fd,data.data()+position,data.size()-position);if (n<=0) {good=false;break;}position+=size_t(n);}
    if (good && fsync(fd)!=0) good=false;if (close(fd)!=0) good=false;
    if (good && rename(temporary.c_str(),path.c_str())==0) return;
    unlink(temporary.c_str());throw std::runtime_error("Could not commit "+path.string());
}
template<class F> bool safe(F action) {try {error.clear();action();return true;}catch (const std::exception& e) {fail(e);return false;}}
}
extern "C" {
const char* studio_last_error(void) {return error.c_str();}
const char* studio_runtime_error(StudioCore* core) {return core?core->fault.c_str():"";}
const char* studio_core_name(StudioCore*) {return "Crispy Core 0.1 · experimental";}
StudioCore* studio_create(const char* rom,const char* directory) {
    error.clear();
    try {
        if (!rom || !directory) throw std::runtime_error("ROM and save paths are required");
        auto core=std::make_unique<StudioCore>();core->saves=directory;std::filesystem::create_directories(core->saves);
        core->engine=crispy::makeCore(crispy::systemForPath(rom));core->engine->load(readFile(rom));core->title=core->engine->title();
        auto battery=core->saves/"battery.sav";
        if (std::filesystem::exists(battery)) core->engine->restoreBattery(readFile(battery,1024*1024));
        return core.release();
    } catch (const std::exception& e) {fail(e);return nullptr;}
}
void studio_flush_save(StudioCore* core) {if (core) safe([&]{auto bytes=core->engine->battery();if (!bytes.empty()) atomicWrite(core->saves/"battery.sav",bytes);});}
void studio_destroy(StudioCore* core) {if (core) studio_flush_save(core);delete core;}
void studio_run_frame(StudioCore* core) {if (core && core->fault.empty()) {try {core->engine->runFrame();}catch (const std::exception& e) {fail(e);core->fault=e.what();}}}
void studio_reset(StudioCore* core) {if (core) {core->engine->reset();core->fault.clear();}}
void studio_set_keys(StudioCore* core,uint32_t keys) {if (core) core->engine->setKeys(uint16_t(keys));}
const uint32_t* studio_pixels(StudioCore* core) {return core?core->engine->pixels().data():nullptr;}
unsigned studio_width(StudioCore* core) {return core?core->engine->capabilities().width:0;}
unsigned studio_height(StudioCore* core) {return core?core->engine->capabilities().height:0;}
double studio_fps(StudioCore* core) {if (!core) return 60;auto c=core->engine->capabilities();return double(c.clockHz)/c.frameCycles;}
size_t studio_read_audio(StudioCore*,float* samples,size_t frames) {if (samples) std::memset(samples,0,frames*2*sizeof(float));return 0;}
void studio_clear_audio(StudioCore*) {}
bool studio_save_state(StudioCore* core,const char* path) {return safe([&]{if (!core || !path) throw std::runtime_error("No running game to save");if (!core->fault.empty()) throw std::runtime_error("A core stopped on unsupported hardware cannot overwrite a valid save state");atomicWrite(path,core->engine->save());});}
bool studio_load_state(StudioCore* core,const char* path) {return safe([&]{if (!core || !path) throw std::runtime_error("No running game to load");auto data=readFile(path,2*1024*1024);core->engine->restore(data);core->fault.clear();});}
bool studio_restore_battery(StudioCore* core,const char* path) {return safe([&]{if (!core || !path) throw std::runtime_error("No battery checkpoint");auto data=readFile(path,1024*1024);core->engine->restoreBattery(data);core->engine->reset();core->fault.clear();});}
const char* studio_title(StudioCore* core) {return core?core->title.c_str():"";}
bool studio_cheat_ensure_set(StudioCore*,const char*) {error="Cheats are staged after GB/GBC/GBA core bring-up";return false;}
bool studio_cheat_add(StudioCore*,const char*,int) {error="Cheats are not implemented in this independent core yet";return false;}
unsigned studio_cheat_count(StudioCore*) {return 0;}
void studio_cheat_clear(StudioCore*) {}
bool studio_cheat_set_enabled(StudioCore*,bool) {error="Cheats are not implemented in this independent core yet";return false;}
}
