#include "crispy/core.hpp"
#include "crispy/gb.hpp"
#include "crispy/gba.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
using namespace crispy;
namespace {
unsigned checks=0;
void require(bool v,const std::string& reason) {++checks;if (!v) throw std::runtime_error(reason);}
template<class F> void rejects(F f,const std::string& why) {bool threw=false;try {f();}catch (const std::exception&) {threw=true;}require(threw,why);}
std::vector<uint8_t> gbROM(unsigned banks=2,uint8_t type=0,uint8_t ram=0) {std::vector<uint8_t> r(banks*0x4000);r[0x147]=type;r[0x149]=ram;return r;}
std::vector<uint8_t> gbaROM() {std::vector<uint8_t> r(32768);r[0xb2]=0x96;return r;}
void quiet(GameBoy& g) {g.debugWrite(0xff40,0);g.debugWrite(0xffff,0);g.debugWrite(0xff0f,0);}
void program(GameBoy& g,std::initializer_list<uint8_t> bytes) {unsigned a=0xc000;for (auto b:bytes) g.debugWrite(a++,b);auto& r=g.debugRegisters();r=GBRegisters{};r.pc=0xc000;}
std::vector<uint8_t> file(const std::string& path) {std::ifstream f(path,std::ios::binary);if (!f) throw std::runtime_error("Cannot read fixture "+path);return {std::istreambuf_iterator<char>(f),{}};}
void aluChecks() {
    GameBoy g;g.load(gbROM());quiet(g);
    for (unsigned operation=0;operation<8;++operation) for (unsigned carry=0;carry<2;++carry) for (unsigned a=0;a<256;++a) for (unsigned b=0;b<256;++b) {
        g.debugWrite(0xc000,uint8_t(0xc6+operation*8));g.debugWrite(0xc001,b);
        auto& cpu=g.debugRegisters();cpu.pc=0xc000;cpu.a=a;cpu.f=carry?0x10:0;cpu.ime=false;cpu.halted=false;
        unsigned cycles=g.step(),result=0,flags=0,c=(operation==1 || operation==3)?carry:0;
        if (operation<=1) {result=a+b+c;flags=((a%16+b%16+c)>15?0x20:0)|(result>255?0x10:0);}
        else if (operation==2 || operation==3 || operation==7) {result=(a-b-c)&255;flags=0x40|((a%16)<(b%16+c)?0x20:0)|(a<b+c?0x10:0);}
        else if (operation==4) {result=a&b;flags=0x20;}else if (operation==5) result=a^b;else result=a|b;
        result&=255;if (!result) flags|=0x80;
        require(cpu.a==(operation==7?a:result) && cpu.f==flags && cycles==8,"GB ALU result/flags/cycles op="+std::to_string(operation));
    }
}
void instructionChecks() {
    GameBoy g;g.load(gbROM());quiet(g);
    program(g,{0x31,0x00,0xd0,0xcd,0x09,0xc0,0x00,0x18,0xfe,0x3e,0x42,0xc9});
    require(g.step()==12,"LD SP timing");require(g.step()==24 && g.debugRegisters().pc==0xc009,"CALL timing and PC");
    require(g.inspect(0xcffe)==6 && g.inspect(0xcfff)==0xc0,"CALL stack byte order");g.step();require(g.step()==16 && g.debugRegisters().pc==0xc006 && g.debugRegisters().a==0x42,"RET and accumulator");
    program(g,{0xf8,0xfe});g.debugRegisters().sp=1;require(g.step()==12 && g.debugRegisters().h==0xff && g.debugRegisters().l==0xff && g.debugRegisters().f==0,"LD HL,SP+negative wrap");
    program(g,{0xe8,0x08});g.debugRegisters().sp=0xfff8;require(g.step()==16 && g.debugRegisters().sp==0 && g.debugRegisters().f==0x30,"ADD SP signed flags");
    program(g,{0xfb,0x00,0x00});g.debugWrite(0xffff,1);g.debugWrite(0xff0f,1);
    g.step();require(!g.debugRegisters().ime,"EI must delay enabling interrupts");g.step();require(g.debugRegisters().ime,"EI enables after next instruction");
    require(g.step()==20 && g.debugRegisters().pc==0x40 && !g.debugRegisters().ime,"Interrupt dispatch, priority and cycles");
    quiet(g);program(g,{0x76,0x3e,0x12});g.debugWrite(0xffff,1);g.debugWrite(0xff0f,1);g.step();require(g.debugRegisters().haltBug,"HALT bug latch");g.step();require(g.debugRegisters().a==0x3e,"HALT bug suppresses one PC increment");
    quiet(g);
    for (unsigned cb=0;cb<256;++cb) {
        program(g,{0xcb,uint8_t(cb)});auto& r=g.debugRegisters();r.h=0xc1;r.l=0;r.b=0x81;r.c=0x81;r.d=0x81;r.e=0x81;r.a=0x81;r.f=0x10;g.debugWrite(0xc100,0x81);
        unsigned expected=(cb&7)==6?(cb>>6)==1?12:16:8;
        require(g.step()==expected,"CB opcode timing "+std::to_string(cb));require(!(r.f&15),"Flags low nibble always zero");
    }
    for (auto op:{0xd3,0xdb,0xdd,0xe3,0xe4,0xeb,0xec,0xed,0xf4,0xfc,0xfd}) {program(g,{uint8_t(op)});rejects([&]{g.step();},"Undefined GB opcode must fail explicitly");}
}
void busAndClockChecks() {
    GameBoy g;g.load(gbROM());quiet(g);
    g.debugWrite(0xc123,0x5a);require(g.inspect(0xe123)==0x5a,"WRAM echo");g.debugWrite(0xe456,0x76);require(g.inspect(0xc456)==0x76,"Echo writes");
    g.debugWrite(0xff00,0x10);g.setKeys(1);require((g.inspect(0xff00)&1)==0 && (g.inspect(0xff0f)&16),"Active-low A and joypad interrupt");
    program(g,{0x00});g.debugWrite(0xff04,0);g.debugWrite(0xff05,0);g.debugWrite(0xff07,5);
    for (unsigned i=0;i<4;++i) {g.debugRegisters().pc=0xc000;g.step();}require(g.inspect(0xff05)==1,"TIMA falling edge at 16 T cycles");
    g.debugWrite(0xff04,0);g.debugWrite(0xff05,0xff);g.debugWrite(0xff06,0x93);g.debugWrite(0xff0f,0);
    for (unsigned i=0;i<4;++i) {g.debugRegisters().pc=0xc000;g.step();}require(g.inspect(0xff05)==0 && !(g.inspect(0xff0f)&4),"TIMA overflow has delayed reload");
    g.debugRegisters().pc=0xc000;g.step();require(g.inspect(0xff05)==0x93 && (g.inspect(0xff0f)&4),"TIMA reload and IRQ after four cycles");
    g.debugWrite(0xff07,0);for (unsigned i=0;i<160;++i) g.debugWrite(0xc000+i,i);g.debugWrite(0xff46,0xc0);
    g.debugWrite(0xff80,0x00);for (unsigned i=0;i<162;++i) {g.debugRegisters().pc=0xff80;g.step();}
    for (unsigned i=0;i<160;++i) require(g.inspect(0xfe00+i)==i,"OAM DMA byte order");
    auto rom=gbROM(4,3,3);for (unsigned b=0;b<4;++b) rom[b*0x4000]=b;g.load(rom);quiet(g);
    require(g.inspect(0x4000)==1,"MBC1 initial ROM bank");g.debugWrite(0x2000,2);require(g.inspect(0x4000)==2,"MBC1 bank switching");
    g.debugWrite(0,0x0a);g.debugWrite(0x6000,1);g.debugWrite(0x4000,1);g.debugWrite(0xa000,0x42);g.debugWrite(0x4000,0);require(g.inspect(0xa000)==0xff,"MBC1 RAM bank isolation");g.debugWrite(0x4000,1);require(g.inspect(0xa000)==0x42,"MBC1 RAM bank return");
    require(g.battery().size()==0x8000,"Battery size follows cartridge RAM");
    GameBoy cgb(true);cgb.load(gbROM());quiet(cgb);cgb.debugWrite(0xff4f,0);cgb.debugWrite(0x8000,0x11);cgb.debugWrite(0xff4f,1);cgb.debugWrite(0x8000,0x22);cgb.debugWrite(0xff4f,0);require(cgb.inspect(0x8000)==0x11,"CGB VRAM banks");
    cgb.debugWrite(0xff70,2);cgb.debugWrite(0xd000,0xab);cgb.debugWrite(0xff70,1);require(cgb.inspect(0xd000)==0,"CGB WRAM banks");
    cgb.debugWrite(0xff68,0xbf);cgb.debugWrite(0xff69,0x7c);require(cgb.inspect(0xff68)==0x80,"CGB palette auto-index wraps");
    program(cgb,{0x10,0});cgb.debugWrite(0xff4d,1);cgb.step();require(cgb.inspect(0xff4d)&0x80,"CGB STOP speed switch");
    cgb.debugWrite(0xc000,0);cgb.debugRegisters().pc=0xc000;require(cgb.step()==2,"CGB double-speed CPU advances two base dots per NOP");
}
void armProgram(GBA& g,std::initializer_list<uint32_t> words) {unsigned address=0x03000000;for (auto word:words) {for (unsigned b=0;b<4;++b) g.debugWrite(address++,word>>(b*8));}g.debugRegisters()=ARMRegisters{};g.debugRegisters().r[15]=0x03000000;g.debugRegisters().r[13]=0x03007f00;g.debugRegisters().banked[2][0]=0x03007fa0;g.debugRegisters().banked[3][0]=0x03007fe0;}
void thumbProgram(GBA& g,std::initializer_list<uint16_t> words) {unsigned address=0x03000000;for (auto word:words) {g.debugWrite(address++,word);g.debugWrite(address++,word>>8);}g.debugRegisters()=ARMRegisters{};g.debugRegisters().cpsr|=32;g.debugRegisters().r[15]=0x03000000;g.debugRegisters().r[13]=0x03007f00;g.debugRegisters().banked[2][0]=0x03007fa0;g.debugRegisters().banked[3][0]=0x03007fe0;}
void gbaChecks() {
    GBA g;g.load(gbaROM());
    armProgram(g,{0xe3a000ff,0xe2900001,0xe3500c01,0x03a01042,0x13a01099});
    for (int i=0;i<5;++i) g.step();require(g.debugRegisters().r[0]==256 && g.debugRegisters().r[1]==0x42 && (g.debugRegisters().cpsr&(1u<<30)),"ARM immediate rotation, CMP and conditional execution");
    armProgram(g,{0xe0902001});g.debugRegisters().r[0]=0x7fffffff;g.debugRegisters().r[1]=1;g.step();require(g.debugRegisters().r[2]==0x80000000 && (g.debugRegisters().cpsr&0xf0000000)==0x90000000,"ARM signed overflow flags");
    armProgram(g,{0xe0902001});g.debugRegisters().r[0]=0xffffffff;g.debugRegisters().r[1]=1;g.step();require(g.debugRegisters().r[2]==0 && (g.debugRegisters().cpsr&0xf0000000)==0x60000000,"ARM carry and zero flags");
    armProgram(g,{0xe1a02061});g.debugRegisters().r[1]=2;g.debugRegisters().cpsr|=1u<<29;g.step();require(g.debugRegisters().r[2]==0x80000001,"ARM RRX uses old carry");
    armProgram(g,{0xe8a00006,0xe2400008,0xe8b00018});g.debugRegisters().r[0]=0x02000000;g.debugRegisters().r[1]=0x12345678;g.debugRegisters().r[2]=0xaabbccdd;g.step();g.step();g.step();require(g.debugRegisters().r[3]==0x12345678 && g.debugRegisters().r[4]==0xaabbccdd,"ARM STM/LDM register order and writeback");
    armProgram(g,{0xe12fff10});g.debugRegisters().r[0]=0x03000101;g.debugWrite(0x03000100,0x2a);g.debugWrite(0x03000101,0x21);g.step();require((g.debugRegisters().cpsr&32) && g.debugRegisters().r[15]==0x03000100,"ARM BX enters Thumb");g.step();require(g.debugRegisters().r[1]==42,"Thumb instruction after BX");
    thumbProgram(g,{0x20ff,0x3001,0x2800,0xd100,0x2142});for (int i=0;i<4;++i) g.step();require(g.debugRegisters().r[0]==256 && g.debugRegisters().r[1]==0,"Thumb compare and conditional branch");
    thumbProgram(g,{0xb503,0x2000,0x2100,0xbd03});g.debugRegisters().r[0]=0x1234;g.debugRegisters().r[1]=0x5678;g.debugRegisters().r[14]=0x03000201;for (int i=0;i<4;++i) g.step();require(g.debugRegisters().r[0]==0x1234 && g.debugRegisters().r[1]==0x5678 && g.debugRegisters().r[15]==0x03000200,"Thumb PUSH/POP PC, register order and stack recovery");
    g.debugWrite(0x02000000,0x78);g.debugWrite(0x02000001,0x56);g.debugWrite(0x02000002,0x34);g.debugWrite(0x02000003,0x12);require(g.debugRead32(0x02000001)==0x78123456,"ARM unaligned word load rotates");
    g.debugWrite(0x02040000,0x5a);require(g.inspect(0x02000000)==0x5a,"GBA EWRAM mirror");
    rejects([&]{g.debugWrite(0x0e000000,1);},"Unsupported GBA save hardware must not silently discard writes");
    armProgram(g,{0xefff0000});rejects([&]{g.step();},"Unimplemented BIOS SWI must stop with an error");
    const uint32_t samples[]={0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff};
    for (unsigned kind=0;kind<4;++kind) for (unsigned amount:{0u,1u,31u,32u,33u,255u}) for (bool initial:{false,true}) for (auto sample:samples) {
        armProgram(g,{uint32_t(0xe1b02011|(kind<<5))});g.debugRegisters().r[0]=amount;g.debugRegisters().r[1]=sample;g.debugRegisters().cpsr|=(1u<<28)|(initial?1u<<29:0);
        uint32_t expected=sample;bool carry=initial;
        for (unsigned bit=0;bit<amount;++bit) {
            if (!kind) {carry=expected>>31;expected<<=1;}
            else {bool low=expected&1;expected=(expected>>1)|(kind==2?(expected&0x80000000):kind==3&&low?0x80000000:0);carry=low;}
        }
        g.step();auto flags=(expected&0x80000000)|(expected==0?1u<<30:0)|(carry?1u<<29:0)|(1u<<28);
        require(g.debugRegisters().r[2]==expected && (g.debugRegisters().cpsr&0xf0000000)==flags,"ARM register-shift boundary and flag vector");
    }
    for (auto a:samples) for (auto b:samples) for (bool carry:{false,true}) for (bool subtraction:{false,true}) {
        armProgram(g,{subtraction?0xe0d02001u:0xe0b02001u});g.debugRegisters().r[0]=a;g.debugRegisters().r[1]=b;if (carry) g.debugRegisters().cpsr|=1u<<29;
        uint64_t unsignedResult=subtraction?uint64_t(a)-b-!carry:uint64_t(a)+b+carry;
        int64_t signedResult=subtraction?int64_t(int32_t(a))-int32_t(b)-!carry:int64_t(int32_t(a))+int32_t(b)+carry;
        uint32_t value=unsignedResult;bool c=subtraction?uint64_t(a)>=uint64_t(b)+!carry:unsignedResult>0xffffffff;
        bool overflow=signedResult>INT32_MAX || signedResult<INT32_MIN;
        uint32_t flags=(value&0x80000000)|(value==0?1u<<30:0)|(c?1u<<29:0)|(overflow?1u<<28:0);
        g.step();require(g.debugRegisters().r[2]==value && (g.debugRegisters().cpsr&0xf0000000)==flags,"ARM ADC/SBC boundary vector");
    }

}
void armModeChecks() {
    GBA g;g.load(gbaROM());
    // Execute the exact reported opcode at the reported cartridge address.
    auto rom=gbaROM();rom.resize(0x210);rom[0x208]=0;rom[0x209]=0xf0;rom[0x20a]=0x29;rom[0x20b]=0xe1;
    g.load(rom);g.debugRegisters().r[15]=0x08000208;g.debugRegisters().r[0]=0xd2;g.step();
    require(g.debugRegisters().cpsr==0xd2 && g.debugRegisters().r[13]==0x03007fa0,"Reported startup MSR enters IRQ with post-BIOS stack");
    armProgram(g,{0xe129f000});
    auto execute=[&](uint32_t op) {for (unsigned b=0;b<4;++b) g.debugWrite(0x03000000+b,op>>(8*b));g.debugRegisters().r[15]=0x03000000;g.debugRegisters().cpsr&=~32u;g.step();};
    auto mode=[&](uint32_t m) {g.debugRegisters().r[0]=m;execute(0xe121f000);};
    const uint32_t modes[]={0x1f,0x11,0x12,0x13,0x17,0x1b};
    for (unsigned i=0;i<6;++i) {
        mode(modes[i]);g.debugRegisters().r[13]=0x02001000+i*16;g.debugRegisters().r[14]=0x08001000+i*16;
        for (unsigned n=8;n<=12;++n) g.debugRegisters().r[n]=(i==1?0xf100:0x5500)+n;
        if (i) {g.debugRegisters().r[0]=(i<<28)|0x3f;execute(0xe16ff000);}
    }
    for (unsigned i=0;i<6;++i) {
        mode(modes[i]);require(g.debugRegisters().r[13]==0x02001000+i*16 && g.debugRegisters().r[14]==0x08001000+i*16,"Each ARM privileged mode retains SP/LR");
        for (unsigned n=8;n<=12;++n) require(g.debugRegisters().r[n]==(i==1?0xf100:0x5500)+n,"FIQ alone banks r8-r12");
        if (i) {execute(0xe14f1000);require(g.debugRegisters().r[1]==((i<<28)|0x3f),"MRS/MSR retain each mode SPSR independently");}
    }
    mode(0x10);require(g.debugRegisters().r[13]==0x02001000,"User and system share SP");
    g.debugRegisters().r[0]=0xf00000d3;execute(0xe12ff000);require(g.debugRegisters().cpsr==0xf0000010,"User MSR changes flags only, cannot gain privilege");
    execute(0xe10f1000);require(g.debugRegisters().r[1]==0xf0000010,"MRS reads current CPSR");
    rejects([&]{execute(0xe14f1000);},"User mode has no SPSR");
    armProgram(g,{0xe121f000});g.debugRegisters().r[0]=0x15;auto old=g.debugRegisters().cpsr;
    rejects([&]{g.step();},"Invalid ARM mode rejected");require(g.debugRegisters().cpsr==old,"Invalid mode does not corrupt CPSR");
    mode(0x13);g.debugRegisters().r[0]=0xf000003f;execute(0xe12ff000);
    require(g.debugRegisters().cpsr==0xf000001f,"MSR respects ARMv4T reserved bits and cannot set Thumb bit");
    mode(0x12);g.debugRegisters().r[0]=0x6000003f;execute(0xe16ff000);g.debugRegisters().r[14]=0x03000103;
    execute(0xe1b0f00e);require(g.debugRegisters().cpsr==0x6000003f && g.debugRegisters().r[15]==0x03000102,"MOVS PC restores SPSR and Thumb alignment");
    mode(0x12);g.debugRegisters().r[0]=0xa000001f;execute(0xe16ff000);g.debugRegisters().r[14]=0x03000208;
    execute(0xe25ef004);require(g.debugRegisters().cpsr==0xa000001f && g.debugRegisters().r[15]==0x03000204,"SUBS PC,LR restores saved flags rather than arithmetic flags");
    // Privileged block transfers with S bit access user bank without switching modes.
    mode(0x1f);g.debugRegisters().r[13]=0x12345678;g.debugRegisters().r[14]=0x87654321;
    mode(0x11);g.debugRegisters().r[13]=0x02004000;g.debugRegisters().r[0]=0x02000000;
    execute(0xe8c06000);require(g.debugRead32(0x02000000)==0x12345678 && g.debugRead32(0x02000004)==0x87654321,"STM caret stores user SP/LR from FIQ");
    g.debugRegisters().r[0]=0x02000000;execute(0xe8d00300);require(g.debugRegisters().userHigh[0]==0x12345678 && g.debugRegisters().userHigh[1]==0x87654321 && g.debugRegisters().r[13]==0x02004000,"LDM caret updates user registers, keeps FIQ bank active");
    mode(0x12);g.debugRegisters().r[0]=0x02000000;g.debugRegisters().r[1]=0x03000203;execute(0xe5801000);
    g.debugRegisters().r[0]=0x6000003f;execute(0xe16ff000);g.debugRegisters().r[0]=0x02000000;execute(0xe8f08000);
    require(g.debugRegisters().cpsr==0x6000003f && g.debugRegisters().r[15]==0x03000202 && g.debugRegisters().r[0]==0x02000004,"LDM caret PC restores CPSR, aligns Thumb PC and writes back");
    mode(0x13);auto saved=g.save();mode(0x11);g.debugRegisters().r[13]=0;g.debugRegisters().spsr.fill(0);g.restore(saved);
    require(g.save()==saved,"Save/restore preserves active and inactive ARM banks and SPSRs");
    mode(0x12);execute(0xe14f1000);require(g.debugRegisters().r[1]==0x6000003f,"Inactive SPSR survives save/load");
    // Immediate MSR and byte masks must preserve fields outside the requested mask.
    mode(0x1f);execute(0xe321f0d3);require(g.debugRegisters().cpsr==0x600000d3,"Immediate MSR switches to supervisor preserving flags");
    execute(0xe328f480);require(g.debugRegisters().cpsr==0x800000d3,"Immediate MSR flags preserves mode and interrupt masks");
    g.debugRegisters().r[0]=0;execute(0xe122f000);require(g.debugRegisters().cpsr==0x800000d3,"MSR reserved byte is ignored");
    g.debugRegisters().r[0]=0x15;execute(0xe161f000);auto badReturn=g.debugRegisters().cpsr;
    rejects([&]{execute(0xe1b0f00e);},"Invalid SPSR mode cannot be restored");
    require(g.debugRegisters().cpsr==badReturn,"Rejected exception return preserves current status");
    mode(0x12);g.debugRegisters().r[13]=0x02000000;g.debugRegisters().r[0]=0x1f;execute(0xe16ff000);
    execute(0xe8fd8000);mode(0x12);require(g.debugRegisters().r[13]==0x02000004,"LDM exception return writes back to outgoing banked stack");
    // Legacy GBA snapshots predate banked registers; keep them loadable.
    auto legacy=std::vector<uint8_t>(saved.begin(),saved.end()-22);legacy[3]=0x31;
    legacy.erase(legacy.begin()+89,legacy.begin()+206);legacy=protectState(std::move(legacy));
    rejects([&]{g.restore(legacy);},"Legacy states reject exception-mode snapshots");
    mode(0x1f);auto systemState=g.save();legacy.assign(systemState.begin(),systemState.end()-22);legacy[3]=0x31;
    legacy.erase(legacy.begin()+89,legacy.begin()+206);legacy=protectState(std::move(legacy));g.restore(legacy);
    require((g.debugRegisters().cpsr&31)==0x1f,"Existing version-one GBA states remain loadable");
}
void gbaServiceChecks() {
    GBA g;g.load(gbaROM());
    auto call=[&](unsigned service,bool thumb=false) {
        if (thumb) {g.debugWrite(0x03000000,service);g.debugWrite(0x03000001,0xdf);}
        else {auto op=0xef000000u|(service<<16);for (unsigned b=0;b<4;++b) g.debugWrite(0x03000000+b,op>>(b*8));}
        g.debugRegisters().r[15]=0x03000000;g.debugRegisters().cpsr=0xa000001f|(thumb?32:0);g.debugRegisters().halted=false;
        auto status=g.debugRegisters().cpsr;auto sp=g.debugRegisters().r[13];g.step();
        if ((service>=6 && service<=8) || service==0xb || service==0xc) {
            for (unsigned n=0;n<1000 && g.debugRegisters().r[15]<0x4000;++n) g.step();
        }
        require(g.debugRegisters().cpsr==status && g.debugRegisters().r[15]==0x03000000+(thumb?2:4) && g.debugRegisters().r[13]==sp,"BIOS HLE returns to caller state, PC and stack");
        require(g.debugRegisters().spsr[3]==status,"SWI records supervisor SPSR");
    };
    for (bool thumb:{false,true}) for (auto a:{INT32_MIN,-1234,-1,0,1,1234,INT32_MAX}) for (auto b:{INT32_MIN,-10,-1,1,10,INT32_MAX}) for (unsigned svc:{6u,7u}) {
        g.debugRegisters().r[svc==6?0:1]=uint32_t(a);g.debugRegisters().r[svc==6?1:0]=uint32_t(b);call(svc,thumb);
        int64_t q=int64_t(a)/b;require(g.debugRegisters().r[0]==uint32_t(q) && g.debugRegisters().r[1]==uint32_t(int64_t(a)%b) && g.debugRegisters().r[3]==uint32_t(q<0?-q:q),"Div/DivArm signed boundary vectors in ARM and Thumb");
    }
    for (unsigned n=0;n<65536;n+=61) for (uint32_t value:{n*n,n*n+uint32_t(n!=65535),n?n*n-1:0}) {
        g.debugRegisters().r[0]=value;call(8,n&1);auto root=g.debugRegisters().r[0];
        require(uint64_t(root)*root<=value && uint64_t(root+1)*(root+1)>value,"Integer BIOS square root bounds");
    }
    g.debugRegisters().r[0]=UINT32_MAX;call(8);require(g.debugRegisters().r[0]==65535,"Square root maximum unsigned input");
    armProgram(g,{0xef060000});g.debugRegisters().r[0]=7;g.debugRegisters().r[1]=0;auto status=g.debugRegisters().cpsr;
    rejects([&]{g.step();},"BIOS division by zero fails explicitly rather than invoking host undefined behaviour");require(g.debugRegisters().cpsr==status,"Rejected BIOS call leaves mode unchanged");
    for (bool fast:{false,true}) for (bool fill:{false,true}) for (bool word:{false,true}) for (unsigned count:{0u,1u,7u,8u,9u,16u}) {
        unsigned width=fast || word?4:2,actual=fast?(count+7)&~7u:count;
        for (unsigned n=0;n<128;++n) {g.debugWrite(0x02000000+n,n^0x5a);g.debugWrite(0x02001000+n,0xcc);}
        g.debugRegisters().r[0]=0x02000000;g.debugRegisters().r[1]=0x02001000;g.debugRegisters().r[2]=count|(fill?1u<<24:0)|(word?1u<<26:0);call(fast?0xc:0xb,fill);
        for (unsigned n=0;n<128;++n) require(g.inspect(0x02001000+n)==(n<actual*width?uint8_t((fill?n%width:n)^0x5a):0xcc),"CpuSet/CpuFastSet copy, fill, width, block rounding and bounds");
    }
    // A halfword transfer into palette RAM must not become duplicated byte writes.
    g.debugRegisters().r[0]=0x02000000;g.debugRegisters().r[1]=0x05000000;g.debugRegisters().r[2]=2;call(0xb);
    require(g.inspect(0x05000000)==0x5a && g.inspect(0x05000001)==0x5b,"CpuSet respects native palette halfword writes");
    g.debugRegisters().r[0]=0;g.debugRegisters().r[1]=0x02001000;g.debugRegisters().r[2]=1;auto before=g.debugRead32(0x02001000);call(0xc);
    require(g.debugRead32(0x02001000)==before,"BIOS copies reject BIOS source region");
    g.reset();armProgram(g,{0xef020000,0xe3a0402a});g.step();require(g.debugRegisters().halted,"Halt SWI stops instruction execution");
    auto instructions=g.statistics().instructions;g.step();require(g.statistics().instructions==instructions,"Halted core advances hardware without executing CPU");
    g.debugWrite(0x04000201,0x10);g.debugWrite(0x04000132,1);g.debugWrite(0x04000133,0x40);g.setKeys(1);g.step();
    require(!g.debugRegisters().halted && g.debugRegisters().r[4]==42,"Enabled pending IRQ wakes Halt even with IME disabled");
}
void gbaDecompressionChecks() {
    auto stream=[](bool lz,unsigned size,std::initializer_list<uint8_t> data) {
        std::vector<uint8_t> bytes{uint8_t(lz?0x10:0x30),uint8_t(size),uint8_t(size>>8),uint8_t(size>>16)};
        bytes.insert(bytes.end(),data);return bytes;
    };
    auto run=[&](unsigned service,bool thumb,uint32_t destination,const std::vector<uint8_t>& compressed,const std::vector<uint8_t>& expected,bool cartridge=false) {
        GBA g;auto rom=gbaROM();
        if (cartridge) std::copy(compressed.begin(),compressed.end(),rom.begin()+0x100);
        g.load(rom);
        if (thumb) thumbProgram(g,{uint16_t(0xdf00|service)});else armProgram(g,{0xef000000u|(service<<16)});
        for (unsigned n=0;n<compressed.size();++n) g.debugWrite(0x02000000+n,compressed[n]);
        for (unsigned n=0;n<expected.size()+4;++n) g.debugWrite(destination-2+n,0xcc);
        g.debugRegisters().r[0]=cartridge?0x0a000100:0x02000000;g.debugRegisters().r[1]=destination;
        auto status=g.debugRegisters().cpsr,sp=g.debugRegisters().r[13],pc=g.debugRegisters().r[15];auto before=g.save();
        g.step();
        require(g.debugRegisters().cpsr==status && g.debugRegisters().r[13]==sp && g.debugRegisters().r[15]==pc+(thumb?2:4),"Decompression returns to ARM/Thumb caller, mode and stack");
        for (unsigned n=0;n<expected.size();++n) require(g.inspect(destination+n)==expected[n],"BIOS decompression exact output bytes");
        if ((destination>>24)!=7) require(g.inspect(destination-1)==0xcc && g.inspect(destination+expected.size())==0xcc,"Decompression preserves destination sentinels");
        auto after=g.save();g.restore(before);g.step();require(g.save()==after,"Decompression state replay is deterministic");
    };
    // Original streams: literals, overlapping matches, maximum match length,
    // flag-byte rollover, raw runs and repeated runs crossing halfword pairs.
    auto lz=stream(true,12,{0x20,'A','B',0x70,1,'C','D'});
    std::vector<uint8_t> lzExpected{'A','B','A','B','A','B','A','B','A','B','A','B'};
    auto rl=stream(false,12,{2,'A','B','C',0x80,'D',3,'E','F','G','H',0x80,'I'});
    std::vector<uint8_t> rlExpected{'A','B','C','D','D','D','E','F','G','H','I','I'};
    for (bool thumb:{false,true}) {
        run(0x11,thumb,0x02002000,lz,lzExpected);
        run(0x14,thumb,0x03001001,rl,rlExpected,true);
        for (uint32_t dest:{0x02002000u,0x03001000u,0x05000002u,0x06000002u,0x07000002u}) {
            run(0x12,thumb,dest,lz,lzExpected,true);run(0x15,thumb,dest,rl,rlExpected);
        }
        run(0x11,thumb,0x02002001,stream(true,7,{0x40,'x',0x30,0}),std::vector<uint8_t>(7,'x'));
        run(0x14,thumb,0x02002001,stream(false,1,{0x80,0x7a}),{0x7a});
        run(0x12,thumb,0x06000002,stream(true,0,{}),{});
    }
    auto large=stream(true,4114,{});std::vector<uint8_t> expected;
    for (unsigned group=0;group<512;++group) {large.push_back(0);for (unsigned n=0;n<8;++n) {large.push_back(uint8_t(group*8+n));expected.push_back(uint8_t(group*8+n));}}
    large.insert(large.end(),{0x80,0xff,0xff});for (unsigned n=0;n<18;++n) expected.push_back(uint8_t(n));
    run(0x11,false,0x02002000,large,expected);run(0x12,true,0x06000002,large,expected,true);
    auto longRL=stream(false,258,{127});expected.clear();
    for (unsigned n=0;n<128;++n) {longRL.push_back(n);expected.push_back(n);}longRL.insert(longRL.end(),{255,0x5a});expected.insert(expected.end(),130,0x5a);
    run(0x14,true,0x02002001,longRL,expected);run(0x15,false,0x06000002,longRL,expected,true);
    auto invalid=[&](unsigned service,const std::vector<uint8_t>& bytes,uint32_t source,uint32_t dest) {
        GBA g;auto rom=gbaROM();
        if (source>=0x08000000 && source<0x08008000) std::copy(bytes.begin(),bytes.end(),rom.begin()+(source&0x7fff));
        g.load(rom);armProgram(g,{0xef000000u|(service<<16)});
        for (unsigned n=0;n<bytes.size();++n) if (source<0x08000000) g.debugWrite(source+n,bytes[n]);
        g.debugRegisters().r[0]=source;g.debugRegisters().r[1]=dest;
        auto before=g.debugRead32(dest),status=g.debugRegisters().cpsr,sp=g.debugRegisters().r[13];
        rejects([&]{g.step();},"Malformed/unsupported decompression must fail explicitly");
        require(g.debugRead32(dest)==before && g.debugRegisters().cpsr==status && g.debugRegisters().r[13]==sp,"Rejected decompression preserves destination, caller mode and stack");
    };
    invalid(0x11,stream(false,4,{0x81,1}),0x02000000,0x02002000);
    invalid(0x11,stream(true,4,{0x80,0,0}),0x02000000,0x02002000);
    invalid(0x11,stream(true,8,{0x40,1,0,4}),0x02000000,0x02002000);
    invalid(0x12,stream(true,4,{0x40,1,0,0}),0x02000000,0x06000000);
    invalid(0x12,lz,0x02000000,0x06000001);
    invalid(0x15,stream(false,3,{0x80,1}),0x02000000,0x06000000);
    invalid(0x11,lz,0x02000001,0x02002000);
    invalid(0x11,lz,0x02000000,0x0203fffc);
    invalid(0x11,lz,0x02000000,0x06000000);
    invalid(0x14,rl,0x02000000,0x04000000);
    invalid(0x11,lz,0x02000000,0x02000004);
    invalid(0x11,stream(true,4,{}),0x08007ffc,0x02002000);
    invalid(0x14,stream(false,4,{}),0x08007ffc,0x02002000);
    invalid(0x11,{},0x00000000,0x02002000);
    invalid(0x11,stream(true,0xffffff,{}),0x02000000,0x02002000);
}
void gbaIRQChecks() {
    auto put=[](GBA& g,uint32_t a,uint32_t value) {for (unsigned b=0;b<4;++b) g.debugWrite(a+b,value>>(8*b));};
    for (bool thumb:{false,true}) {
        GBA g;g.load(gbaROM());if (thumb) thumbProgram(g,{0x242a});else armProgram(g,{0xe3a0402a});
        auto& r=g.debugRegisters();for (unsigned i=0;i<4;++i) r.r[i]=0x11000000+i;r.r[12]=0xabcdef12;r.r[14]=0x08001234;r.r[4]=0;
        r.cpsr|=0xa0000000;r.banked[2][0]=0x03007fa0;
        const uint32_t handler[]={0xe59f000c,0xe3a01a01,0xe1c010b0,0xe2844001,0xe12fff1e,0x04000202};
        for (unsigned n=0;n<6;++n) put(g,0x03000100+n*4,handler[n]);put(g,0x03007ffc,0x03000100);
        g.debugWrite(0x04000201,0x10);g.debugWrite(0x04000208,1);g.debugWrite(0x04000132,1);g.debugWrite(0x04000133,0x40);g.setKeys(1);
        auto status=r.cpsr;auto sp=r.r[13];auto instructions=g.statistics().instructions;g.step();
        require(r.cpsr==((status&~63u)|0x92) && r.spsr[2]==status && r.r[14]==0x03000004 && r.r[15]==0x18,"IRQ exception enters ARM IRQ mode and saves caller status/link");
        require(g.statistics().instructions==instructions,"Exception entry is not counted as an executed instruction");
        g.step();g.step();require(r.r[13]==0x03007f88 && g.debugRead32(0x03007f88)==0x11000000 && g.debugRead32(0x03007f9c)==0x03000004,"IRQ wrapper pushes BIOS-compatible volatile register frame");
        g.step();g.step();g.step();
        require(r.r[0]==0x04000000 && r.r[15]==0x03000100,"IRQ callback receives the documented IO-base argument in r0");
        auto saved=g.save();
        auto finish=[&] {for (unsigned n=0;n<24 && (g.debugRegisters().cpsr&31)==0x12;++n) g.step();};
        finish();auto expected=g.save();require(r.cpsr==status && r.r[15]==0x03000000 && r.r[13]==sp && r.r[14]==0x08001234 && r.r[4]==1,"IRQ callback returns to exact interrupted ARM/Thumb instruction");
        for (unsigned i=0;i<4;++i) require(r.r[i]==0x11000000+i,"IRQ wrapper restores volatile registers");
        require(r.r[12]==0xabcdef12 && r.banked[2][0]==0x03007fa0 && !(g.inspect(0x04000203)&0x10),"IRQ wrapper restores r12 and stack; user handler acknowledges IF");
        g.restore(saved);finish();require(g.save()==expected,"Mid-IRQ snapshot replays trampoline and callback deterministically");
        g.step();require(r.r[4]==42,"CPU executes interrupted instruction after return");
    }
    GBA g;g.load(gbaROM());armProgram(g,{0xe1a00000,0xe1a00000});g.debugWrite(0x04000201,0x10);g.debugWrite(0x04000132,1);g.debugWrite(0x04000133,0x40);g.setKeys(1);
    g.step();require((g.debugRegisters().cpsr&31)==0x1f,"IME masks IRQ entry without clearing IF");
    g.debugWrite(0x04000208,1);g.debugRegisters().cpsr|=0x80;g.step();require((g.debugRegisters().cpsr&31)==0x1f && (g.inspect(0x04000203)&0x10),"CPSR I masks IRQ entry without clearing IF");
    g.debugRegisters().cpsr&=~0x80u;rejects([&]{g.step();},"Uninstalled IRQ callback reports a clear error");
}
void gbaWaitResetChecks() {
    GBA g;g.load(gbaROM());
    auto put=[&](uint32_t a,uint32_t value) {for (unsigned b=0;b<4;++b) g.debugWrite(a+b,value>>(8*b));};
    // An old matching BIOS flag returns immediately, consumes only the requested
    // bits, and enables IME even when no hardware interrupt is currently pending.
    armProgram(g,{0xef040000,0xe3a0402a});put(0x03007ff8,0x1001);g.debugRegisters().r[0]=0;g.debugRegisters().r[1]=1;g.step();
    require(!g.debugRegisters().halted && g.debugRead32(0x03007ff8)==0x1000 && g.inspect(0x04000208)==1,"IntrWait consumes matching old flags and enables IME");g.step();require(g.debugRegisters().r[4]==42,"IntrWait immediate path continues caller");
    armProgram(g,{0xef040000,0xe3a0402a});put(0x03007ff8,0x1001);g.debugRegisters().r[0]=1;g.debugRegisters().r[1]=1;g.debugRegisters().cpsr|=0x80;g.step();
    require(g.debugRegisters().halted && g.debugRead32(0x03007ff8)==0x1000 && !(g.debugRegisters().cpsr&0x80),"IntrWait discard path waits with IRQs enabled");
    auto saved=g.save();auto before=g.statistics().instructions;for (unsigned n=0;n<5;++n) g.step();require(g.statistics().instructions==before,"Waiting CPU does not execute following game instruction");
    put(0x03007ff8,0x1001);g.step();require(g.debugRegisters().r[4]==42 && (g.debugRegisters().cpsr&0x80) && g.debugRead32(0x03007ff8)==0x1000,"IntrWait resumes on BIOS flag, restores caller interrupt mask");
    auto expected=g.save();g.restore(saved);for (unsigned n=0;n<5;++n) g.step();put(0x03007ff8,0x1001);g.step();require(g.save()==expected,"Snapshot preserves pending BIOS wait and deterministic resumption");
    g.reset();thumbProgram(g,{0xdf05,0x242a});put(0x03007ff8,1);g.step();require(g.debugRegisters().halted && g.debugRegisters().r[0]==1 && g.debugRegisters().r[1]==1 && !g.debugRead32(0x03007ff8),"VBlankIntrWait discards old VBlank flag in Thumb mode");
    put(0x03007ff8,2);g.step();require(g.debugRegisters().halted && g.debugRegisters().r[4]==0,"Unrelated BIOS flag cannot release VBlank wait");
    put(0x03007ff8,3);g.step();require(g.debugRegisters().r[4]==42 && (g.debugRegisters().cpsr&32) && g.debugRead32(0x03007ff8)==2,"VBlank wait resumes Thumb caller and preserves unrelated flags");
    // Selective memory reset runs from ROM, so clearing IWRAM cannot erase the caller.
    auto rom=gbaROM();rom[0]=0;rom[1]=0;rom[2]=1;rom[3]=0xef;g.load(rom);
    for (auto a:{0x02000000u,0x03000000u,0x03007dffu,0x03007e00u,0x03007fffu}) g.debugWrite(a,0x5a);
    put(0x05000000,0x11223344);put(0x06000000,0x55667788);put(0x07000000,0x99aabbcc);
    g.debugRegisters().r[0]=0x1e;g.step();
    require(g.inspect(0x02000000)==0x5a && !g.inspect(0x03000000) && !g.inspect(0x03007dff) && g.inspect(0x03007e00)==0x5a && g.inspect(0x03007fff)==0x5a,"RegisterRamReset respects selected RAM and reserved IWRAM tail");
    require(!g.debugRead32(0x05000000) && !g.debugRead32(0x06000000) && !g.debugRead32(0x07000000) && g.inspect(0x04000000)==0x80,"RegisterRamReset clears video memory and forces blank");
    g.debugRegisters().r[15]=0x08000000;g.debugRegisters().r[0]=0xe0;g.debugWrite(0x04000208,1);g.debugWrite(0x04000101,0x12);g.debugWrite(0x04000103,0x80);g.step();
    require(g.debugRead32(0x04000100)==0 && !g.inspect(0x04000208) && g.inspect(0x04000135)==0x80 && (g.debugIO16(0x20)>>8)==1 && (g.debugIO16(0x26)>>8)==1,"RegisterRamReset initializes modeled IO, affine identities and timers");
    for (bool ram:{false,true}) {
        rom[2]=0;g.load(rom);g.debugWrite(0x02000100,0x55);g.debugWrite(0x03007dff,0x66);g.debugWrite(0x03007e00,0x77);g.debugWrite(0x03007ffa,ram);g.debugRegisters().r[4]=99;g.step();
        auto& r=g.debugRegisters();auto target=ram?0x02000000u:0x08000000u;
        require(r.cpsr==0x1f && r.r[15]==target && r.r[14]==target && r.r[13]==0x03007f00 && r.r[4]==0,"SoftReset selects ROM/RAM ARM entry and clears caller registers");
        require(g.inspect(0x02000100)==0x55 && g.inspect(0x03007dff)==0x66 && !g.inspect(0x03007e00) && !g.debugRead32(0x03007ffc),"SoftReset clears only reserved IWRAM tail");
        require(r.banked[2][0]==0x03007fa0 && r.banked[3][0]==0x03007fe0 && !r.spsr[2] && !r.spsr[3],"SoftReset initializes IRQ/SVC banks");
    }
    // Previous banked version-two states still load with no active HLE wait.
    g.reset();auto current=g.save();auto old=std::vector<uint8_t>(current.begin(),current.end()-22);old[3]=0x32;old.erase(old.begin()+201,old.begin()+206);old=protectState(std::move(old));g.restore(old);
    require((g.debugRegisters().cpsr&31)==0x1f,"Version-two banked states remain readable after BIOS wait state addition");
}
void gbaResetIOChecks() {
    GBA g;auto rom=gbaROM();rom[2]=1;rom[3]=0xef;g.load(rom);
    for (unsigned flags:{0u,0x20u,0x40u,0x80u,0xe0u}) {
        g.load(rom);g.setKeys(0x101);
        for (unsigned a:{0x120u,0x121u,0x122u,0x123u,0x128u,0x134u,0x135u,0x154u,0x155u,0x60u,0x80u,0x88u,0x89u,0x20u,0x21u,0x132u,0x133u,0x204u}) g.debugWrite(0x04000000+a,0x55);
        auto input=g.debugRead32(0x04000130)&0xffff;
        g.debugRegisters().r[0]=flags;g.step();
        require(g.inspect(0x04000000)==0x80 && g.inspect(0x04000001)==0 && !g.inspect(0x04000120) && !g.inspect(0x04000121),"Every RegisterRamReset forces blank and destroys SIODATA32 low halfword even without SIO flag");
        require(g.inspect(0x04000122)==(flags&0x20?0:0x55) && g.inspect(0x04000128)==(flags&0x20?0:0x55) && g.inspect(0x04000135)==(flags&0x20?0x80:0x55) && g.inspect(0x04000154)==(flags&0x20?0:0x55),"SIO reset selects general-purpose mode, resets serial/JOY and preserves unselected SIO");
        require(g.inspect(0x04000060)==(flags&0x40?0:0x55) && g.inspect(0x04000080)==(flags&0x40?0:0x55),"Sound reset selection remains independent of other IO flags");
        require((g.debugIO16(0x20)>>8)==(flags&0x80?1:0x55) && g.inspect(0x04000132)==(flags&0x80?0:0x55),"Other-IO reset restores affine identity and keypad control independently");
        require((g.debugRead32(0x04000130)&0xffff)==input && g.inspect(0x04000300)==1,"Selective reset preserves read-only keypad input and post-boot status");
    }
    // Exercise the timer's hidden reload/phase fields as well as visible IO.
    g.load(rom);for (unsigned b=0;b<4;++b) g.debugWrite(0x03000200+b,0xe1c010b0>>(b*8));
    g.debugRegisters().r[15]=0x03000200;g.debugRegisters().r[0]=0x04000100;g.debugRegisters().r[1]=0xfffe;g.step();
    g.debugRegisters().r[15]=0x03000200;g.debugRegisters().r[0]=0x04000102;g.debugRegisters().r[1]=0x80;g.step();
    g.debugRegisters().r[15]=0x08000000;g.debugRegisters().r[0]=0x80;g.step();
    for (unsigned b=0;b<4;++b) g.debugWrite(0x03000000+b,0xe1c010b0>>(b*8));
    g.debugRegisters().r[15]=0x03000000;g.debugRegisters().r[0]=0x04000102;g.debugRegisters().r[1]=0x80;g.step();
    require((g.debugRead32(0x04000100)&0xffff)<16,"IO reset clears hidden timer reload instead of restarting old near-overflow value");
    for (bool half:{false,true}) {
        g.reset();armProgram(g,{half?0xe1c010b0u:0xe5c01000u});g.debugRegisters().r[0]=half?0x04000300:0x04000301;g.debugRegisters().r[1]=half?1:0;
        g.step();require(g.debugRegisters().halted && g.inspect(0x04000300)==1,"HALTCNT byte and POSTFLG/HALTCNT halfword writes both enter Halt");
        g.reset();armProgram(g,{half?0xe1c010b0u:0xe5c01000u});g.debugRegisters().r[0]=half?0x04000300:0x04000301;g.debugRegisters().r[1]=half?0x8001:0x80;
        rejects([&]{g.step();},"Stop requests fail explicitly for byte and halfword writes");require(!g.debugRegisters().halted,"Unsupported Stop is not silently treated as Halt");
    }
    g.reset();g.debugWrite(0x04000300,0xfe);require(!g.inspect(0x04000300),"POSTFLG exposes its documented boot flag bit only");
}
void gbaUndefinedChecks() {
    for (bool thumb:{false,true}) for (unsigned vector=0;vector<3;++vector) {
        GBA g;g.load(gbaROM());
        if (thumb) thumbProgram(g,{uint16_t(vector==0?0xde00:vector==1?0xbe00:0xe800),0x242a});
        else armProgram(g,{vector==0?0xe7f000f0u:vector==1?0xee100f10u:0xec100000u,0xe3a0402a});
        auto status=g.debugRegisters().cpsr|0xa0000040;g.debugRegisters().cpsr=status;
        auto sp=g.debugRegisters().r[13];g.debugRegisters().banked[5][0]=0x03007000;
        require(g.step()==3 && g.debugRegisters().r[15]==4 && g.debugRegisters().r[14]==0x03000000+(thumb?2:4),"Architecturally undefined instruction enters vector with correct ARM/Thumb link and exception clocks");
        require(g.debugRegisters().spsr[5]==status && g.debugRegisters().cpsr==((status&~63u)|0x9b) && g.debugRegisters().r[13]==0x03007000,"Undefined exception saves flags/state and selects UND stack while masking IRQ");
        auto saved=g.save();rejects([&]{g.step();},"Missing independent undefined-vector firmware handler fails explicitly");
        g.restore(saved);require(g.save()==saved,"Undefined exception context is replayable");
        // Substitute an original one-instruction handler in RAM to exercise the
        // CPU's real MOVS exception return; no Nintendo BIOS is supplied.
        for (unsigned b=0;b<4;++b) g.debugWrite(0x03000200+b,0xe1b0f00e>>(b*8));
        g.debugRegisters().r[15]=0x03000200;g.step();
        require(g.debugRegisters().cpsr==status && g.debugRegisters().r[13]==sp && g.debugRegisters().r[15]==0x03000000+(thumb?2:4),"Undefined handler can return to exact caller state and next instruction");
        g.step();require(g.debugRegisters().r[4]==42,"Caller continues after undefined exception return");
    }
    GBA g;g.load(gbaROM());armProgram(g,{0x07f000f0});g.step();
    require(g.debugRegisters().r[15]==0x03000004 && (g.debugRegisters().cpsr&31)==0x1f,"Failed ARM condition suppresses undefined exception");
}
void gbaNestedWaitChecks() {
    auto put=[](GBA& g,uint32_t address,uint32_t value) {for (unsigned n=0;n<4;++n) g.debugWrite(address+n,value>>(n*8));};
    for (bool thumb:{false,true}) {
        GBA g;g.load(gbaROM());
        if (thumb) thumbProgram(g,{0xdf04,0x242a});else armProgram(g,{0xef040000,0xe3a0402a});
        g.debugRegisters().banked[2][0]=0x03007fa0;g.debugRegisters().banked[3][0]=0x03007fe0;
        g.debugRegisters().cpsr|=0xa0000080;auto status=g.debugRegisters().cpsr;
        g.debugRegisters().r[0]=1;g.debugRegisters().r[1]=0x1000;auto sp=g.debugRegisters().r[13];
        // Original reentrant IRQ callback: save SPSR/LR on IRQ stack, acknowledge
        // hardware, OR BIOS flags, then wait for a timer from the keypad handler.
        const uint32_t handler[]={
            0xe92d4070,0xe14f4000,0xe92d0010,0xe59f503c,0xe1d560b0,0xe1c560b0,
            0xe59f5034,0xe1d500b0,0xe1800006,0xe1c500b0,0xe3160a01,0x0a000003,
            0xe3a00001,0xe3a01008,0xef040000,0xe3a07077,
            0xe8bd0010,0xe169f004,0xe8bd4070,0xe12fff1e,0x04000202,0x03007ff8
        };
        for (unsigned n=0;n<std::size(handler);++n) put(g,0x03000100+4*n,handler[n]);
        put(g,0x03007ffc,0x03000100);g.debugWrite(0x04000200,8);g.debugWrite(0x04000201,0x10);
        g.debugWrite(0x04000132,1);g.debugWrite(0x04000133,0x40);
        g.step();require(g.debugRegisters().r[15]==0x140 && (g.debugRegisters().cpsr&0xbf)==0x1f && g.save()[205]==1,"Wait suspends ARM/Thumb caller in interruptible ARM system firmware context");
        g.setKeys(1);
        for (unsigned n=0;n<80 && !(g.debugRegisters().halted && g.save()[205]==2);++n) g.step();
        require(g.debugRegisters().halted && g.save()[205]==2 && g.debugRead32(0x03007ff8)==0x1000,"IRQ callback starts nested wait without consuming outer completion flag");
        require(g.debugRegisters().banked[3][0]==0x03007fc0 && g.debugRead32(0x03007fdc)==0x03000000+(thumb?2:4),"Nested SWI retains independent SVC frames below outer frame");
        auto nested=g.save();g.debugWrite(0x04000100,0xf0);g.debugWrite(0x04000101,0xff);g.debugWrite(0x04000102,0xc0);
        auto finish=[&] {
            for (unsigned n=0;n<200 && g.save()[205]!=0;++n) {
                g.step();
                if (g.debugRegisters().r[15]==0x18) g.debugWrite(0x04000102,0); // one timer IRQ
            }
        };
        finish();auto complete=g.save();
        require(g.debugRegisters().r[4]==42 && g.debugRegisters().r[7]==0x77 && complete[205]==0,"Timer IRQ releases inner wait, callback returns, then outer wait resumes");
        require(g.debugRegisters().cpsr==(thumb?status&0x3fffffffu:status) && g.debugRegisters().r[13]==sp && g.debugRegisters().banked[2][0]==0x03007fa0 && !g.debugRead32(0x03007ff8),"Nested waits restore caller mode/masks, both stacks and consume only matching BIOS bits");
        g.restore(nested);g.debugWrite(0x04000100,0xf0);g.debugWrite(0x04000101,0xff);g.debugWrite(0x04000102,0xc0);finish();
        require(g.save()==complete,"Nested wait snapshot replays real timer IRQ and both returns deterministically");
    }
    GBA g;g.load(gbaROM());armProgram(g,{0xef040000,0xe3a0402a});g.debugRegisters().r[0]=1;g.debugRegisters().r[1]=1;g.step();
    auto pending=g.save();auto payload=std::vector<uint8_t>(pending.begin(),pending.end()-22);
    // Construct the old single-wait layout with its caller PC/mode suspension.
    auto number=[&](unsigned offset,uint32_t value) {for (unsigned n=0;n<4;++n) payload[offset+n]=value>>(n*8);};
    number(80,0x03000004);number(84,0x1f);payload[3]=0x33;
    payload.erase(payload.begin()+201,payload.begin()+228);
    const uint8_t oldWait[]={1,1,0,0x1f,0,0,0,4,0,0,3};payload.insert(payload.begin()+201,std::begin(oldWait),std::end(oldWait));
    auto legacy=protectState(payload);g.restore(legacy);put(g,0x03007ff8,1);g.step();
    require(g.debugRegisters().r[4]==42 && g.save()[205]==0,"Version-three pending waits migrate and return to the legacy caller PC");
    g.restore(pending);auto before=g.save();
    auto corrupt=[&](unsigned offset,uint8_t value) {auto bad=std::vector<uint8_t>(before.begin(),before.end()-4);bad[offset]=value;rejects([&]{g.restore(protectState(bad));},"Malformed nested-wait state is rejected");require(g.save()==before,"Rejected nested-wait state is transactional");};
    corrupt(205,17);corrupt(208,0x15);corrupt(216,0x9f);corrupt(220,0x41);corrupt(224,1);
    g.reset();require(g.save()[205]==0,"Reset clears every suspended wait");
}
void gbaSVCFrameChecks() {
    auto put=[](GBA& g,uint32_t a,uint32_t v) {for (unsigned n=0;n<4;++n) g.debugWrite(a+n,v>>(n*8));};
    for (bool thumb:{false,true}) for (unsigned mode:{0x10u,0x1fu,0x11u,0x12u,0x13u}) {
        auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());
        if (thumb) thumbProgram(g,{0xdf08});else armProgram(g,{0xef080000});
        auto& r=g.debugRegisters();r.cpsr=0xa0000040|mode|(thumb?32:0);
        r.r[0]=81;r.r[11]=0x11111111;r.r[12]=0x12121212;r.r[14]=0x08001234;
        r.userHigh[3]=0xbbbbbbbb;r.userHigh[4]=0xcccccccc;
        r.banked[3][0]=0x0203fff0;r.banked[0]={0x03007e00,0x08003456};
        if (mode==0x13) r.r[13]=0x0203fff0;
        auto status=r.cpsr,sp=r.r[13];g.step();
        for (unsigned n=0;n<1000 && r.r[15]<0x4000;++n) g.step();
        uint32_t frame=0x0203ffe0;
        require(g.debugRead32(frame)==status && g.debugRead32(frame+12)==0x03000000+(thumb?2:4),"SVC frame stores ARM/Thumb SPSR and exception link on relocated stack");
        require(g.debugRead32(frame+4)==(mode==0x11?0xbbbbbbbbu:0x11111111u) && g.debugRead32(frame+8)==(mode==0x11?0xccccccccu:0x12121212u),"SVC frame uses supervisor-visible r11/r12 even for FIQ caller");
        require(r.cpsr==status && r.r[0]==9 && r.r[11]==0x11111111 && r.r[12]==0x12121212 && r.r[13]==sp,"SVC epilogue restores caller registers, bank, stack and status");
        require(mode==0x13?r.r[14]==0x03000000+(thumb?2:4):r.r[14]==0x08001234,"SWI exception link only replaces supervisor LR");
    }
    auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());armProgram(g,{0xef040000,0xe3a0402a});
    g.debugRegisters().r[0]=1;g.debugRegisters().r[1]=1;g.debugRegisters().r[11]=0x11;g.step();
    require(g.debugRegisters().banked[3][0]==0x03007fd0 && g.debugRead32(0x03007fd0)==0x1f && g.debugRead32(0x03007fdc)==0x03000004,"Suspended wait retains live SVC frame and decremented stack");
    auto pending=g.save();
    put(g,0x03007fd4,0x12345678);put(g,0x03007ff8,1);g.step();
    require(g.debugRegisters().r[11]==0x12345678 && g.debugRegisters().banked[3][0]==0x03007fe0,"Wait return reads restored registers from actual frame memory");
    // Actual v4 wait payloads have no frame pointer and do not own a frame.
    auto legacy=std::vector<uint8_t>(pending.begin(),pending.end()-22);legacy[3]=0x34;
    legacy.erase(legacy.begin()+224,legacy.begin()+228);
    // Bank three SP is serialized at offset 153.
    for (unsigned n=0;n<4;++n) legacy[153+n]=0x03007fe0u>>(n*8);
    g.restore(protectState(legacy));put(g,0x03007ff8,1);g.step();
    require(g.debugRegisters().r[4]==42 && g.debugRegisters().banked[3][0]==0x03007fe0,"Version-four pending wait completes without popping a nonexistent SVC frame");
}
void gbaInterruptibleCopyChecks() {
    auto put=[](GBA& g,uint32_t a,uint32_t v) {for (unsigned n=0;n<4;++n) g.debugWrite(a+n,v>>(n*8));};
    for (bool fast:{false,true}) for (bool fill:{false,true}) for (bool thumb:{false,true}) {
        auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());
        if (thumb) thumbProgram(g,{uint16_t(fast?0xdf0c:0xdf0b),0x242a});else armProgram(g,{fast?0xef0c0000u:0xef0b0000u,0xe3a0402a});
        auto& r=g.debugRegisters();r.cpsr|=0xa0000040;
        for (unsigned n=0;n<256;++n) {g.debugWrite(0x02000000+n,n^0x5a);g.debugWrite(0x02001000+n,0xcc);}
        r.r[0]=0x02000000;r.r[1]=0x02001000;r.r[2]=64|(1u<<26)|(fill?1u<<24:0);
        for (unsigned n=4;n<13;++n) r.r[n]=0x55550000+n;
        r.r[14]=0x08001234;auto status=r.cpsr,sp=r.r[13],control=r.r[2];g.step();
        require(r.r[15]<0x4000 && (r.cpsr&0xbf)==0x1f && g.debugRead32(0x02001000)==0xcccccccc,"Copy SWI suspends caller before destination writes");
        for (unsigned n=0;n<100 && g.inspect(0x02001000)==0xcc;++n) g.step();
        require(g.inspect(0x02001000)==0x5a && g.inspect(0x020010fc)==0xcc,"Copy worker exposes partial progress before completion");
        // IRQ callback acknowledges keypad, records partial destination and runs
        // a nested Sqrt SWI. Normal IRQ wrapper preserves copy scratch registers.
        const uint32_t handler[]={0xe59f001c,0xe3a01a01,0xe1c010b0,0xe59f0014,0xe5901000,0xe5801100,0xe3a00051,0xef080000,0xe12fff1e,0x04000202,0x020010fc};
        for (unsigned n=0;n<std::size(handler);++n) put(g,0x03000200+n*4,handler[n]);
        put(g,0x03007ffc,0x03000200);g.debugWrite(0x04000201,0x10);g.debugWrite(0x04000208,1);
        g.debugWrite(0x04000132,1);g.debugWrite(0x04000133,0x40);g.setKeys(1);g.step();
        require(r.r[15]==0x18 && (r.cpsr&31)==0x12,"IRQ preempts an in-flight BIOS copy");
        auto interrupted=g.save();
        auto finish=[&] {for (unsigned n=0;n<2000 && r.r[15]!=0x03000000+(thumb?2:4);++n) g.step();};
        finish();auto after=g.save();
        require(g.debugRead32(0x020011fc)==0xcccccccc,"IRQ callback observes unfinished copy and nested SWI returns to worker");
        require(r.cpsr==status && r.r[13]==sp && r.r[14]==0x08001234 && r.r[2]==control && r.banked[3][0]==0x03007fe0 && r.banked[2][0]==0x03007fa0,"Interrupted copy restores caller flags, mode, stacks, LR and control");
        for (unsigned n=4;n<13;++n) require(r.r[n]==0x55550000+n,"Interrupted copy preserves callee-saved registers");
        for (unsigned n=0;n<256;++n) require(g.inspect(0x02001000+n)==uint8_t((fill?n%4:n)^0x5a),"Interrupted copy/fill completes exact output");
        g.restore(interrupted);finish();require(g.save()==after,"Mid-copy IRQ snapshot replays nested SWI, worker and epilogue exactly");
        g.step();require(r.r[4]==42,"Copy caller continues in original ARM/Thumb state");
    }
    // A timer overflow during ordinary halfword copy must dispatch without an
    // injected IF flag, while the caller's I mask still defers IRQ entry.
    for (bool masked:{false,true}) {
        auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());armProgram(g,{0xef0b0000,0xe1a00000});
        auto& r=g.debugRegisters();if (masked) r.cpsr|=0x80;
        r.r[0]=0x02000000;r.r[1]=0x05000000;r.r[2]=64;
        for (unsigned n=0;n<128;++n) g.debugWrite(0x02000000+n,n^0x6a);
        const uint32_t handler[]={0xe59f0008,0xe3a01008,0xe1c010b0,0xe12fff1e,0x04000202};
        for (unsigned n=0;n<std::size(handler);++n) put(g,0x03000200+n*4,handler[n]);
        put(g,0x03007ffc,0x03000200);g.debugWrite(0x04000200,8);g.debugWrite(0x04000208,1);
        g.step();g.debugWrite(0x04000100,0xc0);g.debugWrite(0x04000101,0xff);g.debugWrite(0x04000102,0xc0);
        bool taken=false;
        for (unsigned n=0;n<1000 && r.r[15]!=0x03000004;++n) {
            g.step();if (r.r[15]==0x18) {taken=true;g.debugWrite(0x04000102,0);}
        }
        require(taken==!masked && r.r[15]==0x03000004,"Timer overflow preempts halfword firmware copy unless caller masks IRQs");
        if (masked) require((g.inspect(0x04000202)&8) && (r.cpsr&0x80),"Masked copy leaves timer request pending and restores I mask");
        for (unsigned n=0;n<128;++n) require(g.inspect(0x05000000+n)==uint8_t(n^0x6a),"Interruptible halfword copy retains native palette writes");
    }
    // Fast copy loads a whole eight-word block before writing overlapping RAM.
    auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());armProgram(g,{0xef0c0000});
    for (unsigned n=0;n<36;++n) g.debugWrite(0x02000000+n,n);
    g.debugRegisters().r[0]=0x02000000;g.debugRegisters().r[1]=0x02000004;g.debugRegisters().r[2]=8;g.step();
    for (unsigned n=0;n<100 && g.debugRegisters().r[15]<0x4000;++n) g.step();
    for (unsigned n=0;n<32;++n) require(g.inspect(0x02000004+n)==n,"CpuFastSet overlap retains block-load/store semantics");
}

