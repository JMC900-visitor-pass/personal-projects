#pragma once
#include "core.hpp"
namespace crispy {
struct GBRegisters {
    uint8_t a=1,f=0xb0,b=0,c=0x13,d=0,e=0xd8,h=1,l=0x4d;
    uint16_t sp=0xfffe,pc=0x100;
    bool ime=false,halted=false,stopped=false,haltBug=false;
    uint8_t imeDelay=0;
};
class GameBoy final : public Core {
public:
    explicit GameBoy(bool colour=false): colour_(colour) { reset(); }
    Capabilities capabilities() const override;
    void load(std::span<const uint8_t>) override;
    void reset() override;
    unsigned step() override;
    void setKeys(uint16_t) override;
    std::span<const uint32_t> pixels() const override { return pixels_; }
    std::span<const uint8_t> battery() const override;
    void restoreBattery(std::span<const uint8_t>) override;
    std::vector<uint8_t> save() const override;
    void restore(std::span<const uint8_t>) override;
    std::string title() const override;
    uint8_t inspect(uint32_t a) const override { return read(uint16_t(a)); }
    void debugWrite(uint32_t a,uint8_t v) override { write(uint16_t(a),v); }
    Statistics statistics() const override { return stats_; }
    GBRegisters& debugRegisters() { return cpu_; }
    const std::string& serialOutput() const { return serial_; }
private:
    static constexpr uint8_t Z=0x80,N=0x40,H=0x20,C=0x10;
    bool colour_;
    std::vector<uint8_t> rom_;
    std::array<uint8_t,0x4000> vram_{};
    std::array<uint8_t,0x8000> wram_{};
    std::array<uint8_t,0x20000> eram_{};
    std::array<uint8_t,0xa0> oam_{};
    std::array<uint8_t,0x80> io_{};
    std::array<uint8_t,0x7f> hram_{};
    std::array<uint8_t,64> bgPalette_{},objPalette_{};
    std::array<uint32_t,160*144> pixels_{};
    GBRegisters cpu_;
    Statistics stats_;
    uint16_t divider_=0;
    unsigned lineDot_=0,dmaTicks_=0,dmaIndex_=0,dmaDelay_=0;
    uint16_t dmaSource_=0,dmaPending_=0,romBank_=1;
    uint8_t ramBank_=0,mapper_=0,cartType_=0,ie_=0,keys_=0,bankMode_=0;
    bool ramEnabled_=false,statLine_=false,doubleSpeed_=false;
    unsigned speedPhase_=0;
    int timerReload_=0,timerReloaded_=0,serialTicks_=0;
    size_t ramSize_=0;
    std::string serial_;
    uint8_t read(uint16_t,bool cpuAccess=false) const;
    void write(uint16_t,uint8_t,bool cpuAccess=false);
    void tick(unsigned cycles);
    bool busConflict(uint16_t) const;
    bool timerSignal() const;
    void timerEdge(bool previous);
    void updateSTAT();
    void renderLine(unsigned line);
    uint8_t rb(uint16_t address) { auto v=read(address,true); tick(4); return v; }
    void wb(uint16_t address,uint8_t v) { write(address,v,true); tick(4); }
    uint8_t fetch() { auto v=rb(cpu_.pc); if (cpu_.haltBug) cpu_.haltBug=false; else ++cpu_.pc; return v; }
    uint16_t fetch16() { auto lo=fetch(); return uint16_t(lo | uint16_t(fetch())<<8); }
    uint16_t hl() const { return uint16_t(cpu_.h)<<8 | cpu_.l; }
    void hl(uint16_t v) { cpu_.h=v>>8; cpu_.l=v; }
    uint16_t pair(unsigned index) const;
    void pair(unsigned index,uint16_t v);
    uint8_t reg(unsigned index);
    void reg(unsigned index,uint8_t v);
    void push(uint16_t v) { wb(--cpu_.sp,v>>8); wb(--cpu_.sp,v); }
    uint16_t pop() { auto lo=rb(cpu_.sp++); return lo | uint16_t(rb(cpu_.sp++))<<8; }
    bool condition(unsigned index) const;
    void alu(unsigned operation,uint8_t value);
    uint8_t inc(uint8_t),dec(uint8_t),rotate(unsigned,uint8_t,bool);
    void execute(uint8_t opcode);
};
}
