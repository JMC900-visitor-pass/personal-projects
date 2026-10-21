// Register-only adapter for the external SingleStepTests/ARM7TDMI v1 format.
// Scope is explicitly user/system, non-mode-changing arithmetic/PSR vectors.
// The external data is emulator-generated, not a hardware timing oracle.
#include "crispy/gba.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
using namespace crispy;
namespace crispy {
struct GBAConformanceAccess {
    static void execute(GBA& g,uint32_t opcode,uint32_t pc,bool thumb) {
        g.cpu_.r[15]=pc+(thumb?2:4);
        if (thumb) g.thumb(uint16_t(opcode),pc);
        else if (g.condition(opcode>>28)) g.arm(opcode,pc);
    }
};
}
struct Reader {
    std::vector<uint8_t> bytes;size_t at=0;
    uint32_t word() {
        if (at+4>bytes.size()) throw std::runtime_error("Truncated conformance input");
        auto p=at;at+=4;return uint32_t(bytes[p])|uint32_t(bytes[p+1])<<8|uint32_t(bytes[p+2])<<16|uint32_t(bytes[p+3])<<24;
    }
    std::array<uint32_t,40> state() {
        auto begin=at;auto size=word();word();std::array<uint32_t,40> result{};
        for (auto& v:result) v=word();if (at!=begin+size) throw std::runtime_error("Unsupported conformance state layout");return result;
    }
};
int main(int argc,char** argv) {
    try {
        if (argc<2) throw std::runtime_error("Usage: arm-conformance category.json.bin ...");
        auto core=std::make_unique<GBA>();auto& g=*core;unsigned allChecked=0,allFailed=0;
        std::cout<<"{\"scope\":\"user/system register-only vectors; no bus/timing or exception-return coverage\",\"categories\":[\n";
        for (int f=1;f<argc;++f) {
            auto name=std::filesystem::path(argv[f]).filename().string();
            const char* supported[]={"arm_data_proc_immediate.json.bin","arm_data_proc_immediate_shift.json.bin","arm_data_proc_register_shift.json.bin","arm_mul_mla.json.bin","arm_mull_mlal.json.bin","arm_mrs.json.bin","arm_msr_imm.json.bin","arm_msr_reg.json.bin","thumb_add_cmp_mov_hi.json.bin","thumb_add_sub.json.bin","thumb_data_proc.json.bin","thumb_lsl_lsr_asr.json.bin","thumb_mov_cmp_add_sub.json.bin"};
            bool allowed=false;for (auto category:supported) if (name==category) allowed=true;
            if (!allowed) throw std::runtime_error("Category is outside the adapter scope: "+name);
            std::ifstream file(argv[f],std::ios::binary);if (!file) throw std::runtime_error("Cannot open "+name);
            Reader input{{std::istreambuf_iterator<char>(file),{}}};
            if (input.word()!=0xd33dbae0) throw std::runtime_error("Invalid external vector magic");
            auto count=input.word();unsigned checked=0,skipped=0,failed=0;
            for (unsigned test=0;test<count;++test) {
                auto begin=input.at;auto size=input.word();auto initial=input.state(),expected=input.state();
                auto txStart=input.at;auto txSize=input.word();input.at=txStart+txSize;
                input.word();input.word();auto opcode=input.word(),pc=input.word();
                if (input.at!=begin+size || input.at>input.bytes.size()) throw std::runtime_error("Invalid external vector size");
                auto mode=initial[31]&31;bool thumb=initial[31]&32;
                bool outside=(mode!=0x10 && mode!=0x1f) || (expected[31]&31)!=mode;
                bool multiply=name=="arm_mul_mla.json.bin" || name=="arm_mull_mlal.json.bin";
                if (!thumb) {
                    // PC+S in a non-exception mode and MRS SPSR lack an SPSR.
                    bool data=name.starts_with("arm_data_proc");unsigned operation=(opcode>>21)&15;
                    outside|=data && (opcode&(1<<20)) && ((opcode>>12)&15)==15 && !(operation>=8 && operation<=11);
                    outside|=name=="arm_mrs.json.bin" && (opcode&(1<<22));
                    outside|=(name=="arm_msr_reg.json.bin" || name=="arm_msr_imm.json.bin") && (opcode&(1<<22));
                    if (multiply) outside|=(opcode&15)==15 || ((opcode>>8)&15)==15 || ((opcode>>12)&15)==15 || ((opcode>>16)&15)==15;
                }
                if (outside) {++skipped;continue;}
                ++checked;auto& r=g.debugRegisters();r=ARMRegisters{};
                for (unsigned n=0;n<16;++n) r.r[n]=initial[n];r.cpsr=initial[31];
                bool pass=true;std::string error;
                try {GBAConformanceAccess::execute(g,opcode,pc,thumb);}catch (const std::exception& e) {pass=false;error=e.what();}
                for (unsigned n=0;n<16;++n) {
                    auto want=expected[n];if (n==15) {bool thumbPC=expected[31]&32;want=(want-(thumbPC?4:8))&~(thumbPC?1u:3u);}
                    if (r.r[n]!=want) {
                        pass=false;if (error.empty()) {error="r"+std::to_string(n)+" expected="+std::to_string(want)+" actual="+std::to_string(r.r[n]);}
                    }
                }
                // The core stores an aligned instruction address; the vectors retain raw
                // low PC bits even though their fetch transactions are aligned.
                // ARM7 multiply's C flag is architecturally unspecified.
                bool thumbMultiply=thumb && (opcode&0xffc0)==0x4340;
                uint32_t mask=(multiply || thumbMultiply)?~(1u<<29):0xffffffffu;
                if ((r.cpsr&mask)!=(expected[31]&mask)) {pass=false;if (error.empty()) error="CPSR expected="+std::to_string(expected[31])+" actual="+std::to_string(r.cpsr);}
                if (!pass) {++failed;if (failed<=8) std::cerr<<name<<" #"<<test<<" opcode=0x"<<std::hex<<opcode<<" pc=0x"<<pc<<std::dec<<" "<<error<<"\n";}
            }
            if (input.at!=input.bytes.size()) throw std::runtime_error("Trailing vector data");
            if (f>1) std::cout<<",\n";
            std::cout<<"{\"file\":\""<<name<<"\",\"total\":"<<count<<",\"checked\":"<<checked<<",\"outside_scope\":"<<skipped<<",\"failed\":"<<failed<<"}";
            allChecked+=checked;allFailed+=failed;
        }
        std::cout<<"\n],\"checked\":"<<allChecked<<",\"failed\":"<<allFailed<<"}\n";
        return allFailed?1:0;
    } catch (const std::exception& e) {std::cerr<<e.what()<<"\n";return 2;}
}