void gbaTransferEdgeChecks() {
    auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());
    auto put=[&](uint32_t a,uint32_t v) {for (unsigned n=0;n<4;++n) g.debugWrite(a+n,v>>(8*n));};
    for (bool thumb:{false,true}) {
        if (thumb) thumbProgram(g,{0x8801});else armProgram(g,{0xe1d010b0});
        put(0x02000000,0x1234abcd);g.debugRegisters().r[0]=0x02000001;g.step();
        require(g.debugRegisters().r[1]==0xcd0000ab,"Odd-address LDRH rotates the zero-extended halfword through all 32 bits");
        if (thumb) thumbProgram(g,{0x5e81});else armProgram(g,{0xe1d010f0});
        g.debugRegisters().r[0]=0x02000001;g.debugRegisters().r[2]=0;g.step();
        require(g.debugRegisters().r[1]==0xffffffab,"Odd-address LDRSH reads and sign extends a byte");
        if (thumb) thumbProgram(g,{0xc806});else armProgram(g,{0xe8b00006});
        g.debugRegisters().r[0]=0x02000001;put(0x02000004,0x56789abc);g.step();
        require(g.debugRegisters().r[1]==0x1234abcd && g.debugRegisters().r[2]==0x56789abc && g.debugRegisters().r[0]==0x02000009,"Unaligned block load aligns each word without rotating and retains base low bits");
        for (bool first:{false,true}) {
            if (thumb) thumbProgram(g,{uint16_t(first?0xc103:0xc003)});else armProgram(g,{first?0xe8a10003u:0xe8a00003u});
            // r0 first: old base; r1 later: updated base.
            auto base=first?1:0;g.debugRegisters().r[base]=0x02000100;g.debugRegisters().r[1-base]=0x42;g.step();
            require(g.debugRead32(0x02000100+base*4)==(base?0x02000108u:0x02000100u),"Block store writes old first-listed base and updated later-listed base");
        }
        if (thumb) thumbProgram(g,{0xc000});else armProgram(g,{0xe8a00000});
        g.debugRegisters().r[0]=0x02000200;g.step();
        require(g.debugRead32(0x02000200)==0x03000000+(thumb?4:12) && g.debugRegisters().r[0]==0x02000240,"Empty ARM7 block store transfers PC and advances base by 64");
        if (thumb) thumbProgram(g,{0xc800});else armProgram(g,{0xe8b00000});
        g.debugRegisters().r[0]=0x02000200;put(0x02000200,0x03000100);g.step();
        require(g.debugRegisters().r[15]==0x03000100 && g.debugRegisters().r[0]==0x02000240,"Empty ARM7 block load loads PC and advances base by 64");
    }
    armProgram(g,{0xe08f0211});g.debugRegisters().r[1]=3;g.debugRegisters().r[2]=1;g.step();
    require(g.debugRegisters().r[0]==0x03000012,"Register-shift ALU reads PC plus 12 as its first operand");
    for (auto opcode:{0xe12fff30u,0xe1200070u,0xe16f0f10u,0xe1000050u,0xe1c010d0u,0xe1c010f0u}) {
        armProgram(g,{opcode});g.step();require(g.debugRegisters().r[15]==4 && (g.debugRegisters().cpsr&31)==0x1b,"Later-architecture ARM opcodes enter the undefined exception on ARMv4T");
    }
    thumbProgram(g,{0xb400});auto stack=g.debugRegisters().r[13];g.step();
    require(g.debugRegisters().r[13]==stack-64 && g.debugRead32(stack-64)==0x03000004,"Empty Thumb PUSH stores PC and allocates 64 bytes");
    thumbProgram(g,{0xbc00});stack=g.debugRegisters().r[13];put(stack,0x03000101);g.step();
    require(g.debugRegisters().r[13]==stack+64 && g.debugRegisters().r[15]==0x03000100,"Empty Thumb POP loads PC and advances SP by 64 bytes");
    thumbProgram(g,{0x4780});g.step();
    require(g.debugRegisters().r[15]==4 && (g.debugRegisters().cpsr&31)==0x1b,"Thumb BLX-register encoding traps as undefined on ARMv4T");
}

