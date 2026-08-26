#pragma once

#include <cstdint>
#include <string>

namespace mpvst {

class SharedMemory final
{
public:
    SharedMemory() = default;
    ~SharedMemory();
    SharedMemory(const SharedMemory&) = delete;
    SharedMemory& operator=(const SharedMemory&) = delete;

    bool create(const std::string& name, std::uint64_t bytes) noexcept;
    bool open(const std::string& name, std::uint64_t bytes) noexcept;
    void close() noexcept;

    void* data() const noexcept { return data_; }
    std::uint64_t size() const noexcept { return size_; }
    bool owner() const noexcept { return owner_; }

private:
    void* data_ = nullptr;
    void* handle_ = nullptr;
    std::uint64_t size_ = 0;
    bool owner_ = false;
    std::string name_;
};

std::string uniqueMappingName();

} // namespace mpvst
