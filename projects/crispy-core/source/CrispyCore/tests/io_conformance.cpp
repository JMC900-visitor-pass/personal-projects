// Executes published IO-read expectations through original ARM store/load code.
#include "crispy/gba.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
using namespace crispy;
int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: io-conformance reference.tsv");
        std::ifstream input(argv[1]);if (!input) throw std::runtime_error("Cannot read IO vectors");
        auto core=std::make_unique<GBA>();auto& g=*core;std::vector<uint8_t> rom(0xc0);rom[0xb2]=0x96;
        unsigned count=0,failed=0;std::string line;
        while (std::getline(input,line)) {
            std::istringstream row(line);uint32_t address,expected,store;std::string name;
            if (!(row>>std::hex>>address>>expected>>store)) throw std::runtime_error("Malformed IO vector");std::getline(row,name);
            g.load(rom);const uint32_t code[]={0xe1c010b0,0xe1d020b0,0xea000000,0xdeaddead,0xe1a00000};
            for (unsigned n=0;n<5;++n) for (unsigned b=0;b<4;++b) g.debugWrite(0x03000000+n*4+b,code[n]>>(b*8));
            auto& r=g.debugRegisters();r.r[15]=store?0x03000000:0x03000004;r.r[0]=address;r.r[1]=0xffff;
            if (store) g.step();g.step();++count;
            if (r.r[2]!=expected) {++failed;std::cerr<<name<<": expected 0x"<<std::hex<<expected<<", got 0x"<<r.r[2]<<std::dec<<"\n";}
        }
        if (!count) throw std::runtime_error("Empty IO vector selection");
        std::cout<<"{\"suite\":\"published mGBA IO-read expectations via local ARM fixture\",\"checked\":"<<count<<",\"failed\":"<<failed<<"}\n";
        return failed?1:0;
    } catch (const std::exception& e) {std::cerr<<e.what()<<"\n";return 2;}
}
