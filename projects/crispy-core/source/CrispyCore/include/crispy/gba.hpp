#pragma once
#include "core.hpp"
namespace crispy {
struct ARMRegisters { std::array<uint32_t,16> r{};uint32_t cpsr=0x1f;bool halted=false;
    // Active registers live in r; these arrays retain inactive physical banks.
    std::array<uint32_t,5> userHigh{},fiqHigh{};
    std::array<std::array<uint32_t,2>,6> banked{}; // user/system, FIQ, IRQ, SVC, abort, undefined
    std::array<uint32_t,6> spsr{}; // bank zero has no SPSR
 };
class GBA final : public Core {
public:
    GBA() { reset(); }
    Capabilities capabilities() const override { return {System::gba,240,160,16777216,280896}; }
    void load(std::span<const uint8_t>) override;
    void reset() override;
    unsigned step() override;
    void setKeys(uint16_t) override;
    std::span<const uint32_t> pixels() const override { return pixels_; }
    std::span<const uint8_t> battery() const override { return saveType_==SaveType::none?std::span<const uint8_t>{}:std::span<const uint8_t>(battery_,saveSize_); }
    void restoreBattery(std::span<const uint8_t>) override;
    // Cartridge save-chip type, for diagnostics and tests. Zero is "no chip".
    enum class SaveType : uint8_t { none=0, sram=1, flash=2, eeprom=3 };
    SaveType saveChipType() const { return saveType_; }
    std::vector<uint8_t> save() const override;
    void restore(std::span<const uint8_t>) override;
    std::string title() const override;
    uint8_t inspect(uint32_t a) const override { return read8(a); }
    void debugWrite(uint32_t a,uint8_t v) override { write8(a,v);pipelineValid_=false; }
    Statistics statistics() const override { return stats_; }
    ARMRegisters& debugRegisters() { return cpu_; }
    uint32_t debugRead32(uint32_t a) const { return read32(a); }
    uint16_t debugIO16(unsigned offset) const { return io16(offset&0x3fe); }
private:
    friend struct GBAConformanceAccess;
    static constexpr uint32_t N=1u<<31,Z=1u<<30,C=1u<<29,V=1u<<28,T=1u<<5;
    std::vector<uint8_t> rom_;
    std::array<uint8_t,0x40000> ewram_{};
    std::array<uint8_t,0x8000> iwram_{};
    std::array<uint8_t,0x400> io_{},palette_{},oam_{};
    std::array<uint8_t,0x18000> vram_{};
    std::array<uint32_t,240*160> pixels_{};
    ARMRegisters cpu_;
    Statistics stats_;
    unsigned lineCycle_=0,line_=0;
    std::array<uint16_t,4> timerReload_{};
    std::array<uint32_t,4> timerPhase_{};
    bool dmaBusy_=false;
    struct BIOSWait { uint16_t mask;uint32_t status,pc,waitStatus,waitPC,svcFrame=0; };
    static constexpr unsigned maxBIOSWaits=16;
    static constexpr uint32_t waitAddress=0x140;
    std::vector<BIOSWait> biosWaits_;
    uint32_t biosLatch_=0xe129f000;
    std::array<uint32_t,2> pipeline_{};
    uint32_t pipelineAddress_=0,openBus_=0;
    bool pipelineValid_=false,pipelineThumb_=false;
    uint32_t fetchOpcode(uint32_t address,bool thumb);
    static int ioReadMask(unsigned offset);

    // Functional cartridge save-chip model. SRAM mirrors within the 1 MiB
    // cartridge window; Flash follows the 0xAA/0x55 command dance with bank
    // switching, program, sector/whole erase and read-id. EEPROM/E-reader
    // chips are detected but their bit-serial protocol faults explicitly.
    void detectSave();
    uint8_t readSave8(uint32_t address) const;
    void saveWrite8(uint32_t address,uint8_t value);
    void flashCommandWrite(uint32_t address,uint8_t value);
    uint8_t flashRead(uint32_t address) const;
    SaveType saveType_=SaveType::none;
    uint32_t saveSize_=0;
    std::vector<uint8_t> battery_;
    enum class FlashMode : uint8_t { raw=0, start=1, continue_=2 };
    enum class FlashOp : uint8_t { none=0, erase=1, id=2, program=3, switchBank=4 };
    FlashMode flashMode_=FlashMode::raw;
    FlashOp flashOp_=FlashOp::none;
    uint8_t flashBank_=0;
    uint32_t flashBusy_=0;

    uint8_t read8(uint32_t) const;
    uint16_t read16(uint32_t) const;
    uint32_t read32(uint32_t) const;
    void write8(uint32_t,uint8_t);
    void write16(uint32_t,uint16_t);
    void write32(uint32_t,uint32_t);
    uint16_t io16(unsigned offset) const { return io_[offset]|uint16_t(io_[offset+1])<<8; }
    void io16(unsigned offset,uint16_t value) { io_[offset]=value;io_[offset+1]=value>>8; }
    uint32_t io32(unsigned offset) const { return io16(offset)|uint32_t(io16(offset+2))<<16; }
    void tick(unsigned cycles);
    void renderLine(unsigned y);
    void dma(unsigned timing);
    static int modeBank(uint32_t);
    void setCPSR(uint32_t);
    void enterException(uint32_t mode,uint32_t vector,uint32_t link);
    uint32_t pushSVCFrame();
    void returnSVCFrame(uint32_t address);
    unsigned undefinedInstruction(uint32_t pc);
    unsigned decompress(unsigned service,uint32_t opcode,uint32_t pc);
    unsigned softwareInterrupt(unsigned service,uint32_t opcode,uint32_t pc);
    static uint32_t firmwareWord(uint32_t address);
    static bool firmwareInstruction(uint32_t address);
    uint32_t savedPSR(uint32_t opcode,uint32_t pc) const;
    uint32_t& userRegister(unsigned);
    bool condition(unsigned) const;
    void nz(uint32_t);
    uint32_t add(uint32_t,uint32_t,bool,bool);
    uint32_t shift(uint32_t,unsigned,unsigned,bool,bool&);
    unsigned arm(uint32_t,uint32_t);
    unsigned thumb(uint16_t,uint32_t);
    [[noreturn]] void unsupported(uint32_t opcode,uint32_t pc,const char* why) const;
};
}
