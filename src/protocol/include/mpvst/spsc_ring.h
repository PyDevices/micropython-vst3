#pragma once

#include "mpvst/atomic.h"

#include <cstdint>

namespace mpvst {

// Dmitry Vyukov-style bounded sequence ownership specialized to one producer
// and one consumer. Endpoints keep their cursor locally; a full or empty ring
// returns immediately and never spins.
template <typename Slot>
inline Slot* try_acquire_producer(Slot* slots, std::uint32_t count,
                                  std::uint64_t position) noexcept
{
    auto* slot = &slots[position % count];
    return acquire_load_u64(&slot->sequence) == position ? slot : nullptr;
}

template <typename Slot>
inline void publish_producer(Slot* slot, std::uint64_t position) noexcept
{
    release_store_u64(&slot->sequence, position + 1U);
}

template <typename Slot>
inline Slot* try_acquire_consumer(Slot* slots, std::uint32_t count,
                                  std::uint64_t position) noexcept
{
    auto* slot = &slots[position % count];
    return acquire_load_u64(&slot->sequence) == position + 1U ? slot : nullptr;
}

template <typename Slot>
inline void release_consumer(Slot* slot, std::uint32_t count,
                             std::uint64_t position) noexcept
{
    release_store_u64(&slot->sequence, position + count);
}

} // namespace mpvst