void gbaPipelineIOChecks() {
    auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());
    auto put=[&](uint32_t a,uint32_t v) {for (unsigned n=0;n<4;++n) g.debugWrite(a+n,v>>(8*n));};
    for (bool thumb:{false,true}) {
        if (thumb) thumbProgram(g,{0x8001,0x2201,0xe7fd});else armProgram(g,{0xe5801000,0xe3a02001,0xeafffffd});
        g.debugRegisters().r[0]=0x03000000+(thumb?2:4);g.debugRegisters().r[1]=thumb?0x2202:0xe3a02002;g.step();
        auto pending=g.save();g.step();require(g.debugRegisters().r[2]==1,"Self-modifying code executes the instruction already in the pipeline");
        g.step();g.step();require(g.debugRegisters().r[2]==2,"Branch refills pipeline and sees modified instruction memory");
        auto after=g.save();g.restore(pending);g.step();g.step();g.step();require(g.save()==after,"Snapshot preserves prefetched instructions even when their memory was overwritten");
        auto bad=std::vector<uint8_t>(after.begin(),after.end()-4);bad[bad.size()-2]=2;
        rejects([&]{g.restore(protectState(bad));},"Malformed pipeline validity is rejected");require(g.save()==after,"Rejected pipeline state leaves running machine unchanged");
    }
    armProgram(g,{0xe5801000,0xeaffffff,0xe3a02001});g.debugRegisters().r[0]=0x03000008;g.debugRegisters().r[1]=0xe3a02002;
    g.step();g.step();g.step();require(g.debugRegisters().r[2]==2,"Branch to the sequential next address still flushes prefetched code");
    for (uint32_t address:{0x00004000u,0x01000000u,0x04000400u,0x10000000u,0xfffffff0u}) {
        armProgram(g,{0xe5901000,0xe1a00000,0xe3a02077});g.debugRegisters().r[0]=address;g.step();
        require(g.debugRegisters().r[1]==0xe3a02077,"ARM unmapped load reads the opcode fetched at PC plus eight");
        armProgram(g,{0xe5d01000,0xe1a00000,0xe3a02077});g.debugRegisters().r[0]=address+1;g.step();
        require(g.debugRegisters().r[1]==0x20,"Open-bus byte read selects addressed byte lane");
    }
    for (uint32_t pc:{0x02001000u,0x03001000u,0x03001002u}) {
        g.reset();auto& r=g.debugRegisters();r.cpsr|=32;r.r[15]=pc;r.r[0]=0x10000000;
        const uint16_t code[]={0x6801,0x46c0,0x2277};
        for (unsigned n=0;n<3;++n) {g.debugWrite(pc+n*2,code[n]);g.debugWrite(pc+n*2+1,code[n]>>8);}
        g.step();auto expected=(pc>>24)==2?0x22772277u:pc&2?0x227746c0u:0x46c02277u;
        require(r.r[1]==expected,"Thumb instruction-bus latch respects 16-bit external and 32-bit internal fetch lanes");
    }
    // Legacy v5 has no pipeline trailer; it must refill at its saved PC.
    g.reset();armProgram(g,{0xe3a01001,0xe3a01002});g.step();auto current=g.save();
    auto legacy=std::vector<uint8_t>(current.begin(),current.end()-22);legacy[3]=0x35;g.restore(protectState(legacy));g.step();
    require(g.debugRegisters().r[1]==2,"Version-five snapshots migrate by refilling instruction pipeline at saved PC");
    g.reset();armProgram(g,{0xe1a00000,0xe1a00000,0xe1a00000,0xe1a00000});
    g.debugWrite(0x04000100,0xfc);g.debugWrite(0x04000101,0xff);g.debugWrite(0x04000102,0xc4);
    require((g.debugRead32(0x04000100)&0xffffff)==0xc0fffc,"Byte timer enable latches reload and ignores cascade on timer zero");
    g.step();g.debugWrite(0x04000100,0xe0);require((g.debugRead32(0x04000100)&0xffff)==0xfffd,"Byte reload write while running preserves current timer counter");
    g.step();g.step();g.step();require((g.debugRead32(0x04000100)&0xffff)==0xffe0 && (g.inspect(0x04000202)&8),"Timer overflow uses updated hidden reload and requests IRQ");
    g.reset();put(0x02000000,0x1234abcd);put(0x040000b0,0x02000000);put(0x040000b4,0x03000100);
    g.debugWrite(0x040000b8,2);g.debugWrite(0x040000bb,0xc0);
    require(g.debugRead32(0x03000100)==0x1234abcd && !(g.inspect(0x040000bb)&0x80) && (g.inspect(0x04000203)&1),"High-byte DMA enable triggers immediate transfer, clears enable and requests IRQ");
    g.debugWrite(0x04000200,0xff);g.debugWrite(0x04000201,0xff);put(0x04000208,0xffffffff);
    require((g.debugRead32(0x04000200)&0xffff)==0x3fff && (g.debugRead32(0x04000208)&0xffff)==1,"IE and IME reserved bits are masked for byte and word writes");
    g.debugWrite(0x04000004,0xff);require((g.inspect(0x04000004)&7)==4,"DISPSTAT byte writes preserve read-only status flags");
    for (unsigned mode:{0u,3u,4u,5u}) {
        g.debugWrite(0x04000000,0x80|mode);g.debugWrite(0x06012000,0x5a);
        require(g.debugRead32(0x06012000)==(mode?0x5a5au:0u),"Bitmap-mode byte writes include framebuffer VRAM above 64 KiB");
        g.debugWrite(0x06014000,0xa5);require(g.debugRead32(0x06014000)==0,"Bitmap OBJ VRAM still ignores byte writes");
    }
    rejects([&]{g.inspect(0x0f000000);},"Mirrored unimplemented cartridge-save space faults explicitly");
    g.reset();g.debugRegisters().r[15]=0x03001000;g.debugWrite(0x04000004,0x10);
    put(0x02000000,0x1234);put(0x040000b0,0x02000000);put(0x040000b4,0x03000100);
    g.debugWrite(0x040000b8,1);g.debugWrite(0x040000bb,0xa0);
    for (unsigned n=0;n<1005;++n) g.step();
    require(!(g.inspect(0x04000004)&2) && !g.debugRead32(0x03000100),"HBlank status and DMA do not begin at pixel 240's cycle 960");
    g.step();require((g.inspect(0x04000004)&2) && (g.inspect(0x04000202)&2) && g.debugRead32(0x03000100)==0x1234,"HBlank status, IRQ and DMA begin at scanline cycle 1006");
    g.reset();g.debugWrite(0x04000005,1);require(!(g.inspect(0x04000004)&4),"Changing VCOUNT compare clears a stale equality flag immediately");
    g.debugWrite(0x04000004,0x20);g.debugWrite(0x04000005,0);
    require((g.inspect(0x04000004)&4) && (g.inspect(0x04000202)&4),"Matching VCOUNT compare updates flag and requests enabled IRQ");
}

