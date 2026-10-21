#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <vector>

namespace crispy {
enum class System : uint8_t { gb = 1, gbc = 2, gba = 3 };
struct Capabilities {
    System system;
    unsigned width, height;
    uint32_t clockHz, frameCycles;
    bool audio = false;
    const char* stage = "experimental bring-up";
};
struct Statistics { uint64_t cycles = 0, instructions = 0, frames = 0; };
// Platform-free boundary: no Cocoa, Metal, GameController or mGBA types.
class Core {
public:
    virtual ~Core() = default;
    virtual Capabilities capabilities() const = 0;
    virtual void load(std::span<const uint8_t> rom) = 0;
    virtual void reset() = 0;
    virtual unsigned step() = 0;
    virtual void setKeys(uint16_t keys) = 0;
    virtual std::span<const uint32_t> pixels() const = 0;
    virtual std::span<const uint8_t> battery() const = 0;
    virtual void restoreBattery(std::span<const uint8_t>) = 0;
    virtual std::vector<uint8_t> save() const = 0;
    virtual void restore(std::span<const uint8_t>) = 0;
    virtual std::string title() const = 0;
    virtual uint8_t inspect(uint32_t address) const = 0;
    virtual void debugWrite(uint32_t address, uint8_t value) = 0;
    virtual Statistics statistics() const = 0;
    // Bounded even if LCD is disabled or the CPU is halted. Carry excess cycles
    // into the next call; a frame budget never discards a CPU instruction.
    void runFrame();
protected:
    uint64_t frameDeadline_ = 0;
};
std::unique_ptr<Core> makeCore(System system);
System systemForPath(const std::string& path);
const char* systemName(System system);
uint64_t fingerprint(std::span<const uint8_t> bytes);
uint32_t colour555(uint16_t value);
std::vector<uint8_t> protectState(std::vector<uint8_t> bytes);
std::span<const uint8_t> checkedState(std::span<const uint8_t> bytes);

struct StateWriter {
    std::vector<uint8_t> bytes;
    void number(uint64_t value, unsigned width);
    void block(std::span<const uint8_t> value);
};
struct StateReader {
    std::span<const uint8_t> bytes;
    size_t position = 0;
    uint64_t number(unsigned width);
    void block(std::span<uint8_t> destination);
    void finish() const;
};
}
