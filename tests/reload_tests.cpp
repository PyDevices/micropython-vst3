#include "sidecar_transport.h"

#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

namespace {

using PyDevices::MicroPythonVST3::SidecarTransport;

void setEnvironment(const char* name, const std::string& value)
{
    (void)_putenv_s(name, value.c_str());
}

bool writeScript(const std::filesystem::path& path, const char* source)
{
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output << source;
    return output.good();
}

bool waitForDiagnostic(SidecarTransport& transport, const char* expected)
{
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::seconds(2);
    while (std::chrono::steady_clock::now() < deadline)
    {
        if (transport.errorCode() != 0U &&
            transport.diagnostic().find(expected) != std::string::npos)
            return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return false;
}

bool waitForSignal(SidecarTransport& transport)
{
    for (std::uint32_t block = 0; block < 80U; ++block)
    {
        std::array<float, 64> left {};
        std::array<float, 64> right {};
        const auto rendered = transport.process(
            left.data(), right.data(), static_cast<std::uint32_t>(left.size()), false);
        if (rendered)
        {
            for (const auto sample : left)
            {
                if (std::isfinite(sample) && std::abs(sample) > 0.000001F)
                    return true;
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return false;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;

    const auto scriptPath = std::filesystem::temp_directory_path() /
        ("mpvst-reload-" + std::to_string(GetCurrentProcessId()) + ".py");
    setEnvironment("MPVST_ENGINE_PATH", argv[1]);
    setEnvironment("MPVST_SCRIPT_PATH", scriptPath.string());

    if (!writeScript(scriptPath, "def broken(:\n"))
        return 3;

    SidecarTransport transport;
    transport.configure(48000.0, 64U, 256U);
    if (!transport.start())
        return 4;
    if (!waitForDiagnostic(transport, "SyntaxError"))
    {
        std::cerr << "initial syntax error was not reported: "
                  << transport.diagnostic() << '\n';
        return 5;
    }

    if (!writeScript(scriptPath, "raise RuntimeError('reload runtime test')\n") ||
        !transport.requestReload() ||
        !waitForDiagnostic(transport, "RuntimeError"))
    {
        std::cerr << "runtime error reload was not reported: "
                  << transport.diagnostic() << '\n';
        return 6;
    }

    constexpr auto validScript =
        "import synthio\n"
        "import vstaudio\n"
        "synth = synthio.Synthesizer(sample_rate=vstaudio.sample_rate())\n"
        "synth.press(synthio.Note(220.0))\n"
        "vstaudio.output(synth)\n";
    if (!writeScript(scriptPath, validScript) || !transport.requestReload() ||
        !waitForSignal(transport) || transport.errorCode() != 0U)
    {
        std::cerr << "corrected script did not recover: "
                  << transport.diagnostic() << '\n';
        return 7;
    }

    transport.stop();
    std::error_code ignored;
    (void)std::filesystem::remove(scriptPath, ignored);
    setEnvironment("MPVST_SCRIPT_PATH", "");
    std::cout << "syntax error, runtime error, and in-instance reload recovery passed\n";
    return 0;
}
