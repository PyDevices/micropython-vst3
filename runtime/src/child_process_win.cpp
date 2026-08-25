#define NOMINMAX
#include "mpvst/child_process.h"

#include <Windows.h>

namespace {

std::string quote(const std::string& value)
{
    std::string result = "\"";
    for (const char character : value)
    {
        if (character == '\"')
            result += '\\';
        result += character;
    }
    result += '\"';
    return result;
}

} // namespace

namespace mpvst {

ChildProcess::~ChildProcess() { terminate(); }

bool ChildProcess::start(const std::string& executable,
                         const std::vector<std::string>& arguments) noexcept
{
    if (process_ != nullptr)
        return false;
    std::string command = quote(executable);
    for (const auto& argument : arguments)
        command += " " + quote(argument);
    command.push_back('\0');

    STARTUPINFOA startup {};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION information {};
    if (!CreateProcessA(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, nullptr, &startup, &information))
        return false;
    CloseHandle(information.hThread);
    process_ = information.hProcess;
    process_id_ = information.dwProcessId;
    return true;
}

bool ChildProcess::running() noexcept
{
    return process_ != nullptr &&
           WaitForSingleObject(static_cast<HANDLE>(process_), 0) == WAIT_TIMEOUT;
}

bool ChildProcess::wait(std::uint32_t timeout_ms, int* exit_code) noexcept
{
    if (process_ == nullptr)
        return true;
    if (WaitForSingleObject(static_cast<HANDLE>(process_), timeout_ms) != WAIT_OBJECT_0)
        return false;
    DWORD code = 0;
    (void)GetExitCodeProcess(static_cast<HANDLE>(process_), &code);
    if (exit_code != nullptr)
        *exit_code = static_cast<int>(code);
    CloseHandle(static_cast<HANDLE>(process_));
    process_ = nullptr;
    process_id_ = 0U;
    return true;
}

void ChildProcess::terminate() noexcept
{
    if (process_ == nullptr)
        return;
    (void)TerminateProcess(static_cast<HANDLE>(process_), 1U);
    (void)WaitForSingleObject(static_cast<HANDLE>(process_), 2000U);
    CloseHandle(static_cast<HANDLE>(process_));
    process_ = nullptr;
    process_id_ = 0U;
}

} // namespace mpvst
