#include "crispy/core.hpp"
#include "crispy/gb.hpp"
#include "crispy/gba.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <iomanip>
#include <optional>
int main(int argc,char** argv) {
    try {
        if (argc<2) {std::cerr<<"Usage: crispy-core ROM [--frames N] [--ppm PATH] [--mooneye MAX_INSTRUCTIONS]\n";return 2;}
        std::string path=argv[1],image;uint64_t frames=3,limit=0;std::optional<crispy::System> forced;
        for (int i=2;i<argc;++i) {
            std::string argument=argv[i];if (i+1>=argc) throw std::runtime_error("Missing option value");
            if (argument=="--frames") frames=std::stoull(argv[++i]);else if (argument=="--ppm") image=argv[++i];else if (argument=="--mooneye") limit=std::stoull(argv[++i]);else if (argument=="--system") {std::string name=argv[++i];if (name=="gb") forced=crispy::System::gb;else if (name=="gbc") forced=crispy::System::gbc;else if (name=="gba") forced=crispy::System::gba;else throw std::runtime_error("Unknown system");}else throw std::runtime_error("Unknown option: "+argument);
        }
        if (frames>1000000 || limit>1000000000) throw std::runtime_error("Run budget is too large");
        std::ifstream input(path,std::ios::binary);if (!input) throw std::runtime_error("Cannot open ROM");
        std::vector<uint8_t> rom{std::istreambuf_iterator<char>(input),{}};
        auto core=crispy::makeCore(forced.value_or(crispy::systemForPath(path)));core->load(rom);
        if (limit) {
            auto* gb=dynamic_cast<crispy::GameBoy*>(core.get());if (!gb) throw std::runtime_error("Mooneye protocol requires a GB/GBC ROM");
            for (uint64_t n=0;n<limit;++n) {
                const auto& r=gb->debugRegisters();
                if (core->inspect(r.pc)==0x40) {
                    if (r.b==3&&r.c==5&&r.d==8&&r.e==13&&r.h==21&&r.l==34) {std::cout<<"PASS "<<path<<" instructions="<<n<<"\n";return 0;}
                    if (r.b==0x42&&r.c==0x42&&r.d==0x42&&r.e==0x42&&r.h==0x42&&r.l==0x42) {std::cerr<<"FAIL "<<path<<"\n";return 1;}
                }
                core->step();
            }
            const auto& r=gb->debugRegisters();std::cerr<<"TIMEOUT "<<path<<" PC="<<std::hex<<r.pc<<" BC="<<unsigned(r.b)<<":"<<unsigned(r.c)<<" DE="<<unsigned(r.d)<<":"<<unsigned(r.e)<<" HL="<<unsigned(r.h)<<":"<<unsigned(r.l)<<"\n";return 3;
        }
        for (uint64_t n=0;n<frames;++n) core->runFrame();
        auto cap=core->capabilities();auto stats=core->statistics();
        std::cout<<"Crispy Core | "<<crispy::systemName(cap.system)<<" | "<<cap.stage<<" | "<<core->title()<<" | "<<cap.width<<"x"<<cap.height<<" | cycles="<<stats.cycles<<" instructions="<<stats.instructions<<" frames="<<stats.frames<<"\n";
        if (auto* gb=dynamic_cast<crispy::GameBoy*>(core.get())) std::cout<<gb->serialOutput();
        if (!image.empty()) {
            std::ofstream ppm(image,std::ios::binary);if (!ppm) throw std::runtime_error("Cannot create frame image");ppm<<"P6\n"<<cap.width<<" "<<cap.height<<"\n255\n";
            for (auto pixel:core->pixels()) {char bytes[]={char(pixel),char(pixel>>8),char(pixel>>16)};ppm.write(bytes,3);}if (!ppm) throw std::runtime_error("Cannot write frame image");
        }
        return 0;
    } catch (const std::exception& e) {std::cerr<<"CRISPY_CORE_ERROR: "<<e.what()<<"\n";return 1;}
}
