#define NOMINMAX
#include "mpvst/shared_memory.h"

#include <Windows.h>

#include <chrono>
#include <cstdio>

namespace mpvst {

SharedMemory::~SharedMemory() { close(); }

bool SharedMemory::create(const std::string& name, std::uint64_t bytes) noexcept
{
    close();
    const auto high = static_cast<DWORD>(bytes >> 32U);
    const auto low = static_cast<DWORD>(bytes & UINT64_C(0xffffffff));
    const auto handle = CreateFileMappingA(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                                           high, low, name.c_str());
    if (handle == nullptr || GetLastError() == ERROR_ALREADY_EXISTS)
    {
        if (handle != nullptr)
            CloseHandle(handle);
        return false;
    }
    data_ = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0,
                          static_cast<SIZE_T>(bytes));
    if (data_ == nullptr)
    {
        CloseHandle(handle);
        return false;
    }
    handle_ = handle;
    size_ = bytes;
    owner_ = true;
    name_ = name;
    return true;
}

bool SharedMemory::open(const std::string& name, std::uint64_t bytes) noexcept
{
    close();
    const auto handle = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name.c_str());
    if (handle == nullptr)
        return false;
    data_ = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0,
                          static_cast<SIZE_T>(bytes));
    if (data_ == nullptr)
    {
        CloseHandle(handle);
        return false;
    }
    handle_ = handle;
    size_ = bytes;
    name_ = name;
    return true;
}

void SharedMemory::close() noexcept
{
    if (data_ != nullptr)
        UnmapViewOfFile(data_);
    if (handle_ != nullptr)
        CloseHandle(static_cast<HANDLE>(handle_));
    data_ = nullptr;
    handle_ = nullptr;
    size_ = 0U;
    owner_ = false;
    name_.clear();
}

std::string uniqueMappingName()
{
    const auto tick = std::chrono::steady_clock::now().time_since_epoch().count();
    char buffer[96] {};
    std::snprintf(buffer, sizeof(buffer), "Local\\mpvst_%lu_%lld",
                  static_cast<unsigned long>(GetCurrentProcessId()),
                  static_cast<long long>(tick));
    return buffer;
}

} // namespace mpvst
