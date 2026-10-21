#include "crispy/gb.hpp"
#include <algorithm>
#include <bit>
#include <iomanip>
#include <sstream>
#include <stdexcept>
namespace crispy {
Capabilities GameBoy::capabilities() const { return {colour_?System::gbc:System::gb,160,144,4194304,70224}; }
void GameBoy::load(std::span<const uint8_t> bytes) {
    if (bytes.size()<0x150 || bytes.size()>8*1024*1024 || bytes.size()%0x4000) throw std::runtime_error("GB ROM must contain complete 16 KiB banks and a cartridge header");
    if (!colour_ && (bytes[0x143]&0xc0)==0xc0) throw std::runtime_error("This cartridge requires the GBC core");
    const auto type=bytes[0x147];
    if (!(type==0 || type==1 || type==2 || type==3 || type==8 || type==9 || type==0x11 || type==0x12 || type==0x13 || (type>=0x19 && type<=0x1e)))
        throw std::runtime_error("This cartridge mapper/RTC is not implemented in Crispy Core yet");
    const size_t sizes[]={0,0x800,0x2000,0x8000,0x20000,0x10000};
    if (bytes[0x149]>=std::size(sizes)) throw std::runtime_error("Unknown cartridge RAM size");
    if ((type==0 || type==8 || type==9) && bytes.size()>0x8000) throw std::runtime_error("Unbanked ROM exceeds 32 KiB");
    rom_.assign(bytes.begin(),bytes.end()); cartType_=type;
    mapper_=type>=0x19?5:type>=0x11?3:type>=1 && type<=3?1:0;
    ramSize_=sizes[bytes[0x149]]; eram_.fill(0xff); reset();
}
void GameBoy::reset() {
    cpu_=GBRegisters{};
    if (colour_) { cpu_.a=0x11;cpu_.f=0x80;cpu_.b=0;cpu_.c=0;cpu_.d=0xff;cpu_.e=0x56;cpu_.h=0;cpu_.l=0x0d; }
    vram_.fill(0);wram_.fill(0);oam_.fill(0);io_.fill(0);hram_.fill(0);
    bgPalette_.fill(0xff);objPalette_.fill(0xff);pixels_.fill(0xffffffff);
    io_[0]=0x30;io_[0x40]=0x91;io_[0x47]=0xfc;io_[0x48]=io_[0x49]=0xff;io_[0x0f]=1;io_[0x70]=1;
    stats_={};frameDeadline_=0;divider_=0;lineDot_=0;dmaTicks_=dmaIndex_=dmaDelay_=0;dmaSource_=dmaPending_=0;
    ie_=keys_=bankMode_=ramBank_=0;romBank_=1;ramEnabled_=mapper_==0;
    statLine_=doubleSpeed_=false;speedPhase_=0;timerReload_=timerReloaded_=serialTicks_=0;serial_.clear();updateSTAT();
}
std::string GameBoy::title() const {
    if (rom_.size()<0x144) return "Game Boy";
    auto first=rom_.begin()+0x134, end=rom_.begin()+((rom_[0x143]&0x80)?0x13f:0x144);
    return std::string(first,std::find(first,end,0));
}
std::span<const uint8_t> GameBoy::battery() const {
    const bool saved=cartType_==3 || cartType_==9 || cartType_==0x13 || cartType_==0x1b || cartType_==0x1e;
    return {eram_.data(),saved?ramSize_:0};
}
void GameBoy::restoreBattery(std::span<const uint8_t> data) {
    if (data.size()!=battery().size()) throw std::runtime_error("Battery RAM size does not match this cartridge");
    std::copy(data.begin(),data.end(),eram_.begin());
}
bool GameBoy::busConflict(uint16_t a) const {
    auto bus=[&](uint16_t address) { if (address>=0x8000 && address<0xa000) return 1; if (address>=0xc000 && address<0xfe00) return colour_?2:0;return 0; };
    return dmaTicks_ && a<0xfe00 && bus(a)==bus(dmaSource_);
}
uint8_t GameBoy::read(uint16_t a,bool access) const {
    if (access && busConflict(a)) return read(dmaSource_+(dmaIndex_?dmaIndex_-1:0));
    if (a<0x8000) {
        if (rom_.empty()) return 0xff;
        unsigned bank=a<0x4000?(mapper_==1 && bankMode_?romBank_&0x60:0):romBank_;
        return rom_[((size_t(bank)%(rom_.size()/0x4000))*0x4000)+(a&0x3fff)];
    }
    if (a<0xa000) { if (access && (io_[0x40]&0x80) && (io_[0x41]&3)==3) return 0xff; return vram_[(colour_?(io_[0x4f]&1)*0x2000:0)+(a&0x1fff)]; }
    if (a<0xc000) {
        if (!ramEnabled_ || !ramSize_ || (mapper_==3 && ramBank_>3)) return 0xff;
        unsigned bank=(mapper_==1 && !bankMode_)?0:ramBank_;
        return eram_[(size_t(bank)*0x2000+(a&0x1fff))%ramSize_];
    }
    if (a<0xe000) {
        unsigned bank=1; if (colour_) { bank=io_[0x70]&7;if (!bank) bank=1; }
        return wram_[a<0xd000?(a&0xfff):bank*0x1000+(a&0xfff)];
    }
    if (a<0xfe00) return read(a-0x2000,access);
    if (a<0xfea0) { if (access && (dmaTicks_ || ((io_[0x40]&0x80) && (io_[0x41]&3)>=2))) return 0xff;return oam_[a-0xfe00]; }
    if (a<0xff00) return 0xff;
    if (a>=0xff80) return a==0xffff?ie_:hram_[a-0xff80];
    auto i=a&0x7f;
    switch (i) {
        case 0: { uint8_t v=0xf;if (!(io_[0]&0x10)) v&=~(keys_>>4);if (!(io_[0]&0x20)) v&=~(keys_&15);return 0xc0|(io_[0]&0x30)|v; }
        case 2:return io_[2]|(colour_?0x7c:0x7e);
        case 4:return divider_>>8;
        case 7:return io_[7]|0xf8;
        case 0x0f:return io_[i]|0xe0;
        case 0x41:return io_[i]|0x80;
        case 0x4d:return colour_?0x7e|(doubleSpeed_?0x80:0)|(io_[i]&1):0xff;
        case 0x4f:return colour_?0xfe|(io_[i]&1):0xff;
        case 0x69:return colour_?bgPalette_[io_[0x68]&63]:0xff;
        case 0x6b:return colour_?objPalette_[io_[0x6a]&63]:0xff;
        case 0x70:return colour_?io_[i]|0xf8:0xff;
        default: if (!colour_ && i>=0x51 && i<=0x70) return 0xff;return io_[i];
    }
}
void GameBoy::write(uint16_t a,uint8_t v,bool access) {
    if (access && busConflict(a)) return;
    if (a<0x8000) {
        if (!mapper_) return;
        if (a<0x2000) ramEnabled_=(v&15)==10;
        else if (a<0x4000) {
            if (mapper_==1) romBank_=(romBank_&0x60)|((v&31)?v&31:1);
            else if (mapper_==3) romBank_=(v&0x7f)?v&0x7f:1;
            else if (a<0x3000) romBank_=(romBank_&0x100)|v;
            else romBank_=(romBank_&0xff)|((v&1)<<8);
        } else if (a<0x6000) {
            if (mapper_==1) { ramBank_=v&3;romBank_=(romBank_&31)|((v&3)<<5); }
            else ramBank_=mapper_==5?(v&(cartType_>=0x1c?7:15)):v&15;
        } else if (mapper_==1) bankMode_=v&1;
        return;
    }
    if (a<0xa000) { if (access && (io_[0x40]&0x80) && (io_[0x41]&3)==3) return;vram_[(colour_?(io_[0x4f]&1)*0x2000:0)+(a&0x1fff)]=v;return; }
    if (a<0xc000) { if (ramEnabled_ && ramSize_ && !(mapper_==3 && ramBank_>3)) { unsigned bank=mapper_==1&&!bankMode_?0:ramBank_;eram_[(size_t(bank)*0x2000+(a&0x1fff))%ramSize_]=v; }return; }
    if (a<0xe000) { unsigned bank=colour_?(io_[0x70]&7):1;if (!bank) bank=1;wram_[a<0xd000?(a&0xfff):bank*0x1000+(a&0xfff)]=v;return; }
    if (a<0xfe00) { write(a-0x2000,v,access);return; }
    if (a<0xfea0) { if (!access || (!dmaTicks_ && (!(io_[0x40]&0x80)||(io_[0x41]&3)<2))) oam_[a-0xfe00]=v;return; }
    if (a<0xff00) return;
    if (a>=0xff80) { if (a==0xffff) ie_=v;else hram_[a-0xff80]=v;return; }
    unsigned i=a&0x7f;
    switch(i) {
        case 0: { auto before=read(0xff00);io_[0]=v&0x30;if ((before&~read(0xff00)&15)) io_[0xf]|=0x10;break; }
        case 2: io_[2]=v;if ((v&0x81)==0x81) serialTicks_=colour_&&(v&2)?128:4096;break;
        case 4: { bool before=timerSignal();divider_=0;timerEdge(before);break; }
        case 5:if (!timerReloaded_) {io_[5]=v;timerReload_=0;}break;
        case 6:io_[6]=v;if (timerReloaded_) io_[5]=v;break;
        case 7: { bool before=timerSignal();io_[7]=v&7;timerEdge(before);break; }
        case 0xf:io_[i]=v&31;break;
        case 0x40: { bool was=io_[i]&0x80;io_[i]=v;if (was != bool(v&0x80)) { io_[0x44]=0;lineDot_=0;updateSTAT();if (!(v&0x80)) pixels_.fill(0xffffffff); }break; }
        case 0x41:io_[i]=(io_[i]&7)|(v&0x78);updateSTAT();break;
        case 0x44:break;
        case 0x45:io_[i]=v;updateSTAT();break;
        case 0x46:io_[i]=v;dmaPending_=uint16_t(v)<<8;dmaDelay_=8;break;
        case 0x4d:if (colour_) io_[i]=v&1;break;
        case 0x4f:if (colour_) io_[i]=v&1;break;
        case 0x55:
            if (colour_) {
                if (v&0x80) throw std::runtime_error("CGB HBlank DMA is not implemented in this prototype");
                unsigned src=uint16_t(io_[0x51])<<8|(io_[0x52]&0xf0),dst=0x8000|((io_[0x53]&31)<<8)|(io_[0x54]&0xf0);
                unsigned count=((v&127)+1)*16;
                for (unsigned n=0;n<count;++n) { auto b=read(uint16_t(src++));vram_[(io_[0x4f]&1)*0x2000+(dst++&0x1fff)]=b; }
                io_[0x51]=src>>8;io_[0x52]=src&0xf0;io_[0x53]=(dst>>8)&31;io_[0x54]=dst&0xf0;io_[i]=0xff;tick(count*(doubleSpeed_?4:2));
            }break;
        case 0x69:case 0x6b:
            if (colour_) { auto index=i==0x69?0x68:0x6a;auto& palette=i==0x69?bgPalette_:objPalette_;palette[io_[index]&63]=v;if (io_[index]&0x80) io_[index]=0x80|((io_[index]+1)&63); }break;
        case 0x68:case 0x6a:if (colour_) io_[i]=v&0xbf;break;
        case 0x70:if (colour_) io_[i]=v&7;break;
        default:io_[i]=v;break;
    }
}
void GameBoy::setKeys(uint16_t keys) { auto previous=read(0xff00);keys_=keys&255;if (previous&~read(0xff00)&15) io_[0xf]|=0x10;if (keys_) cpu_.stopped=false; }
bool GameBoy::timerSignal() const { const unsigned bit[]={9,3,5,7};return (io_[7]&4) && (divider_&(1u<<bit[io_[7]&3])); }
void GameBoy::timerEdge(bool previous) { if (previous && !timerSignal() && !timerReload_ && !timerReloaded_) { if (++io_[5]==0) timerReload_=4; } }
void GameBoy::updateSTAT() {
    const bool on=io_[0x40]&0x80;
    unsigned mode=!on?0:io_[0x44]>=144?1:lineDot_<80?2:lineDot_<252?3:0;
    io_[0x41]=(io_[0x41]&0x78)|mode|(io_[0x44]==io_[0x45]?4:0);
    bool signal=on && (((mode==0)&&(io_[0x41]&8)) || ((mode==1)&&(io_[0x41]&16)) || ((mode==2)&&(io_[0x41]&32)) || ((io_[0x41]&4)&&(io_[0x41]&64)));
    if (signal && !statLine_) io_[0xf]|=2;statLine_=signal;
}
void GameBoy::tick(unsigned cycles) {
    for (unsigned i=0;i<cycles;++i) {
        if (timerReloaded_) --timerReloaded_;
        if (timerReload_ && --timerReload_==0) { io_[5]=io_[6];io_[0xf]|=4;timerReloaded_=4; }
        bool before=timerSignal();++divider_;timerEdge(before);
        if (serialTicks_ && --serialTicks_==0) { serial_.push_back(char(io_[1]));io_[1]=0xff;io_[2]&=0x7f;io_[0xf]|=8; }
        if (dmaTicks_) { --dmaTicks_;if (!(dmaTicks_&3) && dmaIndex_<160) { oam_[dmaIndex_]=read(dmaSource_+dmaIndex_);++dmaIndex_; } }
        if (dmaDelay_ && --dmaDelay_==0) {dmaSource_=dmaPending_;dmaIndex_=0;dmaTicks_=640;}
        if (doubleSpeed_ && (++speedPhase_&1)) continue;
        ++stats_.cycles;
        if (!(io_[0x40]&0x80)) continue;
        ++lineDot_;
        if (lineDot_==252 && io_[0x44]<144) renderLine(io_[0x44]);
        if (lineDot_>=456) { lineDot_=0;if (++io_[0x44]==144) { io_[0xf]|=1;++stats_.frames; }if (io_[0x44]>=154) io_[0x44]=0; }
        if (lineDot_==0 || lineDot_==80 || lineDot_==252) updateSTAT();
    }
}
uint16_t GameBoy::pair(unsigned i) const { if (!i) return uint16_t(cpu_.b)<<8|cpu_.c;if (i==1) return uint16_t(cpu_.d)<<8|cpu_.e;if (i==2) return hl();return cpu_.sp; }
void GameBoy::pair(unsigned i,uint16_t v) { if (!i) {cpu_.b=v>>8;cpu_.c=v;}else if (i==1) {cpu_.d=v>>8;cpu_.e=v;}else if (i==2) hl(v);else cpu_.sp=v; }
uint8_t GameBoy::reg(unsigned i) { switch(i) {case 0:return cpu_.b;case 1:return cpu_.c;case 2:return cpu_.d;case 3:return cpu_.e;case 4:return cpu_.h;case 5:return cpu_.l;case 6:return rb(hl());default:return cpu_.a;} }
void GameBoy::reg(unsigned i,uint8_t v) { switch(i) {case 0:cpu_.b=v;break;case 1:cpu_.c=v;break;case 2:cpu_.d=v;break;case 3:cpu_.e=v;break;case 4:cpu_.h=v;break;case 5:cpu_.l=v;break;case 6:wb(hl(),v);break;default:cpu_.a=v;} }
bool GameBoy::condition(unsigned i) const { return i==0?!(cpu_.f&Z):i==1?bool(cpu_.f&Z):i==2?!(cpu_.f&C):bool(cpu_.f&C); }
uint8_t GameBoy::inc(uint8_t v) { auto r=uint8_t(v+1);cpu_.f=(cpu_.f&C)|(r==0?Z:0)|((v&15)==15?H:0);return r; }
uint8_t GameBoy::dec(uint8_t v) { auto r=uint8_t(v-1);cpu_.f=(cpu_.f&C)|N|(r==0?Z:0)|((v&15)==0?H:0);return r; }
void GameBoy::alu(unsigned op,uint8_t v) {
    const unsigned a=cpu_.a, carry=(cpu_.f&C)?1:0;
    unsigned r=0;uint8_t flags=0;
    switch(op) {
        case 0:case 1: { unsigned c=op==1?carry:0;r=a+v+c;flags=((a&15)+(v&15)+c>15?H:0)|(r>255?C:0);break; }
        case 2:case 3:case 7: { unsigned c=op==3?carry:0;r=a-v-c;flags=N|((a&15)<(v&15)+c?H:0)|(a<unsigned(v)+c?C:0);break; }
        case 4:r=a&v;flags=H;break;case 5:r=a^v;break;case 6:r=a|v;break;
    }
    cpu_.f=flags|((r&255)==0?Z:0);if (op!=7) cpu_.a=r;
}
uint8_t GameBoy::rotate(unsigned op,uint8_t value,bool zeros) {
    unsigned carry=0;uint8_t r=value;
    switch(op) {
        case 0:carry=value>>7;r=(value<<1)|carry;break;
        case 1:carry=value&1;r=(value>>1)|(carry<<7);break;
        case 2:carry=value>>7;r=(value<<1)|((cpu_.f&C)?1:0);break;
        case 3:carry=value&1;r=(value>>1)|((cpu_.f&C)?128:0);break;
        case 4:carry=value>>7;r=value<<1;break;
        case 5:carry=value&1;r=(value>>1)|(value&0x80);break;
        case 6:r=(value<<4)|(value>>4);break;
        case 7:carry=value&1;r=value>>1;break;
    }
    cpu_.f=(carry?C:0)|(zeros&&r==0?Z:0);return r;
}
unsigned GameBoy::step() {
    const auto start=stats_.cycles;
    uint8_t pending=ie_&io_[0xf]&31;
    if (pending) { cpu_.halted=false;cpu_.stopped=false; }
    if (pending && cpu_.ime) {
        unsigned bit=std::countr_zero(unsigned(pending));cpu_.ime=false;cpu_.imeDelay=0;io_[0xf]&=~(1<<bit);
        tick(8);push(cpu_.pc);tick(4);cpu_.pc=0x40+bit*8;
    } else if (cpu_.halted || cpu_.stopped) tick(4);
    else { auto op=fetch();execute(op);++stats_.instructions;if (cpu_.imeDelay && --cpu_.imeDelay==0) cpu_.ime=true; }
    cpu_.f&=0xf0;return unsigned(stats_.cycles-start);
}
void GameBoy::execute(uint8_t op) {
    unsigned x=op>>6,y=(op>>3)&7,z=op&7,p=y>>1,q=y&1;
    if (x==1) {
        if (op==0x76) { if (!cpu_.ime && (ie_&io_[0xf]&31)) cpu_.haltBug=true;else cpu_.halted=true; }
        else { auto v=reg(z);reg(y,v); }return;
    }
    if (x==2) { alu(y,reg(z));return; }
    if (x==0) {
        switch(z) {
            case 0:
                if (y==1) {auto a=fetch16();wb(a,cpu_.sp);wb(a+1,cpu_.sp>>8);}
                else if (y==2) {++cpu_.pc;if (colour_&&(io_[0x4d]&1)) {doubleSpeed_=!doubleSpeed_;io_[0x4d]=0;divider_=0;speedPhase_=0;}else cpu_.stopped=true;}
                else if (y>=3) {auto d=int8_t(fetch());if (y==3 || condition(y-4)) {cpu_.pc=uint16_t(cpu_.pc+d);tick(4);} }return;
            case 1:if (!q) pair(p,fetch16());else { unsigned a=hl(),v=pair(p),r=a+v;cpu_.f=(cpu_.f&Z)|((a&0xfff)+(v&0xfff)>0xfff?H:0)|(r>0xffff?C:0);hl(r);tick(4); }return;
            case 2: {uint16_t a=p<2?pair(p):hl();if (!q) wb(a,cpu_.a);else cpu_.a=rb(a);if (p>=2) hl(uint16_t(a+(p==2?1:-1)));return;}
            case 3:pair(p,uint16_t(pair(p)+(q?-1:1)));tick(4);return;
            case 4:{auto v=reg(y);reg(y,inc(v));return;}
            case 5:{auto v=reg(y);reg(y,dec(v));return;}
            case 6:{auto v=fetch();reg(y,v);return;}
            case 7:
                if (y<4) cpu_.a=rotate(y,cpu_.a,false);
                else if (y==4) {
                    unsigned a=cpu_.a,adjust=0;bool c=cpu_.f&C;
                    if (!(cpu_.f&N)) {if (c || a>0x99) {adjust|=0x60;c=true;}if ((cpu_.f&H)||(a&15)>9) adjust|=6;a+=adjust;}
                    else {if (c) adjust|=0x60;if (cpu_.f&H) adjust|=6;a-=adjust;}
                    cpu_.a=a;cpu_.f=(cpu_.f&N)|(c?C:0)|(cpu_.a==0?Z:0);
                } else if (y==5) {cpu_.a=~cpu_.a;cpu_.f|=N|H;}
                else if (y==6) cpu_.f=(cpu_.f&Z)|C;
                else cpu_.f=(cpu_.f&Z)|((cpu_.f&C)?0:C);
                return;
        }
    }
    switch(z) {
        case 0:
            if (y<4) {tick(4);if (condition(y)) {cpu_.pc=pop();tick(4);} }
            else if (y==4) {auto a=fetch();wb(0xff00|a,cpu_.a);}
            else if (y==6) {auto a=fetch();cpu_.a=rb(0xff00|a);}
            else {auto b=fetch();auto sp=cpu_.sp;auto value=uint16_t(sp+int8_t(b));cpu_.f=((sp&15)+(b&15)>15?H:0)|((sp&255)+b>255?C:0);tick(4);if (y==5) {cpu_.sp=value;tick(4);}else hl(value); }return;
        case 1:
            if (!q) {auto v=pop();if (p==3) {cpu_.a=v>>8;cpu_.f=v&0xf0;}else pair(p,v);}
            else if (p==0 || p==1) {cpu_.pc=pop();tick(4);if (p==1) {cpu_.ime=true;cpu_.imeDelay=0;} }
            else if (p==2) cpu_.pc=hl();
            else {cpu_.sp=hl();tick(4);}return;
        case 2:
            if (y<4) {auto a=fetch16();if (condition(y)) {cpu_.pc=a;tick(4);} }
            else if (y==4) wb(0xff00|cpu_.c,cpu_.a);
            else if (y==5) {auto a=fetch16();wb(a,cpu_.a);}
            else if (y==6) cpu_.a=rb(0xff00|cpu_.c);
            else {auto a=fetch16();cpu_.a=rb(a);}return;
        case 3:
            if (!y) {cpu_.pc=fetch16();tick(4);return;}
            if (y==1) {auto cb=fetch();unsigned group=cb>>6,operation=(cb>>3)&7,index=cb&7;auto v=reg(index);if (!group) reg(index,rotate(operation,v,true));else if (group==1) cpu_.f=(cpu_.f&C)|H|((v&(1<<operation))?0:Z);else reg(index,group==2?v&~(1<<operation):v|(1<<operation));return;}
            if (y==6) {cpu_.ime=false;cpu_.imeDelay=0;return;}
            if (y==7) {if (!cpu_.imeDelay) cpu_.imeDelay=2;return;}break;
        case 4:if (y<4) {auto a=fetch16();if (condition(y)) {tick(4);push(cpu_.pc);cpu_.pc=a;}return;}break;
        case 5:
            if (!q) {tick(4);push(p==3?(uint16_t(cpu_.a)<<8|cpu_.f):pair(p));return;}
            if (!p) {auto a=fetch16();tick(4);push(cpu_.pc);cpu_.pc=a;return;}break;
        case 6:alu(y,fetch());return;
        case 7:tick(4);push(cpu_.pc);cpu_.pc=y*8;return;
    }
    std::ostringstream error;error<<"Undefined GB opcode 0x"<<std::hex<<unsigned(op)<<" at 0x"<<uint16_t(cpu_.pc-1);throw std::runtime_error(error.str());
}
void GameBoy::renderLine(unsigned line) {
    const auto lcd=io_[0x40];std::array<uint8_t,160> bg{},priority{};
    const uint32_t grey[]={0xffffffff,0xffaaaaaa,0xff555555,0xff000000};
    auto pal=[&](const auto& data,unsigned index,unsigned shade) {unsigned offset=index*8+shade*2;return colour555(uint16_t(data[offset])|uint16_t(data[offset+1])<<8);};
    for (int x=0;x<160;++x) {
        bool window=(lcd&0x20) && line>=io_[0x4a] && x>=int(io_[0x4b])-7 && (colour_||(lcd&1));
        unsigned sx=window?x-(int(io_[0x4b])-7):(x+io_[0x43])&255,sy=window?line-io_[0x4a]:(line+io_[0x42])&255;
        unsigned map=(window?(lcd&0x40):(lcd&8))?0x1c00:0x1800;map+=(sy/8)*32+sx/8;
        uint8_t tile=vram_[map],attr=colour_?vram_[0x2000+map]:0;
        unsigned row=(attr&0x40)?7-(sy&7):sy&7,column=(attr&0x20)?sx&7:7-(sx&7);
        int tileBase=(lcd&0x10)?int(tile)*16:0x1000+int(int8_t(tile))*16;
        unsigned address=(attr&8?0x2000:0)+tileBase+row*2;
        unsigned shade=((vram_[address]>>column)&1)|(((vram_[address+1]>>column)&1)<<1);
        if (!colour_ && !(lcd&1)) shade=0;
        bg[x]=shade;priority[x]=attr>>7;
        pixels_[line*160+x]=colour_?pal(bgPalette_,attr&7,shade):grey[(io_[0x47]>>(shade*2))&3];
    }
    if (!(lcd&2)) return;
    std::vector<unsigned> sprites;unsigned height=(lcd&4)?16:8;
    for (unsigned i=0;i<40 && sprites.size()<10;++i) {int y=int(oam_[i*4])-16;if (int(line)>=y && int(line)<y+int(height)) sprites.push_back(i);}
    if (!colour_ || (io_[0x6c]&1)) std::stable_sort(sprites.begin(),sprites.end(),[&](auto a,auto b){return oam_[a*4+1]<oam_[b*4+1];});
    for (int x=0;x<160;++x) for (auto i:sprites) {
        int left=int(oam_[i*4+1])-8;if (x<left || x>=left+8) continue;
        auto attr=oam_[i*4+3];unsigned row=line-(int(oam_[i*4])-16),column=x-left;
        if (attr&0x40) row=height-1-row;if (!(attr&0x20)) column=7-column;
        unsigned tile=oam_[i*4+2];if (height==16) tile&=0xfe;
        unsigned address=tile*16+row*2+(colour_&&(attr&8)?0x2000:0);
        unsigned shade=((vram_[address]>>column)&1)|(((vram_[address+1]>>column)&1)<<1);if (!shade) continue;
        bool behind=colour_?bool((lcd&1) && bg[x] && (priority[x]||(attr&0x80))):bool(bg[x]&&(attr&0x80));
        if (!behind) pixels_[line*160+x]=colour_?pal(objPalette_,attr&7,shade):grey[(io_[attr&0x10?0x49:0x48]>>(shade*2))&3];
        break;
    }
}
std::vector<uint8_t> GameBoy::save() const {
    StateWriter w;w.number(0x31424743,4);w.number(colour_?2:1,1);w.number(fingerprint(rom_),8);w.number(frameDeadline_,8);
    for (auto n:{cpu_.a,cpu_.f,cpu_.b,cpu_.c,cpu_.d,cpu_.e,cpu_.h,cpu_.l}) w.number(n,1);
    w.number(cpu_.sp,2);w.number(cpu_.pc,2);w.number(cpu_.ime,1);w.number(cpu_.halted,1);w.number(cpu_.stopped,1);w.number(cpu_.haltBug,1);w.number(cpu_.imeDelay,1);
    w.number(stats_.cycles,8);w.number(stats_.instructions,8);w.number(stats_.frames,8);
    w.number(divider_,2);w.number(lineDot_,2);w.number(dmaTicks_,2);w.number(dmaIndex_,2);w.number(dmaSource_,2);w.number(dmaPending_,2);w.number(dmaDelay_,1);w.number(romBank_,2);
    for (auto n:{ramBank_,ie_,keys_,bankMode_}) w.number(n,1);
    w.number(ramEnabled_,1);w.number(statLine_,1);w.number(doubleSpeed_,1);w.number(speedPhase_,1);w.number(timerReload_,1);w.number(timerReloaded_,1);w.number(serialTicks_,2);
    w.block(vram_);w.block(wram_);w.block(eram_);w.block(oam_);w.block(io_);w.block(hram_);w.block(bgPalette_);w.block(objPalette_);
    for (auto p:pixels_) w.number(p,4);
    return protectState(std::move(w.bytes));
}
void GameBoy::restore(std::span<const uint8_t> data) {
    auto next=*this;StateReader r{checkedState(data)};
    if (r.number(4)!=0x31424743 || r.number(1)!=(colour_?2u:1u) || r.number(8)!=fingerprint(rom_)) throw std::runtime_error("State version, console or ROM does not match");
    next.frameDeadline_=r.number(8);
    for (auto p:{&next.cpu_.a,&next.cpu_.f,&next.cpu_.b,&next.cpu_.c,&next.cpu_.d,&next.cpu_.e,&next.cpu_.h,&next.cpu_.l}) *p=r.number(1);
    next.cpu_.sp=r.number(2);next.cpu_.pc=r.number(2);next.cpu_.ime=r.number(1);next.cpu_.halted=r.number(1);next.cpu_.stopped=r.number(1);next.cpu_.haltBug=r.number(1);next.cpu_.imeDelay=r.number(1);
    next.stats_.cycles=r.number(8);next.stats_.instructions=r.number(8);next.stats_.frames=r.number(8);
    next.divider_=r.number(2);next.lineDot_=r.number(2);next.dmaTicks_=r.number(2);next.dmaIndex_=r.number(2);next.dmaSource_=r.number(2);next.dmaPending_=r.number(2);next.dmaDelay_=r.number(1);next.romBank_=r.number(2);
    next.ramBank_=r.number(1);next.ie_=r.number(1);next.keys_=r.number(1);next.bankMode_=r.number(1);
    next.ramEnabled_=r.number(1);next.statLine_=r.number(1);next.doubleSpeed_=r.number(1);next.speedPhase_=r.number(1);next.timerReload_=r.number(1);next.timerReloaded_=r.number(1);next.serialTicks_=r.number(2);
    r.block(next.vram_);r.block(next.wram_);r.block(next.eram_);r.block(next.oam_);r.block(next.io_);r.block(next.hram_);r.block(next.bgPalette_);r.block(next.objPalette_);
    for (auto& p:next.pixels_) p=r.number(4);r.finish();
    if (next.stats_.cycles>UINT64_MAX-70224*2u || (next.frameDeadline_>next.stats_.cycles && next.frameDeadline_-next.stats_.cycles>70224)) throw std::runtime_error("Invalid state clock budget");
    if (next.lineDot_>=456 || next.io_[0x44]>=154 || next.dmaTicks_>640 || next.dmaIndex_>160 || next.dmaDelay_>8 || next.timerReloaded_>4 || next.romBank_>511 || next.ramBank_>15 || next.bankMode_>1 || next.timerReload_>4 || next.cpu_.imeDelay>2 || next.serialTicks_>4096 || next.speedPhase_>255 || (next.cpu_.f&15)) throw std::runtime_error("Invalid GB state fields");
    next.serial_.clear();*this=std::move(next);
}
}
