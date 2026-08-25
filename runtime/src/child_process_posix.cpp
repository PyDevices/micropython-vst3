#include "mpvst/child_process.h"

#include <chrono>
#include <csignal>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>

namespace mpvst {

ChildProcess::~ChildProcess() { terminate(); }

bool ChildProcess::start(const std::string& executable,
                         const std::vector<std::string>& arguments) noexcept
{
    if (process_id_ != 0U)
        return false;
    const auto child = fork();
    if (child < 0)
        return false;
    if (child == 0)
    {
        std::vector<char*> argv;
        argv.reserve(arguments.size() + 2U);
        argv.push_back(const_cast<char*>(executable.c_str()));
        for (const auto& argument : arguments)
            argv.push_back(const_cast<char*>(argument.c_str()));
        argv.push_back(nullptr);
        execv(executable.c_str(), argv.data());
        _exit(127);
    }
    process_id_ = static_cast<std::uint64_t>(child);
    return true;
}

bool ChildProcess::running() noexcept
{
    if (process_id_ == 0U)
        return false;
    int status = 0;
    const auto result = waitpid(static_cast<pid_t>(process_id_), &status, WNOHANG);
    if (result == 0)
        return true;
    if (result > 0)
        process_id_ = 0U;
    return false;
}

bool ChildProcess::wait(std::uint32_t timeout_ms, int* exit_code) noexcept
{
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(timeout_ms);
    while (process_id_ != 0U)
    {
        int status = 0;
        const auto result = waitpid(static_cast<pid_t>(process_id_), &status, WNOHANG);
        if (result > 0)
        {
            if (exit_code != nullptr)
                *exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
            process_id_ = 0U;
            return true;
        }
        if (result < 0 || std::chrono::steady_clock::now() >= deadline)
            return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return true;
}

void ChildProcess::terminate() noexcept
{
    if (process_id_ == 0U)
        return;
    (void)kill(static_cast<pid_t>(process_id_), SIGKILL);
    int status = 0;
    (void)waitpid(static_cast<pid_t>(process_id_), &status, 0);
    process_id_ = 0U;
}

} // namespace mpvst
