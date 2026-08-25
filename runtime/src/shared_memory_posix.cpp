#include "mpvst/shared_memory.h"

#include <chrono>
#include <cstdio>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace mpvst {

SharedMemory::~SharedMemory() { close(); }

bool SharedMemory::create(const std::string& name, std::uint64_t bytes) noexcept
{
    close();
    if (name.empty() || bytes == 0U)
        return false;
    const int descriptor = shm_open(name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0600);
    if (descriptor < 0)
        return false;
    if (ftruncate(descriptor, static_cast<off_t>(bytes)) != 0)
    {
        ::close(descriptor);
        shm_unlink(name.c_str());
        return false;
    }
    data_ = mmap(nullptr, static_cast<std::size_t>(bytes), PROT_READ | PROT_WRITE,
                 MAP_SHARED, descriptor, 0);
    ::close(descriptor);
    if (data_ == MAP_FAILED)
    {
        data_ = nullptr;
        shm_unlink(name.c_str());
        return false;
    }
    size_ = bytes;
    owner_ = true;
    name_ = name;
    return true;
}

bool SharedMemory::open(const std::string& name, std::uint64_t bytes) noexcept
{
    close();
    const int descriptor = shm_open(name.c_str(), O_RDWR, 0600);
    if (descriptor < 0)
        return false;
    data_ = mmap(nullptr, static_cast<std::size_t>(bytes), PROT_READ | PROT_WRITE,
                 MAP_SHARED, descriptor, 0);
    ::close(descriptor);
    if (data_ == MAP_FAILED)
    {
        data_ = nullptr;
        return false;
    }
    size_ = bytes;
    name_ = name;
    return true;
}

void SharedMemory::close() noexcept
{
    if (data_ != nullptr)
        munmap(data_, static_cast<std::size_t>(size_));
    if (owner_ && !name_.empty())
        shm_unlink(name_.c_str());
    data_ = nullptr;
    size_ = 0U;
    owner_ = false;
    name_.clear();
}

std::string uniqueMappingName()
{
    const auto tick = std::chrono::steady_clock::now().time_since_epoch().count();
    char buffer[96] {};
    std::snprintf(buffer, sizeof(buffer), "/mpvst_%ld_%lld", static_cast<long>(getpid()),
                  static_cast<long long>(tick));
    return buffer;
}

} // namespace mpvst
