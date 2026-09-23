#pragma once
#include <cstdint>
#include <optional>
#include <vector>

namespace aurora::stream {

struct Packet {
    std::uint32_t sequence{};
    std::uint8_t track_id{};
    std::uint8_t flags{};
    std::uint64_t pts{};
    std::uint64_t duration{};
    std::vector<std::uint8_t> payload;
};

std::vector<std::uint8_t> encode(const Packet& p);
Packet decode(const std::vector<std::uint8_t>& wire);

class IncrementalParser {
public:
    void push(const std::uint8_t* data,std::size_t size);
    void push(const std::vector<std::uint8_t>& data) { push(data.data(),data.size()); }
    std::optional<Packet> pop();
    std::size_t buffered() const noexcept { return buffer_.size(); }
private:
    std::vector<std::uint8_t> buffer_;
};

class OrderedReceiver {
public:
    Packet accept(const std::vector<std::uint8_t>& wire);
    std::uint32_t next_sequence() const noexcept { return next_; }
private:
    std::uint32_t next_{0};
};

} // namespace aurora::stream
