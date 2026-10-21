#include "EmulatorBridge.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
#include <cstring>
void require(bool v,const char* why) {if (!v) throw std::runtime_error(why);}
std::vector<uint8_t> read(const std::filesystem::path& p) {std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char** argv) {
    try {
        require(argc==3,"Use bridge-checks DEMO_DIRECTORY TEMP_DIRECTORY");
        auto root=std::filesystem::path(argv[2]);std::filesystem::create_directories(root);
        for (const char* ext:{"gb","gbc","gba"}) {
            auto rom=std::filesystem::path(argv[1])/(std::string("crispy-demo.")+ext),dir=root/ext;std::filesystem::create_directories(dir);
            auto* c=studio_create(rom.c_str(),dir.c_str());require(c,"Create console through C boundary");
            require(std::string(studio_core_name(c)).find("Crispy Core")==0,"Bridge must identify its independent backend");
            for (unsigned n=0;n<3;++n) studio_run_frame(c);
            require(std::strlen(studio_runtime_error(c))==0,"Demo must not fault");require(studio_width(c)==(std::string(ext)=="gba"?240u:160u),"Native framebuffer dimensions");
            float audio[16];std::fill_n(audio,16,1);require(studio_read_audio(c,audio,8)==0,"Prototype audio reports unavailable");for (auto sample:audio) require(sample==0,"Unavailable audio is silent");
            auto state=dir/"slot.cstate";require(studio_save_state(c,state.c_str()),"Commit state");require(studio_load_state(c,state.c_str()),"Restore state");
            require(!studio_load_state(c,(dir/"absent.cstate").c_str()),"Missing state is a recoverable failure");studio_run_frame(c);require(std::strlen(studio_runtime_error(c))==0,"Failed load leaves live core usable");studio_destroy(c);
        }
        auto bad=read(std::filesystem::path(argv[1])/"crispy-demo.gba");bad[0]=0;bad[1]=0;bad[2]=0xff;bad[3]=0xef; // SWI: unsupported BIOS service
        auto rom=root/"unsupported.gba";std::ofstream f(rom,std::ios::binary);f.write(reinterpret_cast<char*>(bad.data()),bad.size());f.close();
        auto* c=studio_create(rom.c_str(),root.c_str());require(c,"Unsupported instruction ROM can initialise");auto state=root/"last-valid.cstate";
        require(studio_save_state(c,state.c_str()),"Save valid starting point");auto before=read(state);studio_run_frame(c);require(std::strlen(studio_runtime_error(c))>0,"Runtime failure latches a descriptive error");
        require(!studio_save_state(c,state.c_str()),"Faulted core cannot overwrite valid state");require(read(state)==before,"Last valid state survives a core fault");
        require(studio_load_state(c,state.c_str()),"Valid state reload clears runtime fault");require(std::strlen(studio_runtime_error(c))==0,"Fault cleared only after valid restore/reset");studio_destroy(c);
        std::cout<<"PASS: GB/GBC/GBA C ABI, native frames, honest silent audio, atomic state load/save and faulted-core save protection\n";
    } catch (const std::exception& e) {std::cerr<<"FAIL bridge: "<<e.what()<<"\n";return 1;}
}
