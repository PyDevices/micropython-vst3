#pragma once

#include <stdint.h>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

namespace mpvst {

inline uint64_t acquire_load_u64(const uint64_t* value) noexcept
{
#if defined(_MSC_VER)
    return static_cast<uint64_t>(_InterlockedCompareExchange64(
        reinterpret_cast<volatile long long*>(const_cast<uint64_t*>(value)), 0, 0));
#else
    return __atomic_load_n(value, __ATOMIC_ACQUIRE);
#endif
}

inline void release_store_u64(uint64_t* value, uint64_t desired) noexcept
{
#if defined(_MSC_VER)
    (void)_InterlockedExchange64(reinterpret_cast<volatile long long*>(value),
                                 static_cast<long long>(desired));
#else
    __atomic_store_n(value, desired, __ATOMIC_RELEASE);
#endif
}

inline uint64_t relaxed_fetch_add_u64(uint64_t* value, uint64_t amount) noexcept
{
#if defined(_MSC_VER)
    return static_cast<uint64_t>(_InterlockedExchangeAdd64(
        reinterpret_cast<volatile long long*>(value), static_cast<long long>(amount)));
#else
    return __atomic_fetch_add(value, amount, __ATOMIC_RELAXED);
#endif
}

inline uint32_t acquire_load_u32(const uint32_t* value) noexcept
{
#if defined(_MSC_VER)
    return static_cast<uint32_t>(_InterlockedCompareExchange(
        reinterpret_cast<volatile long*>(const_cast<uint32_t*>(value)), 0, 0));
#else
    return __atomic_load_n(value, __ATOMIC_ACQUIRE);
#endif
}

inline void release_store_u32(uint32_t* value, uint32_t desired) noexcept
{
#if defined(_MSC_VER)
    (void)_InterlockedExchange(reinterpret_cast<volatile long*>(value),
                               static_cast<long>(desired));
#else
    __atomic_store_n(value, desired, __ATOMIC_RELEASE);
#endif
}

} // namespace mpvst