void gbaArithmeticIRQChecks() {
    auto put=[](GBA& g,uint32_t a,uint32_t v) {for (unsigned n=0;n<4;++n) g.debugWrite(a+n,v>>(n*8));};
    for (unsigned service:{6u,7u,8u}) for (bool thumb:{false,true}) for (bool masked:{false,true}) {
        auto core=std::make_unique<GBA>();auto& g=*core;g.load(gbaROM());
        if (thumb) thumbProgram(g,{uint16_t(0xdf00|service),0x242a});else armProgram(g,{0xef000000u|(service<<16),0xe3a0402a});
        auto& r=g.debugRegisters();r.cpsr|=0xa0000040|(masked?0x80:0);auto status=r.cpsr,sp=r.r[13];
        r.r[0]=service==7?7u:service==8?0xffffffffu:uint32_t(-12345);r.r[1]=service==7?uint32_t(-12345):7u;r.r[2]=0x12345678;r.r[14]=0x08001234;
        for (unsigned n=4;n<=12;++n) r.r[n]=0xcccc0000+n;
        // The IRQ itself calls another arithmetic worker. Save caller-volatile
        // registers via the normal IRQ wrapper and resume each worker in turn.
        const uint32_t handler[]={0xe59f0010,0xe3a01008,0xe1c010b0,0xe3a00051,0xef080000,0xe12fff1e,0x04000202};
        for (unsigned n=0;n<std::size(handler);++n) put(g,0x03000200+n*4,handler[n]);
        put(g,0x03007ffc,0x03000200);g.debugWrite(0x04000200,8);g.debugWrite(0x04000208,1);
        g.step();for (unsigned n=0;n<5;++n) g.step();
        require(r.r[15]<0x4000 && r.r[13]<sp,"Arithmetic SWI executes interruptible firmware with a live user stack frame");
        auto pending=g.save();
        auto finish=[&] {
            g.debugWrite(0x04000100,0xf0);g.debugWrite(0x04000101,0xff);g.debugWrite(0x04000102,0xc0);bool taken=false;
            for (unsigned n=0;n<2000 && r.r[15]!=0x03000000+(thumb?2:4);++n) {
                g.step();if (r.r[15]==0x18) {taken=true;g.debugWrite(0x04000102,0);}
            }
            return taken;
        };
        require(finish()==!masked,"Arithmetic worker allows timer IRQ and nested Sqrt unless caller I mask is set");
        require(r.r[0]==(service==8?65535u:uint32_t(-1763)) && (service==8 || (r.r[1]==uint32_t(-4) && r.r[3]==1763)),"Interrupted division/remainder/absolute quotient and sqrt results are correct");
        require(r.cpsr==status && r.r[13]==sp && r.r[14]==0x08001234 && r.r[2]==0x12345678 && r.banked[3][0]==0x03007fe0 && r.banked[2][0]==0x03007fa0,"Arithmetic return restores caller masks, state, stacks, LR and r2");
        for (unsigned n=4;n<=12;++n) require(r.r[n]==0xcccc0000+n,"Nested arithmetic preserves callee-saved registers");
        auto after=g.save();g.restore(pending);finish();require(g.save()==after,"Mid-arithmetic pipeline snapshot replays timer IRQ and nested SWI deterministically");
    }
}

