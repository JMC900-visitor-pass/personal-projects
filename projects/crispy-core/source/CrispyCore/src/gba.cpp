#include "crispy/gba.hpp"
#include <algorithm>
#include <bit>
#include <iomanip>
#include <sstream>
#include <stdexcept>
namespace crispy {
#include "gba_copy_firmware.hpp"
#include "gba_arithmetic_firmware.hpp"
namespace { uint32_t rolror(uint32_t v,unsigned amount) { return std::rotr(v,int(amount&31)); } }
void GBA::load(std::span<const uint8_t> bytes) {
    if (bytes.size()<0xc0 || bytes.size()>32*1024*1024 || bytes[0xb2]!=0x96) throw std::runtime_error("GBA ROM has no supported cartridge header");
    rom_.assign(bytes.begin(),bytes.end());reset();
}
void GBA::reset() {
    ewram_.fill(0);iwram_.fill(0);io_.fill(0);palette_.fill(0);vram_.fill(0);oam_.fill(0);pixels_.fill(0xffffffff);
    cpu_=ARMRegisters{};cpu_.r[13]=0x03007f00;cpu_.r[15]=0x08000000;cpu_.banked[2][0]=0x03007fa0;cpu_.banked[3][0]=0x03007fe0;
    stats_={};frameDeadline_=0;lineCycle_=line_=0;timerReload_.fill(0);timerPhase_.fill(0);dmaBusy_=false;biosWaits_.clear();biosLatch_=0xe129f000;
    pipeline_={};pipelineAddress_=openBus_=0;pipelineValid_=pipelineThumb_=false;
    io16(0x130,0x3ff);io16(0x000,0x80);io16(4,4);io_[0x300]=1; // post-boot entry, no logo firmware
    detectSave();
}
std::string GBA::title() const { if (rom_.size()<0xac) return "Game Boy Advance";auto start=rom_.begin()+0xa0,end=rom_.begin()+0xac;return std::string(start,std::find(start,end,0)); }
void GBA::restoreBattery(std::span<const uint8_t> data) {
    if (saveType_==SaveType::none) { if (!data.empty()) throw std::runtime_error("GBA cartridge has no battery save chip"); return; }
    if (saveType_==SaveType::eeprom) throw std::runtime_error("GBA EEPROM save hardware is not supported in this prototype");
    if (data.size()>saveSize_) throw std::runtime_error("Battery data is larger than this cartridge's save chip");
    battery_.assign(saveSize_,0xff); // start erased, then overlay the checkpoint
    std::copy(data.begin(),data.end(),battery_.begin());
}
// Independently assembled compatibility trampoline, not a Nintendo BIOS image.
// The CPU executes the wrapper normally, including its IRQ-bank stack accesses.
uint32_t GBA::firmwareWord(uint32_t address) {
    if (address>=copy_start && address<copy_start+sizeof(copyFirmware) && !(address&3)) return copyFirmware[(address-copy_start)/4];
    if (address>=divarm_start && address<divarm_start+sizeof(arithmeticFirmware) && !(address&3)) return arithmeticFirmware[(address-divarm_start)/4];
    switch (address) {
        case 0x18:return 0xea0000f8; // B 0x400; retain the old wrapper for saved PCs.
        case 0x100:return 0xe92d500f; // STMFD sp!, {r0-r3,r12,lr}
        case 0x104:return 0xe59f0010; // LDR r0, [pc,#0x10] -> callback address literal
        case 0x108:return 0xe1a0e00f; // MOV lr, pc -> return to 0x110
        case 0x10c:return 0xe590f000; // LDR pc, [r0]
        case 0x110:return 0xe8bd500f; // LDMFD sp!, {r0-r3,r12,lr}
        case 0x114:return 0xe25ef004; // SUBS pc, lr, #4
        case 0x11c:return 0x03007ffc;
        case 0x400:return 0xe92d500f; // STMFD sp!, {r0-r3,r12,lr}
        case 0x404:return 0xe3a00301; // MOV r0, #0x04000000 (callback ABI)
        case 0x408:return 0xe1a0e00f; // MOV lr, pc -> 0x410
        case 0x40c:return 0xe510f004; // LDR pc, [r0,#-4] (IWRAM mirror)
        case 0x410:return 0xe8bd500f; // LDMFD sp!, {r0-r3,r12,lr}
        case 0x414:return 0xe25ef004; // SUBS pc, lr, #4
        default:return 0;
    }
}
bool GBA::firmwareInstruction(uint32_t address) {
    return address==0x18 || (address>=0x100 && address<=0x114 && !(address&3)) ||
        (address>=copy_start && address<copy_start+sizeof(copyFirmware) && !(address&3)) ||
        (address>=0x400 && address<=0x414 && !(address&3)) ||
        (address>=divarm_start && address<divarm_start+sizeof(arithmeticFirmware) && !(address&3));
}
int GBA::ioReadMask(unsigned offset) {
    // Negative means the port does not drive the data bus. Zero is a
    // readable, hard-wired zero (not the same as an open-bus port).
    if (offset>=0x10 && offset<=0x46) return -1;
    if (offset>=0x90 && offset<=0x9e) return 0xffff;
    if (offset>=0xb0 && offset<=0xde) {
        auto relative=(offset-0xb0)%12;
        return relative==8?0:relative==10?(offset==0xde?0xffe0:0xf7e0):-1;
    }
    if (offset>=0x100 && offset<=0x10e) return offset&2?(offset==0x102?0xc3:0xc7):0xffff;
    if (offset>=0x120 && offset<=0x12a) return 0xffff; // serial mode details remain provisional
    switch (offset) {
        case 0:case 0xc:case 0xe:return 0xffff;
        case 2:return 1;case 4:return 0xff3f;case 6:return 0xff;
        case 8:case 0xa:return 0xdfff;
        case 0x48:case 0x4a:return 0x3f3f;
        case 0x50:return 0x3fff;case 0x52:return 0x1f1f;
        case 0x60:return 0x7f;case 0x62:case 0x68:return 0xffc0;
        case 0x64:case 0x6c:case 0x74:return 0x4000;
        case 0x70:return 0xe0;case 0x72:return 0xe000;
        case 0x78:return 0xff00;case 0x7c:return 0x40ff;
        case 0x80:return 0xff77;case 0x82:return 0x770f;
        case 0x84:return 0x80;case 0x88:return 0xc3ff;
        case 0x66:case 0x6a:case 0x6e:case 0x76:case 0x7a:case 0x7e:case 0x86:case 0x8a:
        case 0x136:case 0x142:case 0x15a:case 0x206:case 0x20a:case 0x302:return 0;
        case 0x130:return 0x3ff;case 0x132:return 0xc3ff;
        case 0x134:return 0xffff;case 0x140:return 0x47;
        case 0x150:case 0x152:case 0x154:case 0x156:return 0xffff;
        case 0x158:return 0x3a;
        case 0x200:case 0x202:return 0x3fff;
        case 0x204:return 0x5fff;case 0x208:case 0x300:return 1;
        default:return -1;
    }
}
uint8_t GBA::read8(uint32_t a) const {
    switch(a>>24) {
        case 0:
            if (a>=0x4000) return uint8_t(openBus_>>((a&3)*8));
            return uint8_t((cpu_.r[15]<0x4000 && !dmaBusy_?firmwareWord(a&~3u):biosLatch_)>>((a&3)*8));
        case 0x02:return ewram_[a&0x3ffff];case 0x03:return iwram_[a&0x7fff];
        case 0x04: {
            auto mask=a<0x04000400?ioReadMask(a&0x3fe):-1;
            return mask<0?uint8_t(openBus_>>((a&3)*8)):uint8_t((io16(a&0x3fe)&mask)>>((a&1)*8));
        }
        case 0x05:return palette_[a&0x3ff];
        case 0x06: { unsigned offset=a&0x1ffff;if (offset>=0x18000) offset-=0x8000;return vram_[offset]; }
        case 0x07:return oam_[a&0x3ff];
        case 0x08:case 0x09:case 0x0a:case 0x0b:case 0x0c:case 0x0d: { auto offset=a&0x1ffffff;return offset<rom_.size()?rom_[offset]:uint8_t((a>>1)>>((a&1)*8)); }
        case 0x0e:case 0x0f: {
            if (saveType_==SaveType::none) throw std::runtime_error("GBA cartridge has no recognized SRAM or Flash save chip");
            if (saveType_==SaveType::eeprom) throw std::runtime_error("GBA EEPROM save hardware is not supported in this prototype");
            return readSave8(a);
        }
        default:return uint8_t(openBus_>>((a&3)*8));
    }
}
uint16_t GBA::read16(uint32_t a) const { a&=~1u;return read8(a)|uint16_t(read8(a+1))<<8; }
uint32_t GBA::read32(uint32_t a) const { unsigned shift=(a&3)*8;a&=~3u;return rolror(read16(a)|uint32_t(read16(a+2))<<16,shift); }
void GBA::write8(uint32_t a,uint8_t v) {
    switch(a>>24) {
        case 2:ewram_[a&0x3ffff]=v;break;case 3:iwram_[a&0x7fff]=v;break;
        case 4:
            if (a>=0x04000400) break;
            if (a==0x04000300) {io_[0x300]=v&1;break;}
            if (a==0x04000301) {
                if (v&0x80) throw std::runtime_error("GBA Stop power-down timing is not implemented yet");
                cpu_.halted=true;break;
            }
            if (a==0x04000130 || a==0x04000131 || a==0x04000006 || a==0x04000007) break;
            if (a==0x04000202 || a==0x04000203) { io_[a&0x3ff]&=~v;break; }
            {
                unsigned offset=(a&0x3ff)&~1u;
                if (offset==0 || offset==4 || (offset>=0x100 && offset<=0x10e) ||
                    offset==0x200 || offset==0x208 || (offset>=0xba && offset<=0xde && (offset-0xba)%12==0)) {
                    auto old=offset>=0x100 && offset<=0x10c && !(offset&2)?timerReload_[(offset-0x100)/4]:io16(offset);
                    auto value=uint16_t(a&1?(old&255)|(uint16_t(v)<<8):(old&0xff00)|v);
                    write16(0x04000000+offset,value);break;
                }
            }
            io_[a&0x3ff]=v;break;
        case 5: {auto offset=a&0x3fe;palette_[offset]=palette_[offset+1]=v;break;}
        case 6: {unsigned offset=a&0x1fffe;if (offset>=0x18000) offset-=0x8000;if (offset<((io16(0)&7)>=3?0x14000u:0x10000u)) vram_[offset]=vram_[offset+1]=v;break;}
        case 7:break; // OAM ignores byte writes
        case 0x0e:case 0x0f:
            if (saveType_==SaveType::none) throw std::runtime_error("GBA cartridge has no recognized SRAM or Flash save chip");
            if (saveType_==SaveType::eeprom) throw std::runtime_error("GBA EEPROM save hardware is not supported in this prototype");
            saveWrite8(a,v);break;
        default:break;
    }
}
void GBA::write16(uint32_t a,uint16_t v) {
    a&=~1u;
    if ((a>>24)==5) {palette_[a&0x3fe]=v;palette_[(a&0x3fe)+1]=v>>8;return;}
    if ((a>>24)==6) {unsigned offset=a&0x1fffe;if (offset>=0x18000) offset-=0x8000;vram_[offset]=v;vram_[offset+1]=v>>8;return;}
    if ((a>>24)==7) {oam_[a&0x3fe]=v;oam_[(a&0x3fe)+1]=v>>8;return;}
    if (a>=0x04000000 && a<0x04000400) {
        unsigned offset=a&0x3ff;
        if (offset==0) {io16(0,(v&~8u)|(io16(0)&8));return;}
        if (offset==0x200) {io16(offset,v&0x3fff);return;}
        if (offset==0x208) {io16(offset,v&1);return;}
        if (offset==0x300) {
            if (v&0x8000) throw std::runtime_error("GBA Stop power-down timing is not implemented yet");
            write8(a,v);write8(a+1,v>>8);return;
        }
        if (offset==0x202) {io16(offset,io16(offset)&~v);return;}
        if (offset==4) {
            auto previous=io16(4);auto match=line_==(v>>8);
            io16(4,(v&0xff38)|(previous&3)|(match?4:0));
            if (match && !(previous&4) && (v&32)) io16(0x202,io16(0x202)|4);
            return;
        }
        if (offset==6 || offset==0x130) return;
        if (offset>=0x100 && offset<=0x10e) {
            unsigned n=(offset-0x100)/4;
            if (!(offset&2)) { timerReload_[n]=v;if (!(io16(offset+2)&0x80)) io16(offset,v);return; }
            auto old=io16(offset);io16(offset,v&(n?0xc7:0xc3));
            if (!(old&0x80) && (v&0x80)) {io16(offset-2,timerReload_[n]);timerPhase_[n]=0;}return;
        }
        io16(offset,v);
        if (offset>=0xba && offset<=0xde && (offset-0xba)%12==0 && (v&0x8000) && !dmaBusy_) dma(0);
        return;
    }
    write8(a,v);write8(a+1,v>>8);
}
void GBA::write32(uint32_t a,uint32_t v) { a&=~3u;write16(a,v);write16(a+2,v>>16); }
void GBA::setKeys(uint16_t keys) {
    io16(0x130,(~keys)&0x3ff);auto select=io16(0x132);
    bool active=select&0x8000?(keys&(select&0x3ff))==(select&0x3ff):bool(keys&select&0x3ff);
    if ((select&0x4000) && active) io16(0x202,io16(0x202)|0x1000);
}
void GBA::tick(unsigned cycles) {
    const unsigned dividers[]={1,64,256,1024};
    for (unsigned n=0;n<cycles;++n) {
        ++stats_.cycles;bool overflow=false;
        for (unsigned t=0;t<4;++t) {
            auto control=io16(0x102+t*4);if (!(control&0x80)) {overflow=false;continue;}
            bool increment=control&4?overflow:++timerPhase_[t]>=dividers[control&3];overflow=false;
            if (!increment) continue;
            if (!(control&4)) timerPhase_[t]=0;
            unsigned value=unsigned(io16(0x100+t*4))+1;
            if (value>0xffff) {value=timerReload_[t];overflow=true;if (control&0x40) io16(0x202,io16(0x202)|(1<<(t+3)));}
            io16(0x100+t*4,value);
        }
        ++lineCycle_;
        if (lineCycle_==960 && line_<160) renderLine(line_);
        if (lineCycle_==1006) {
            io16(4,io16(4)|2);if (line_<160) dma(2);if (io16(4)&16) io16(0x202,io16(0x202)|2);
        }
        if (lineCycle_>=1232) {
            lineCycle_=0;line_=(line_+1)%228;io16(6,line_);auto status=io16(4)&~7u;
            if (line_>=160 && line_<227) status|=1;
            if (line_==(status>>8)) {status|=4;if (status&32) io16(0x202,io16(0x202)|4);}
            io16(4,status);
            if (line_==160) {++stats_.frames;if (status&8) io16(0x202,io16(0x202)|1);dma(1);}
        }
    }
}
void GBA::dma(unsigned timing) {
    if (dmaBusy_) return;dmaBusy_=true;
    try {
        for (unsigned channel=0;channel<4;++channel) {
            unsigned base=0xb0+channel*12;auto control=io16(base+10);
            if (!(control&0x8000) || ((control>>12)&3)!=timing) continue;
            uint32_t source=io32(base)&(channel?0x0fffffff:0x07ffffff),destination=io32(base+4)&(channel==3?0x0fffffff:0x07ffffff);
            unsigned count=io16(base+8)&(channel==3?0xffff:0x3fff);if (!count) count=channel==3?0x10000:0x4000;
            unsigned width=control&0x400?4:2;unsigned sourceMode=(control>>7)&3,destMode=(control>>5)&3;
            if (sourceMode==3) throw std::runtime_error("Invalid GBA DMA source mode");
            for (unsigned n=0;n<count;++n) {
                if (width==4) write32(destination,read32(source));else write16(destination,read16(source));
                source+=sourceMode==0?width:sourceMode==1?-int(width):0;
                destination+=destMode==0 || destMode==3?width:destMode==1?-int(width):0;
            }
            // This first implementation performs the transfer atomically. Bus
            // arbitration, precise DMA latency and FIFO timing are later work.
            io16(base,source);io16(base+2,source>>16);
            if (destMode!=3) {io16(base+4,destination);io16(base+6,destination>>16);}
            if (!(control&0x200) || !timing) io16(base+10,control&~0x8000);
            if (control&0x4000) io16(0x202,io16(0x202)|(1<<(8+channel)));
        }
    } catch (...) {dmaBusy_=false;throw;}
    dmaBusy_=false;
}
void GBA::renderLine(unsigned y) {
    auto display=io16(0);unsigned mode=display&7;
    if (display&0x80) {std::fill_n(pixels_.begin()+y*240,240,0xffffffff);return;}
    if (mode<3) throw std::runtime_error("GBA tiled/affine display modes 0–2 are not implemented in this prototype");
    if (mode>5) throw std::runtime_error("Invalid GBA display mode");
    for (unsigned x=0;x<240;++x) {
        uint16_t colour=uint16_t(palette_[0])|uint16_t(palette_[1])<<8;
        unsigned page=display&16?0xa000:0;
        if (display&0x400) {
            if (mode==3) {unsigned a=(y*240+x)*2;colour=uint16_t(vram_[a])|uint16_t(vram_[a+1])<<8;}
            else if (mode==4) {unsigned a=vram_[page+y*240+x]*2;colour=uint16_t(palette_[a])|uint16_t(palette_[a+1])<<8;}
            else if (x<160 && y<128) {unsigned a=page+(y*160+x)*2;colour=uint16_t(vram_[a])|uint16_t(vram_[a+1])<<8;}
        }
        pixels_[y*240+x]=colour555(colour);
    }
}
int GBA::modeBank(uint32_t status) {
    switch (status&31) {
        case 0x10:case 0x1f:return 0;case 0x11:return 1;case 0x12:return 2;
        case 0x13:return 3;case 0x17:return 4;case 0x1b:return 5;default:return -1;
    }
}
void GBA::setCPSR(uint32_t status) {
    int old=modeBank(cpu_.cpsr),next=modeBank(status);
    if (next<0 || old<0) throw std::runtime_error("Invalid ARM processor mode");
    if (old!=next) {
        cpu_.banked[old]={cpu_.r[13],cpu_.r[14]};
        if ((old==1)!=(next==1)) {
            auto& outgoing=old==1?cpu_.fiqHigh:cpu_.userHigh;
            auto& incoming=next==1?cpu_.fiqHigh:cpu_.userHigh;
            for (unsigned n=0;n<5;++n) {outgoing[n]=cpu_.r[n+8];cpu_.r[n+8]=incoming[n];}
        }
        cpu_.r[13]=cpu_.banked[next][0];cpu_.r[14]=cpu_.banked[next][1];
    }
    if ((cpu_.cpsr^status)&T) pipelineValid_=false;
    cpu_.cpsr=status;
}
void GBA::enterException(uint32_t mode,uint32_t vector,uint32_t link) {
    pipelineValid_=false;
    auto status=cpu_.cpsr;
    setCPSR((status&~(31u|T))|mode|0x80);
    cpu_.spsr[modeBank(mode)]=status;cpu_.r[14]=link;cpu_.r[15]=vector;cpu_.halted=false;
}
unsigned GBA::undefinedInstruction(uint32_t pc) {
    auto link=pc+(cpu_.cpsr&T?2:4);enterException(0x1b,4,link);return 3;
}
uint32_t GBA::pushSVCFrame() {
    // Ascending addresses: saved SPSR, r11, r12, exception link.
    cpu_.r[13]-=16;
    write32(cpu_.r[13],cpu_.spsr[3]);write32(cpu_.r[13]+4,cpu_.r[11]);
    write32(cpu_.r[13]+8,cpu_.r[12]);write32(cpu_.r[13]+12,cpu_.r[14]);
    return cpu_.r[13];
}
void GBA::returnSVCFrame(uint32_t address) {
    pipelineValid_=false;
    auto status=read32(address),r11=read32(address+4),r12=read32(address+8),link=read32(address+12);
    if (modeBank(status)<0) throw std::runtime_error("Invalid GBA BIOS SVC stack return status");
    setCPSR((cpu_.cpsr&~63u)|0x93);
    cpu_.r[13]=address+16;cpu_.r[11]=r11;cpu_.r[12]=r12;cpu_.r[14]=link;cpu_.spsr[3]=status;
    setCPSR(status);cpu_.r[15]=link&~(status&T?1u:3u);
    biosLatch_=0xe3a02004;
}
// Functional decompression HLE. Validate and decode before touching emulated
// memory so malformed streams cannot leave partially installed graphics.
unsigned GBA::decompress(unsigned service,uint32_t op,uint32_t pc) {
    bool lz=service==0x11 || service==0x12,half=service==0x12 || service==0x15;
    uint32_t source=cpu_.r[0],destination=cpu_.r[1];
    auto fail=[&](const char* why) {unsupported(op,pc,why);};
    if (source&3) fail("GBA BIOS decompression requires a word-aligned source");
    // Restrict HLE to contiguous physical RAM or populated cartridge data.
    // Mirrored/overlapping streams and other bus regions need firmware fidelity.
    auto endOf=[&](uint32_t a,bool input)->uint64_t {
        if (a>=0x02000000 && a<0x02040000) return 0x02040000;
        if (a>=0x03000000 && a<0x03008000) return 0x03008000;
        if (input && a>=0x08000000 && a<0x0e000000) {
            uint32_t base=a&0xfe000000u;
            if ((a&0x1ffffff)<rom_.size()) return uint64_t(base)+rom_.size();
        }
        if (!input && half) {
            if (a>=0x05000000 && a<0x05000400) return 0x05000400;
            if (a>=0x06000000 && a<0x06018000) return 0x06018000;
            if (a>=0x07000000 && a<0x07000400) return 0x07000400;
        }
        return 0;
    };
    auto sourceEnd=endOf(source,true);
    uint64_t cursor=source;
    auto byte=[&]()->uint8_t {
        if (cursor>=sourceEnd) fail("Truncated or unsupported GBA BIOS decompression source");
        return read8(uint32_t(cursor++));
    };
    uint32_t header=byte();for (unsigned n=1;n<4;++n) header|=uint32_t(byte())<<(n*8);
    if ((header&255)!=(lz?0x10u:0x30u)) fail("Invalid GBA BIOS compression header");
    unsigned size=header>>8;
    if (!size) return 0;
    if (half && ((destination|size)&1)) fail("GBA BIOS halfword decompression requires an aligned destination and even output size");
    if (uint64_t(destination)+size>endOf(destination,false)) fail("Unsupported GBA BIOS decompression destination or size");
    std::vector<uint8_t> output;output.reserve(size);
    auto append=[&](uint8_t value) {output.push_back(value);};
    while (output.size()<size) {
        unsigned control=byte();
        if (lz) {
            for (unsigned mask=0x80;mask && output.size()<size;mask>>=1) {
                if (!(control&mask)) append(byte());
                else {
                    unsigned high=byte(),low=byte(),count=(high>>4)+3,distance=((high&15)<<8|low)+1;
                    if (distance>output.size()) fail("Invalid GBA BIOS LZ77 back-reference");
                    if (half && distance==1) fail("GBA BIOS VRAM LZ77 distance-one references are unsupported");
                    for (unsigned n=0;n<count && output.size()<size;++n) append(output[output.size()-distance]);
                }
            }
        } else {
            unsigned count=(control&127)+((control&128)?3:1);
            if (control&128) {auto value=byte();for (unsigned n=0;n<count && output.size()<size;++n) append(value);}
            else for (unsigned n=0;n<count && output.size()<size;++n) append(byte());
        }
    }
    // Decode first for host safety, but reject overlap instead of claiming to
    // reproduce firmware's interleaved source reads and destination writes.
    if (uint64_t(source)<uint64_t(destination)+size && uint64_t(destination)<cursor)
        fail("Overlapping GBA BIOS decompression buffers are unsupported");
    for (unsigned n=0;n<size;n+=half?2:1) {
        if (half) write16(destination+n,output[n]|uint16_t(output[n+1])<<8);
        else write8(destination+n,output[n]);
    }
    return unsigned(cursor-source)+size*2; // approximate, atomic HLE timing
}
unsigned GBA::softwareInterrupt(unsigned service,uint32_t op,uint32_t pc) {
    if (service!=0 && service!=1 && service!=2 && service!=4 && service!=5 && service!=6 && service!=7 && service!=8 && service!=0xb && service!=0xc && service!=0x11 && service!=0x12 && service!=0x14 && service!=0x15)
        unsupported(op,pc,"This GBA BIOS service is not implemented yet");
    if ((service==6 && !cpu_.r[1]) || (service==7 && !cpu_.r[0]))
        unsupported(op,pc,"GBA BIOS division by zero would hang the console");
    if ((service==4 || service==5) && biosWaits_.size()>=maxBIOSWaits)
        unsupported(op,pc,"GBA BIOS interrupt-wait nesting limit reached");
    unsigned decompressionCycles=service>=0x11?decompress(service,op,pc):0;
    auto next=cpu_.r[15];enterException(0x13,8,next);unsigned cycles=12+decompressionCycles;bool waiting=false;
    auto svcFrame=pushSVCFrame();
    auto callerStatus=cpu_.spsr[3];
    setCPSR((cpu_.cpsr&~63u)|0x1f); // Remaining firmware work uses the user/system bank.
    if (service==0) {
        auto target=iwram_[0x7ffa]?0x02000000u:0x08000000u;
        std::fill(iwram_.begin()+0x7e00,iwram_.end(),0);setCPSR(0x1f);
        std::fill_n(cpu_.r.begin(),13,0);cpu_.r[13]=0x03007f00;cpu_.r[14]=cpu_.r[15]=target;
        cpu_.banked[2]={0x03007fa0,0};cpu_.banked[3]={0x03007fe0,0};cpu_.spsr[2]=cpu_.spsr[3]=0;
        cpu_.halted=false;biosWaits_.clear();biosLatch_=0xe129f000;return cycles+128;
    } else if (service==1) {
        auto flags=cpu_.r[0];
        if (flags&1) {ewram_.fill(0);cycles+=ewram_.size()/4;}
        if (flags&2) {std::fill_n(iwram_.begin(),0x7e00,0);cycles+=0x7e00/4;}
        if (flags&4) {palette_.fill(0);cycles+=palette_.size()/4;}
        if (flags&8) {vram_.fill(0);cycles+=vram_.size()/4;}
        if (flags&16) {oam_.fill(0);cycles+=oam_.size()/4;}
        if (flags&32) {std::fill(io_.begin()+0x120,io_.begin()+0x12c,0);std::fill(io_.begin()+0x134,io_.begin()+0x15c,0);io16(0x134,0x8000);}
        if (flags&64) {std::fill(io_.begin()+0x60,io_.begin()+0xa8,0);io16(0x88,0x200);}
        if (flags&128) {
            std::fill_n(io_.begin(),0x56,0);io16(0x20,0x100);io16(0x26,0x100);io16(0x30,0x100);io16(0x36,0x100);
            std::fill(io_.begin()+0xb0,io_.begin()+0xe0,0);std::fill(io_.begin()+0x100,io_.begin()+0x110,0);
            timerReload_.fill(0);timerPhase_.fill(0);io16(0x132,0);for (unsigned off=0x200;off<=0x208;off+=2) io16(off,0);
            io16(6,line_);auto status=uint16_t((line_>=160 && line_<227?1:0)|(lineCycle_>=1006?2:0)|(line_==0?4:0));io16(4,status);
        }
        io16(0,0x80);io16(0x120,0); // documented low serial-data side effect
    } else if (service==2) cpu_.halted=true;
    else if (service==4 || service==5) {
        if (service==5) {cpu_.r[0]=1;cpu_.r[1]=1;}
        auto mask=uint16_t(cpu_.r[1]);auto flags=read16(0x03007ff8);
        io16(0x208,1);
        if (cpu_.r[0]) {write16(0x03007ff8,flags&~mask);flags&=~mask;}
        if (flags&mask) write16(0x03007ff8,flags&~mask);
        else {
            auto status=cpu_.spsr[3],waitStatus=(status&~0xbfu)|0x1f; // BIOS runs waits in ARM system mode with IRQ enabled.
            biosWaits_.push_back({mask,status,next,waitStatus,waitAddress,svcFrame});waiting=true;cpu_.halted=true;
        }
    } else if (service>=6 && service<=8) {
        setCPSR((callerStatus&~63u)|0x1f);
        cpu_.r[15]=service==6?div_start:service==7?divarm_start:sqrt_start;
        return cycles;
    } else if (service==0xb || service==0xc) {
        bool fast=service==0xc,fill=cpu_.r[2]&(1u<<24);unsigned width=fast || (cpu_.r[2]&(1u<<26))?4:2;
        unsigned count=cpu_.r[2]&0x1fffff;if (fast) count=(count+7)&~7u;
        uint32_t source=cpu_.r[0]&~(width-1);
        // BIOS rejects source regions below EWRAM, including overflow into them.
        if (count && source>=0x02000000 && uint64_t(source)+uint64_t(fill?1:count)*width<=0x100000000ull) {
            // Original ARM workers retain all progress in CPU registers and
            // emulated stacks. IRQs and nested SWIs use the normal interpreter.
            setCPSR((callerStatus&~63u)|0x1f);
            cpu_.r[15]=fast?fast_start:copy_start;
            return cycles;
        }
    }
    // Non-copy services remain atomic; pending waits keep their SVC frame live.
    if (waiting) {setCPSR(biosWaits_.back().waitStatus);cpu_.r[15]=waitAddress;}
    else returnSVCFrame(svcFrame);
    return cycles;
}
uint32_t GBA::savedPSR(uint32_t op,uint32_t pc) const {
    int bank=modeBank(cpu_.cpsr);
    if (bank<=0) unsupported(op,pc,"This ARM processor mode has no SPSR");
    return cpu_.spsr[bank];
}
uint32_t& GBA::userRegister(unsigned reg) {
    int bank=modeBank(cpu_.cpsr);
    if (reg>=8 && reg<=12 && bank==1) return cpu_.userHigh[reg-8];
    if (reg>=13 && reg<=14 && bank!=0) return cpu_.banked[0][reg-13];
    return cpu_.r[reg];
}
bool GBA::condition(unsigned c) const {
    bool n=cpu_.cpsr&N,z=cpu_.cpsr&Z,carry=cpu_.cpsr&C,v=cpu_.cpsr&V;
    switch(c) {case 0:return z;case 1:return !z;case 2:return carry;case 3:return !carry;case 4:return n;case 5:return !n;case 6:return v;case 7:return !v;case 8:return carry&&!z;case 9:return !carry||z;case 10:return n==v;case 11:return n!=v;case 12:return !z&&n==v;case 13:return z||n!=v;case 14:return true;default:return false;}
}
void GBA::nz(uint32_t v) {cpu_.cpsr=(cpu_.cpsr&~(N|Z))|(v&N)|(v==0?Z:0);}
uint32_t GBA::add(uint32_t a,uint32_t b,bool carry,bool flags) {
    uint64_t sum=uint64_t(a)+b+unsigned(carry);uint32_t result=sum;
    if (flags) {nz(result);bool overflow=((~(a^b)&(a^result))>>31)!=0;cpu_.cpsr=(cpu_.cpsr&~(C|V))|(sum>>32?C:0)|(overflow?V:0);}
    return result;
}
uint32_t GBA::shift(uint32_t v,unsigned type,unsigned amount,bool immediate,bool& carry) {
    if (!amount) {
        if (!immediate || type==0) return v;
        if (type==3) {bool old=carry;carry=v&1;return (v>>1)|(old?N:0);}amount=32;
    }
    switch(type) {
        case 0:carry=amount<=32?bool((v>>(32-amount))&1):false;return amount<32?v<<amount:0;
        case 1:carry=amount<=32?bool((v>>(amount-1))&1):false;return amount<32?v>>amount:0;
        case 2:carry=amount<32?bool((v>>(amount-1))&1):bool(v&N);return amount<32?uint32_t(int32_t(v)>>amount):(v&N?0xffffffff:0);
        default: {auto rotated=rolror(v,amount);carry=rotated&N;return rotated;}
    }
}
[[noreturn]] void GBA::unsupported(uint32_t opcode,uint32_t pc,const char* why) const {
    std::ostringstream s;s<<why<<" (opcode 0x"<<std::hex<<opcode<<", PC 0x"<<pc<<")";throw std::runtime_error(s.str());
}
uint32_t GBA::fetchOpcode(uint32_t address,bool thumbState) {
    auto value=thumbState?uint32_t(read16(address)):read32(address);
    // A halfword fetch on the 32-bit internal instruction bus replaces only
    // its addressed lane. On the 16-bit external bus it drives both lanes.
    bool internal=(address>>24)==0 || (address>>24)==3 || (address>>24)==7;
    if (!thumbState) openBus_=value;
    else if (internal) {unsigned shift=(address&2)*8;openBus_=(openBus_&~(0xffffu<<shift))|(value<<shift);}
    else openBus_=value*0x10001u;
    if (address<0x4000) biosLatch_=firmwareWord(address&~3u);
    return value;
}
unsigned GBA::step() {
    auto start=stats_.cycles;
    bool atWait=!biosWaits_.empty() && cpu_.r[15]==biosWaits_.back().waitPC &&
        (cpu_.cpsr&0x3f)==(biosWaits_.back().waitStatus&0x3f);
    if (atWait) {
        auto wait=biosWaits_.back();auto flags=read16(0x03007ff8);
        if (flags&wait.mask) {
            write16(0x03007ff8,flags&~wait.mask);biosWaits_.pop_back();
            if (wait.svcFrame) returnSVCFrame(wait.svcFrame);
            else { // Older snapshots did not write SVC frames into memory.
                pipelineValid_=false;
                cpu_.spsr[3]=wait.status;cpu_.banked[3][1]=wait.pc;
                setCPSR(wait.status);cpu_.r[15]=wait.pc;biosLatch_=0xe3a02004;
            }
            cpu_.halted=false;atWait=false;
        }
    }
    if (io16(0x200)&io16(0x202)) cpu_.halted=false;
    if ((io16(0x208)&1) && (io16(0x200)&io16(0x202)) && !(cpu_.cpsr&0x80)) {
        auto handler=read32(0x03007ffc);
        if (!handler || (handler&3)) throw std::runtime_error("GBA IRQ requires an aligned ARM callback at 0x03007FFC");
        enterException(0x12,0x18,cpu_.r[15]+4);tick(3);return 3;
    }
    if (atWait || cpu_.halted) {cpu_.halted=true;tick(1);return 1;}
    uint32_t pc=cpu_.r[15];
    if (pc==4 && (cpu_.cpsr&31)==0x1b) throw std::runtime_error("GBA undefined-instruction exception reached a BIOS handler not implemented by the independent firmware");
    if (pc<0x4000 && ((cpu_.cpsr&T) || !firmwareInstruction(pc))) unsupported(0,pc,"Address is outside the executable independent GBA firmware routines");bool isThumb=cpu_.cpsr&T;unsigned cycles;
    unsigned width=isThumb?2:4;
    if (!pipelineValid_ || pipelineAddress_!=pc || pipelineThumb_!=isThumb) {
        pipeline_[0]=fetchOpcode(pc,isThumb);pipeline_[1]=fetchOpcode(pc+width,isThumb);
    }
    auto op=pipeline_[0];pipeline_[0]=pipeline_[1];pipeline_[1]=fetchOpcode(pc+width*2,isThumb);
    pipelineAddress_=pc+width;pipelineThumb_=isThumb;pipelineValid_=true;cpu_.r[15]=pc+width;
    cycles=isThumb?thumb(uint16_t(op),pc):condition(op>>28)?arm(op,pc):1;
    if (pc==0x114 || pc==0x414) biosLatch_=0xe25ef004;
    if (pc==copy_return || pc==arithmetic_return) biosLatch_=0xe3a02004;
    ++stats_.instructions;tick(cycles);return unsigned(stats_.cycles-start);
}
unsigned GBA::arm(uint32_t op,uint32_t pc) {
    // ARMv4T undefined transfer encodings and absent coprocessors trap in the
    // CPU. Other unsupported emulator features retain their explicit faults.
    if ((op&0x0e000010)==0x06000010 || (op&0x0e000000)==0x0c000000 || (op&0x0f000000)==0x0e000000)
        return undefinedInstruction(pc);
    auto value=[&](unsigned n){return n==15?pc+8:cpu_.r[n];};
    if ((op&0x0ffffff0)==0x012fff10) {pipelineValid_=false;auto target=value(op&15);cpu_.cpsr=(cpu_.cpsr&~T)|(target&1?T:0);cpu_.r[15]=target&~(target&1?1u:3u);return 3;}
    if ((op&0x0fbf0fff)==0x010f0000) {if (((op>>12)&15)==15) unsupported(op,pc,"MRS cannot target PC");cpu_.r[(op>>12)&15]=op&(1<<22)?savedPSR(op,pc):cpu_.cpsr;return 1;}
    if ((op&0x0db0f000)==0x0120f000) {
        uint32_t operand=op&(1<<25)?rolror(op&255,((op>>8)&15)*2):value(op&15);uint32_t mask=0;
        for (unsigned b=0;b<4;++b) if (op&(1<<(16+b))) mask|=0xffu<<(8*b);
        if (op&(1<<22)) {
            auto old=savedPSR(op,pc);mask&=0xf00000ff;cpu_.spsr[modeBank(cpu_.cpsr)]=(old&~mask)|(operand&mask);
        } else {
            // ARMv4T: user mode can write flags only; MSR cannot switch ARM/Thumb.
            mask&=(cpu_.cpsr&31)==0x10?0xf0000000:0xf00000df;
            uint32_t next=(cpu_.cpsr&~mask)|(operand&mask);
            if (modeBank(next)<0) unsupported(op,pc,"Invalid ARM processor mode in MSR");
            setCPSR(next);
        }
        return 1;
    }
    if ((op&0x0f8000f0)==0x00800090) {
        bool signedMultiply=op&(1<<22),accumulate=op&(1<<21);unsigned hi=(op>>16)&15,lo=(op>>12)&15;
        uint64_t result=signedMultiply?uint64_t(int64_t(int32_t(value(op&15)))*int64_t(int32_t(value((op>>8)&15)))):uint64_t(value(op&15))*value((op>>8)&15);
        if (accumulate) result+=(uint64_t(cpu_.r[hi])<<32)|cpu_.r[lo];cpu_.r[lo]=result;cpu_.r[hi]=result>>32;
        if (op&(1<<20)) cpu_.cpsr=(cpu_.cpsr&~(N|Z))|(result>>63?N:0)|(result==0?Z:0);return 3;
    }
    if ((op&0x0fc000f0)==0x00000090) {
        uint32_t result=value(op&15)*value((op>>8)&15);if (op&(1<<21)) result+=value((op>>12)&15);cpu_.r[(op>>16)&15]=result;if (op&(1<<20)) nz(result);return 2;
    }
    if ((op&0x0fb00ff0)==0x01000090) {
        auto address=value((op>>16)&15);bool byte=op&(1<<22);auto old=byte?read8(address):read32(address);if (byte) write8(address,value(op&15));else write32(address,value(op&15));cpu_.r[(op>>12)&15]=old;return 4;
    }
    if ((op&0x0e000090)==0x00000090) {
        unsigned rn=(op>>16)&15,rd=(op>>12)&15;uint32_t base=value(rn),offset=op&(1<<22)?((op>>4)&0xf0)|(op&15):value(op&15);
        uint32_t adjusted=op&(1<<23)?base+offset:base-offset,address=op&(1<<24)?adjusted:base;unsigned kind=(op>>5)&3;
        if (!kind || (!(op&(1<<20)) && kind!=1)) return undefinedInstruction(pc);
        if (!(op&(1<<20))) write16(address,value(rd));
        else {uint32_t result;if (kind==1) result=rolror(read16(address),(address&1)*8);else if (kind==2) result=uint32_t(int32_t(int8_t(read8(address))));else if (kind==3) result=address&1?uint32_t(int32_t(int8_t(read8(address)))):uint32_t(int32_t(int16_t(read16(address))));else unsupported(op,pc,"Invalid ARM halfword transfer");if (rd==15) pipelineValid_=false;cpu_.r[rd]=rd==15?result&~3u:result;}
        if (!(op&(1<<24)) || (op&(1<<21))) if (rn!=rd || !(op&(1<<20))) cpu_.r[rn]=adjusted;return op&(1<<20)?3:2;
    }
    unsigned group=(op>>25)&7;
    if (group==5) {pipelineValid_=false;if (op&(1<<24)) cpu_.r[14]=pc+4;int32_t offset=int32_t(op<<8)>>6;cpu_.r[15]=pc+8+offset;return 3;}
    if (group==4) {
        unsigned rn=(op>>16)&15,list=op&0xffff,count=std::popcount(list);
        if (!count) {list=0x8000;count=16;} // ARM7 empty list transfers PC, advances base by 64.
        bool load=op&(1<<20),special=op&(1<<22),restore=special && load && (list&0x8000);
        uint32_t status=restore?savedPSR(op,pc):cpu_.cpsr;
        if (restore && modeBank(status)<0) unsupported(op,pc,"Invalid ARM SPSR mode on LDM return");
        bool user=special && !restore;
        uint32_t base=value(rn),address=op&(1<<23)?base+(op&(1<<24)?4:0):base-count*4+(op&(1<<24)?0:4);
        uint32_t writeback=op&(1<<23)?base+count*4:base-count*4;
        unsigned first=std::countr_zero(list);
        for (unsigned reg=0;reg<16;++reg) if (list&(1<<reg)) {
            if (load) {auto result=read32(address&~3u);(user?userRegister(reg):cpu_.r[reg])=reg==15?result&~(status&T?1u:3u):result;}
            else {auto data=reg==15?pc+12:user?userRegister(reg):value(reg);
                if (!user && (op&(1<<21)) && reg==rn && reg!=first) data=writeback;
                write32(address,data);}
            address+=4;
        }
        if ((op&(1<<21)) && !((op&(1<<20)) && (list&(1<<rn)))) cpu_.r[rn]=op&(1<<23)?base+count*4:base-count*4;
        if (load && (list&0x8000)) pipelineValid_=false;
        if (restore) setCPSR(status);
        return count+(op&(1<<20)?2:1);
    }
    if ((op&0x0c000000)==0x04000000) {
        unsigned rn=(op>>16)&15,rd=(op>>12)&15;uint32_t base=value(rn),offset=op&0xfff;
        if (op&(1<<25)) {if (op&16) unsupported(op,pc,"Invalid ARM transfer shift");bool carry=cpu_.cpsr&C;offset=shift(value(op&15),(op>>5)&3,(op>>7)&31,true,carry);}
        uint32_t adjusted=op&(1<<23)?base+offset:base-offset,address=op&(1<<24)?adjusted:base;
        if (op&(1<<20)) {uint32_t result=op&(1<<22)?read8(address):read32(address);if (rd==15) pipelineValid_=false;cpu_.r[rd]=rd==15?result&~3u:result;}
        else {uint32_t result=rd==15?pc+12:value(rd);if (op&(1<<22)) write8(address,result);else write32(address,result);}
        if (!(op&(1<<24)) || (op&(1<<21))) if (!(op&(1<<20)) || rn!=rd) cpu_.r[rn]=adjusted;
        return op&(1<<20)?3:2;
    }
    if ((op&0x0c000000)==0) {
        bool flags=op&(1<<20),carry=cpu_.cpsr&C;unsigned operation=(op>>21)&15,rn=(op>>16)&15,rd=(op>>12)&15;uint32_t b;
        // Non-flag test/compare slots are PSR operations or later-architecture
        // encodings (BLX, CLZ, BKPT, saturating arithmetic), not ARMv4 ALU ops.
        if (!flags && operation>=8 && operation<=11) return undefinedInstruction(pc);
        if (op&(1<<25)) {unsigned rotate=((op>>8)&15)*2;b=rolror(op&255,rotate);if (rotate) carry=b&N;}
        else {unsigned amount=op&16?value((op>>8)&15)&255:(op>>7)&31;uint32_t input=value(op&15);if ((op&16) && (op&15)==15) input=pc+12;b=shift(input,(op>>5)&3,amount,!(op&16),carry);}
        auto a=rn==15 && !(op&(1<<25)) && (op&16)?pc+12:value(rn);uint32_t result=0;bool arithmetic=operation>=2&&operation<=7;
        bool exceptionReturn=flags && rd==15 && !(operation>=8 && operation<=11);
        uint32_t status=exceptionReturn?savedPSR(op,pc):cpu_.cpsr;
        if (exceptionReturn && modeBank(status)<0) unsupported(op,pc,"Invalid ARM SPSR mode on data-processing return");
        bool update=!exceptionReturn && (flags || (operation>=8 && operation<=11));
        switch(operation) {
            case 0:case 8:result=a&b;break;case 1:case 9:result=a^b;break;
            case 2:case 10:result=add(a,~b,true,update);break;
            case 3:result=add(b,~a,true,update);break;
            case 4:case 11:result=add(a,b,false,update);break;
            case 5:result=add(a,b,cpu_.cpsr&C,update);break;
            case 6:result=add(a,~b,cpu_.cpsr&C,update);break;
            case 7:result=add(b,~a,cpu_.cpsr&C,update);break;
            case 12:result=a|b;break;case 13:result=b;break;case 14:result=a&~b;break;case 15:result=~b;break;
        }
        arithmetic=arithmetic || operation==10 || operation==11;
        if (update && !arithmetic) {nz(result);cpu_.cpsr=(cpu_.cpsr&~C)|(carry?C:0);}
        if (!(operation>=8 && operation<=11)) {if (rd==15) pipelineValid_=false;if (exceptionReturn) setCPSR(status);cpu_.r[rd]=rd==15?result&~(cpu_.cpsr&T?1u:3u):result;}
        return rd==15?3:1+(!(op&(1<<25)) && (op&16)?1:0);
    }
    if ((op&0x0f000000)==0x0f000000) return softwareInterrupt((op>>16)&255,op,pc);
    unsupported(op,pc,"Unsupported ARMv4T instruction");
}
unsigned GBA::thumb(uint16_t op,uint32_t pc) {
    if ((op&0xff00)==0xbe00 || (op&0xf800)==0xe800) return undefinedInstruction(pc);
    auto& r=cpu_.r;unsigned rd=op&7,rs=(op>>3)&7;
    if ((op&0xf800)<0x1800) {bool carry=cpu_.cpsr&C;r[rd]=shift(r[rs],(op>>11)&3,(op>>6)&31,true,carry);nz(r[rd]);cpu_.cpsr=(cpu_.cpsr&~C)|(carry?C:0);return 1;}
    if ((op&0xf800)==0x1800) {auto b=op&0x400?uint32_t((op>>6)&7):r[(op>>6)&7];r[rd]=op&0x200?add(r[rs],~b,true,true):add(r[rs],b,false,true);return 1;}
    if ((op&0xe000)==0x2000) {unsigned target=(op>>8)&7,kind=(op>>11)&3;uint32_t imm=op&255;if (!kind) {r[target]=imm;nz(imm);}else if (kind==1) add(r[target],~imm,true,true);else if (kind==2) r[target]=add(r[target],imm,false,true);else r[target]=add(r[target],~imm,true,true);return 1;}
    if ((op&0xfc00)==0x4000) {
        unsigned kind=(op>>6)&15;auto a=r[rd],b=r[rs];uint32_t result=0;bool carry=cpu_.cpsr&C,store=true,arithmetic=false;
        switch(kind) {
            case 0:result=a&b;break;case 1:result=a^b;break;
            case 2:case 3:case 4:result=shift(a,kind-2,b&255,false,carry);break;
            case 5:result=add(a,b,carry,true);arithmetic=true;break;case 6:result=add(a,~b,carry,true);arithmetic=true;break;
            case 7:result=shift(a,3,b&255,false,carry);break;
            case 8:result=a&b;store=false;break;case 9:result=add(0,~b,true,true);arithmetic=true;break;
            case 10:result=add(a,~b,true,true);arithmetic=true;store=false;break;
            case 11:result=add(a,b,false,true);arithmetic=true;store=false;break;
            case 12:result=a|b;break;case 13:result=a*b;break;case 14:result=a&~b;break;default:result=~b;break;
        }
        if (!arithmetic) {nz(result);cpu_.cpsr=(cpu_.cpsr&~C)|(carry?C:0);}if (store) r[rd]=result;return kind==13?2:1;
    }
    if ((op&0xfc00)==0x4400) {
        unsigned target=(op&7)|((op>>4)&8),source=(op>>3)&15,kind=(op>>8)&3;
        auto a=target==15?pc+4:r[target],b=source==15?pc+4:r[source];
        if (kind==3) {if (op&0x80) return undefinedInstruction(pc);pipelineValid_=false;cpu_.cpsr=(cpu_.cpsr&~T)|(b&1?T:0);r[15]=b&~(b&1?1u:3u);return 3;}
        if (kind==1) {add(a,~b,true,true);return 1;}
        auto result=kind==0?a+b:b;if (target==15) pipelineValid_=false;r[target]=target==15?result&~1u:result;return target==15?3:1;
    }
    if ((op&0xf800)==0x4800) {r[(op>>8)&7]=read32(((pc+4)&~3u)+(op&255)*4);return 3;}
    if ((op&0xf000)==0x5000) {
        auto address=r[rs]+r[(op>>6)&7];unsigned kind=(op>>9)&7;
        switch(kind) {case 0:write32(address,r[rd]);break;case 1:write16(address,r[rd]);break;case 2:write8(address,r[rd]);break;case 3:r[rd]=uint32_t(int32_t(int8_t(read8(address))));break;case 4:r[rd]=read32(address);break;case 5:r[rd]=rolror(read16(address),(address&1)*8);break;case 6:r[rd]=read8(address);break;case 7:r[rd]=address&1?uint32_t(int32_t(int8_t(read8(address)))):uint32_t(int32_t(int16_t(read16(address))));break;}return kind>=3?3:2;
    }
    if ((op&0xe000)==0x6000) {bool byte=op&0x1000,load=op&0x800;auto address=r[rs]+((op>>6)&31)*(byte?1:4);if (load) r[rd]=byte?read8(address):read32(address);else if (byte) write8(address,r[rd]);else write32(address,r[rd]);return load?3:2;}
    if ((op&0xf000)==0x8000) {auto address=r[rs]+((op>>6)&31)*2;if (op&0x800) r[rd]=rolror(read16(address),(address&1)*8);else write16(address,r[rd]);return op&0x800?3:2;}
    if ((op&0xf000)==0x9000) {auto address=r[13]+(op&255)*4;if (op&0x800) r[(op>>8)&7]=read32(address);else write32(address,r[(op>>8)&7]);return op&0x800?3:2;}
    if ((op&0xf000)==0xa000) {r[(op>>8)&7]=(op&0x800?r[13]:(pc+4)&~3u)+(op&255)*4;return 1;}
    if ((op&0xff00)==0xb000) {r[13]+=op&0x80?-int((op&127)*4):int((op&127)*4);return 1;}
    if ((op&0xf600)==0xb400) {
        bool pop=op&0x800;unsigned list=op&255,count=std::popcount(list)+bool(op&0x100);
        if (!count) {
            if (pop) {pipelineValid_=false;r[15]=read32(r[13]&~3u)&~1u;r[13]+=64;}
            else {r[13]-=64;write32(r[13],pc+4);}
            return pop?5:2;
        }
        uint32_t address=pop?r[13]:r[13]-count*4;
        for (unsigned i=0;i<8;++i) if (list&(1<<i)) {if (pop) r[i]=read32(address&~3u);else write32(address,r[i]);address+=4;}
        if (op&0x100) {if (pop) {pipelineValid_=false;r[15]=read32(address&~3u)&~1u;}else write32(address,r[14]);}
        r[13]+=pop?count*4:-int(count*4);return count+(pop?2:1);
    }
    if ((op&0xf000)==0xc000) {
        unsigned base=(op>>8)&7,list=op&255,count=std::popcount(list);auto address=r[base];
        if (!count) {if (op&0x800) {pipelineValid_=false;r[15]=read32(address&~3u)&~1u;}else write32(address,pc+4);r[base]+=64;return op&0x800?5:2;}
        auto writeback=address+count*4;unsigned first=std::countr_zero(list);
        for (unsigned i=0;i<8;++i) if (list&(1<<i)) {if (op&0x800) r[i]=read32(address&~3u);else write32(address,i==base && i!=first?writeback:r[i]);address+=4;}
        if (!(op&0x800) || !(list&(1<<base))) r[base]=address;return count+(op&0x800?2:1);
    }
    if ((op&0xf000)==0xd000) {unsigned c=(op>>8)&15;if (c==15) return softwareInterrupt(op&255,op,pc);if (c==14) return undefinedInstruction(pc);if (condition(c)) {pipelineValid_=false;r[15]=pc+4+int32_t(int8_t(op&255))*2;return 3;}return 1;}
    if ((op&0xf800)==0xe000) {pipelineValid_=false;int32_t offset=int32_t(uint32_t(op&0x7ff)<<21)>>20;r[15]=pc+4+offset;return 3;}
    if ((op&0xf800)==0xf000) {int32_t offset=int32_t(uint32_t(op&0x7ff)<<21)>>9;r[14]=pc+4+offset;return 1;}
    if ((op&0xf800)==0xf800) {pipelineValid_=false;auto target=r[14]+(op&0x7ff)*2;r[14]=(pc+2)|1;r[15]=target&~1u;return 3;}
    unsupported(op,pc,"Unsupported Thumb instruction");
}
std::vector<uint8_t> GBA::save() const {
    StateWriter w;w.number(0x36414743,4);w.number(fingerprint(rom_),8);w.number(frameDeadline_,8);
    for (auto r:cpu_.r) w.number(r,4);w.number(cpu_.cpsr,4);w.number(cpu_.halted,1);
    for (auto v:cpu_.userHigh) w.number(v,4);for (auto v:cpu_.fiqHigh) w.number(v,4);
    for (auto bank:cpu_.banked) for (auto v:bank) w.number(v,4);for (auto v:cpu_.spsr) w.number(v,4);
    w.number(biosLatch_,4);w.number(biosWaits_.size(),1);
    for (auto wait:biosWaits_) {w.number(wait.mask,2);w.number(wait.status,4);w.number(wait.pc,4);w.number(wait.waitStatus,4);w.number(wait.waitPC,4);w.number(wait.svcFrame,4);}
    w.number(stats_.cycles,8);w.number(stats_.instructions,8);w.number(stats_.frames,8);w.number(line_,2);w.number(lineCycle_,2);
    for (auto r:timerReload_) w.number(r,2);for (auto p:timerPhase_) w.number(p,4);
    w.block(ewram_);w.block(iwram_);w.block(io_);w.block(palette_);w.block(vram_);w.block(oam_);for (auto p:pixels_) w.number(p,4);
    for (auto p:pipeline_) w.number(p,4);w.number(pipelineAddress_,4);w.number(openBus_,4);w.number(pipelineValid_,1);w.number(pipelineThumb_,1);
    return protectState(std::move(w.bytes));
}
void GBA::restore(std::span<const uint8_t> data) {
    auto next=*this;StateReader r{checkedState(data)};auto version=r.number(4);if ((version<0x31414743 || version>0x36414743 || (version&0xffffff)!=0x414743) || r.number(8)!=fingerprint(rom_)) throw std::runtime_error("GBA state version or ROM does not match");
    next.frameDeadline_=r.number(8);for (auto& n:next.cpu_.r) n=r.number(4);next.cpu_.cpsr=r.number(4);next.cpu_.halted=r.number(1);
    next.cpu_.userHigh.fill(0);next.cpu_.fiqHigh.fill(0);next.cpu_.banked={};next.cpu_.spsr.fill(0);
    if (version>=0x32414743) {
        for (auto& v:next.cpu_.userHigh) v=r.number(4);for (auto& v:next.cpu_.fiqHigh) v=r.number(4);
        for (auto& bank:next.cpu_.banked) for (auto& v:bank) v=r.number(4);for (auto& v:next.cpu_.spsr) v=r.number(4);
    } else {next.cpu_.banked[2][0]=0x03007fa0;next.cpu_.banked[3][0]=0x03007fe0;}
    next.biosWaits_.clear();next.biosLatch_=0xe129f000;
    if (version==0x33414743) {
        auto active=r.number(1);auto mask=uint16_t(r.number(2));auto status=uint32_t(r.number(4)),pc=uint32_t(r.number(4));
        if (active>1) throw std::runtime_error("Invalid legacy GBA BIOS wait flag");
        if (active) next.biosWaits_.push_back({mask,status,pc,status&~0x80u,pc});
    } else if (version>=0x34414743) {
        next.biosLatch_=r.number(4);auto count=r.number(1);
        if (count>maxBIOSWaits) throw std::runtime_error("Invalid GBA BIOS wait depth");
        for (unsigned n=0;n<count;++n) {
            BIOSWait wait;wait.mask=r.number(2);wait.status=r.number(4);wait.pc=r.number(4);wait.waitStatus=r.number(4);wait.waitPC=r.number(4);
            if (version>=0x35414743) wait.svcFrame=r.number(4);
            next.biosWaits_.push_back(wait);
        }
    }
    next.stats_.cycles=r.number(8);next.stats_.instructions=r.number(8);next.stats_.frames=r.number(8);next.line_=r.number(2);next.lineCycle_=r.number(2);
    for (auto& v:next.timerReload_) v=r.number(2);for (auto& v:next.timerPhase_) v=r.number(4);
    r.block(next.ewram_);r.block(next.iwram_);r.block(next.io_);r.block(next.palette_);r.block(next.vram_);r.block(next.oam_);for (auto& p:next.pixels_) p=r.number(4);
    next.pipeline_={};next.pipelineAddress_=next.openBus_=0;next.pipelineValid_=next.pipelineThumb_=false;
    if (version>=0x36414743) {
        for (auto& p:next.pipeline_) p=r.number(4);next.pipelineAddress_=r.number(4);next.openBus_=r.number(4);
        auto valid=r.number(1),thumbState=r.number(1);
        if (valid>1 || thumbState>1 || (next.pipelineAddress_&(thumbState?1:3)) ||
            (valid && thumbState && ((next.pipeline_[0]|next.pipeline_[1])>0xffff))) throw std::runtime_error("Invalid GBA pipeline state");
        next.pipelineValid_=valid;next.pipelineThumb_=thumbState;
    }
    r.finish();
    if (next.stats_.cycles>UINT64_MAX-280896*2u || (next.frameDeadline_>next.stats_.cycles && next.frameDeadline_-next.stats_.cycles>280896)) throw std::runtime_error("Invalid state clock budget");
    if (next.line_>=228 || next.lineCycle_>=1232 || (modeBank(next.cpu_.cpsr)<0 || (version==0x31414743 && modeBank(next.cpu_.cpsr)!=0)) || (next.cpu_.r[15]&(next.cpu_.cpsr&T?1:3))) throw std::runtime_error("Invalid GBA state fields");
    for (auto wait:next.biosWaits_)
        if (modeBank(wait.status)<0 || modeBank(wait.waitStatus)<0 || (wait.waitStatus&0x80) ||
            (wait.pc&(wait.status&T?1:3)) || (wait.waitPC&(wait.waitStatus&T?1:3)) || (wait.svcFrame&3))
            throw std::runtime_error("Invalid GBA BIOS wait state");
    for (auto p:next.timerPhase_) if (p>=1024) throw std::runtime_error("Invalid GBA timer phase");
    next.dmaBusy_=false;*this=std::move(next);
}
}
