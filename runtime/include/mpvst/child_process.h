#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace mpvst {

class ChildProcess final
{
public:
    ChildProcess() = default;
    ~ChildProcess();
    ChildProcess(const ChildProcess&) = delete;
    ChildProcess& operator=(const ChildProcess&) = delete;

    bool start(const std::string& executable,
               const std::vector<std::string>& arguments) noexcept;
    bool running() noexcept;
    bool wait(std::uint32_t timeout_ms, int* exit_code = nullptr) noexcept;
    void terminate() noexcept;

private:
    void* process_ = nullptr;
    std::uint64_t process_id_ = 0;
};

} // namespace mpvst