void gbaBIOSMemoryChecks() {
    GBA g;g.load(gbaROM());
    require(g.debugRead32(0)==0xe129f000 && g.debugRead32(0x100)==0xe129f000,"Outside BIOS, protected reads use startup latch rather than firmware contents");
    require(g.inspect(1)==0xf0 && g.inspect(2)==0x29 && g.inspect(3)==0xe1 && g.debugRead32(1)==0x00e129f0,"Protected BIOS byte lanes and unaligned word rotation");
    g.debugWrite(0,0);require(g.debugRead32(0)==0xe129f000,"BIOS writes are ignored");
    armProgram(g,{0xef080000,0xe5901000});g.debugRegisters().r[0]=4;g.step();
    for (unsigned n=0;n<1000 && g.debugRegisters().r[15]<0x4000;++n) g.step();
    require(g.debugRead32(0x18)==0xe3a02004,"SWI return updates protected BIOS latch");
    auto saved=g.save();g.reset();g.restore(saved);require(g.debugRead32(0)==0xe3a02004,"BIOS latch survives state replay");
    // The CPU's access is protected as well as the public inspection path.
    g.debugRegisters().r[0]=0;g.step();require(g.debugRegisters().r[1]==0xe3a02004,"ARM LDR cannot expose independent BIOS code outside BIOS");
    g.debugRegisters().r[15]=0x100;require(g.debugRead32(0x18)==0xea0000f8 && g.debugRead32(0x11c)==0x03007ffc,"Code executing within BIOS can read independent firmware and literals");
    // DMA does not gain BIOS read permission from a BIOS-resident CPU PC.
    // Point the independent wrapper's STMFD at DMA0 registers. The control
    // halfword starts DMA while the CPU PC is still inside BIOS.
    g.debugRegisters().r[15]=0x100;g.debugRegisters().r[13]=0x040000c8;
    g.debugRegisters().r[0]=0x18;g.debugRegisters().r[1]=0x02001000;g.debugRegisters().r[2]=0x84000001;
    g.step();require(g.debugRead32(0x02001000)==0xe1a0e00f,"DMA BIOS source remains protected even while CPU executes inside BIOS");
}
void statesAndDemos(const std::string& root) {
    {
        GBA boot;boot.load(file(root+"/crispy-startup.gba"));
        for (unsigned n=0;n<4;++n) boot.runFrame();
        require(boot.debugRead32(0x02000000)>=3,"Original startup ROM handles successive hardware VBlank callbacks through BIOS IRQ wrapper");
        require(boot.debugRegisters().halted,"Startup ROM sleeps between VBlanks using BIOS wait");
        for (auto pixel:boot.pixels()) require(pixel==colour555(0x03e0),"Startup ROM displays image filled by BIOS CpuSet");
        auto saved=boot.save();boot.runFrame();auto expected=boot.save();boot.restore(saved);boot.runFrame();
        require(boot.save()==expected,"Startup mode/BIOS/VBlank execution replays deterministically");
    }
    for (auto system:{System::gb,System::gbc,System::gba}) {
        auto core=makeCore(system);auto rom=file(root+"/crispy-demo."+(system==System::gb?"gb":system==System::gbc?"gbc":"gba"));core->load(rom);
        for (unsigned n=0;n<3;++n) core->runFrame();
        auto cap=core->capabilities();require(core->pixels().size()==cap.width*cap.height,"Frame has native console dimensions");require(core->statistics().frames>=2,"Demo reaches successive VBlanks");
        if (system==System::gba) {
            for (unsigned index:{0u,1u,239u,240u,10000u,32767u,38399u}) require(core->pixels()[index]==colour555(index&0x7fff),"GBA homebrew executed its ARM framebuffer gradient");
        } else {
            auto* gb=dynamic_cast<GameBoy*>(core.get());require(gb->serialOutput().find("READY")!=std::string::npos,"GB/GBC homebrew serial handshake");
            require(core->pixels()[0]!=core->pixels()[2],"GB/GBC demo has tile pattern, not a fabricated static frame");
            if (system==System::gbc) require(core->pixels()[2]==colour555(0x03e0) || core->pixels()[2]==colour555(0x001f),"CGB hardware palette renders colour");
        }
        auto saved=core->save();core->runFrame();auto expected=core->save();core->restore(saved);core->runFrame();require(core->save()==expected,"Save-state replay is byte-deterministic");
        auto before=core->save();auto corrupt=before;corrupt[corrupt.size()/2]^=128;rejects([&]{core->restore(corrupt);},"Checksum rejects bit-corrupted state");require(core->save()==before,"Corrupt state leaves live core untouched");
        auto clockPayload=std::vector<uint8_t>(before.begin(),before.end()-4);auto clockOffset=system==System::gba?12:13;
        for (unsigned i=0;i<8;++i) clockPayload[clockOffset+i]=0xff;
        auto badClock=protectState(std::move(clockPayload));rejects([&]{core->restore(badClock);},"Implausible future state clock rejected");
        auto truncated=before;truncated.resize(truncated.size()/2);rejects([&]{core->restore(truncated);},"Truncated states rejected");require(core->save()==before,"Failed state load leaves live core untouched");
        auto different=rom;different.back()^=1;auto other=makeCore(system);other->load(different);rejects([&]{other->restore(saved);},"States from another ROM rejected");
        auto old=core->statistics().cycles;core->reset();require(core->statistics().cycles==0 && old>0,"Reset reinitialises clock");
    }
}
}
int main(int argc,char** argv) {
    try {
        aluChecks();instructionChecks();busAndClockChecks();gbaChecks();armModeChecks();gbaServiceChecks();gbaDecompressionChecks();gbaIRQChecks();gbaWaitResetChecks();gbaResetIOChecks();gbaUndefinedChecks();gbaNestedWaitChecks();gbaArithmeticIRQChecks();gbaPipelineIOChecks();gbaTransferEdgeChecks();gbaSVCFrameChecks();gbaInterruptibleCopyChecks();gbaBIOSMemoryChecks();
        if (argc>1) statesAndDemos(argv[1]);
        std::cout<<"PASS: "<<checks<<" checks; exhaustive GB ALU, CPU/CB timing, interrupt/HALT, bus/mapper/timers/DMA, CGB banking/speed, ARM/Thumb, independent GB/GBC/GBA demo execution and transactional deterministic states\n";
    } catch (const std::exception& e) {std::cerr<<"FAIL after "<<checks<<" checks: "<<e.what()<<"\n";return 1;}
}
