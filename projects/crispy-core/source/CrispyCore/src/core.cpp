#include "crispy/core.hpp"
#include "crispy/gb.hpp"
#include "crispy/gba.hpp"
#include <algorithm>
#include <cctype>
#include <stdexcept>
namespace crispy {
void Core::runFrame() {
    const auto period = capabilities().frameCycles;
    if (!frameDeadline_) frameDeadline_ = statistics().cycles;
    frameDeadline_ += period;
    while (statistics().cycles < frameDeadline_) {
        const auto before = statistics().cycles;
        step();
        if (statistics().cycles <= before) throw std::runtime_error("Core failed to advance its clock");
    }
}
std::unique_ptr<Core> makeCore(System system) {
    if (system == System::gba) return std::make_unique<GBA>();
    if (system == System::gb || system == System::gbc) return std::make_unique<GameBoy>(system == System::gbc);
    throw std::runtime_error("Unknown console type");
}
System systemForPath(const std::string& path) {
    auto dot = path.find_last_of('.');
    std::string extension = dot == std::string::npos ? "" : path.substr(dot);
    std::transform(extension.begin(),extension.end(),extension.begin(),[](unsigned char c){ return std::tolower(c); });
    if (extension == ".gb") return System::gb;
    if (extension == ".gbc") return System::gbc;
    if (extension == ".gba") return System::gba;
    throw std::runtime_error("Choose a .gb, .gbc or .gba ROM");
}
const char* systemName(System system) { return system == System::gba ? "GBA" : system == System::gbc ? "GBC" : "GB"; }
uint64_t fingerprint(std::span<const uint8_t> bytes) {
    uint64_t result = 14695981039346656037ull;
    for (auto b : bytes) { result ^= b; result *= 1099511628211ull; }
    return result; // identity check for prototype states, not a security primitive
}
uint32_t colour555(uint16_t value) {
    auto expand = [](unsigned c){ return (c << 3) | (c >> 2); };
    return 0xff000000u | expand(value&31) | (expand((value>>5)&31)<<8) | (expand((value>>10)&31)<<16);
}
namespace {
uint32_t stateCRC(std::span<const uint8_t> bytes) {
    uint32_t crc=0xffffffff;
    for (auto b:bytes) {crc^=b;for (unsigned bit=0;bit<8;++bit) crc=(crc>>1)^((crc&1)?0xedb88320u:0);}
    return ~crc;
}
}
std::vector<uint8_t> protectState(std::vector<uint8_t> bytes) {
    auto crc=stateCRC(bytes);for (unsigned i=0;i<4;++i) bytes.push_back(crc>>(8*i));return bytes;
}
std::span<const uint8_t> checkedState(std::span<const uint8_t> bytes) {
    if (bytes.size()<4) throw std::runtime_error("Truncated core state");
    auto payload=bytes.first(bytes.size()-4);uint32_t stored=0;for (unsigned i=0;i<4;++i) stored|=uint32_t(bytes[payload.size()+i])<<(8*i);
    if (stateCRC(payload)!=stored) throw std::runtime_error("Core state checksum failed; the file is corrupt");
    return payload;
}
void StateWriter::number(uint64_t v,unsigned width) { for (unsigned i=0;i<width;++i) bytes.push_back(uint8_t(v>>(i*8))); }
void StateWriter::block(std::span<const uint8_t> v) { bytes.insert(bytes.end(),v.begin(),v.end()); }
uint64_t StateReader::number(unsigned width) {
    if (width > 8 || position > bytes.size() || width > bytes.size()-position) throw std::runtime_error("Truncated core state");
    uint64_t v=0; for (unsigned i=0;i<width;++i) v |= uint64_t(bytes[position++]) << (i*8); return v;
}
void StateReader::block(std::span<uint8_t> destination) {
    if (position > bytes.size() || destination.size() > bytes.size()-position) throw std::runtime_error("Truncated core state");
    std::copy_n(bytes.begin()+position,destination.size(),destination.begin()); position += destination.size();
}
void StateReader::finish() const { if (position != bytes.size()) throw std::runtime_error("Unexpected data in core state"); }
}
