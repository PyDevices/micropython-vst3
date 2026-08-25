#include "sidecar_transport.h"

#include "mpvst/atomic.h"
#include "mpvst/spsc_ring.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <thread>
#include <vector>

#if defined(_WIN32)
#define NOMINMAX
#include <Windows.h>
#else
#include <dlfcn.h>
#endif

namespace PyDevices::MicroPythonVST3 {

namespace {

constexpr std::uint32_t kSlotCount = 8U;
constexpr std::uint32_t kEventCapacity = 256U;
constexpr std::uint32_t kCommandCapacity = 8U;
constexpr std::size_t kMaximumScriptBytes = 1024U * 1024U;
// Reported as the last exit code when the supervisor kills a stalled engine
// rather than finding one that exited by itself. No real process status uses
// it, so telemetry can tell a hang apart from a crash.
constexpr std::int32_t kStalledExitCode = -1000;

std::string environmentValue(const char* name)
{
#if defined(_WIN32)
    char* value = nullptr;
    std::size_t size = 0;
    if (_dupenv_s(&value, &size, name) != 0 || value == nullptr)
        return {};
    std::string result(value);
    std::free(value);
    return result;
#else
    const auto* value = std::getenv(name);
    return value == nullptr ? std::string {} : std::string {value};
#endif
}

std::string readScript(const std::filesystem::path& path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input)
        return {};
    input.seekg(0, std::ios::end);
    const auto size = input.tellg();
    if (size < 0 || static_cast<std::uint64_t> (size) > kMaximumScriptBytes)
        return {};
    input.seekg(0, std::ios::beg);
    std::string result(static_cast<std::size_t> (size), '\0');
    if (!result.empty() &&
        !input.read(result.data(), static_cast<std::streamsize> (result.size())))
        return {};
    return result;
}

} // namespace

SidecarTransport::~SidecarTransport() { stop(); }

std::string SidecarTransport::initialScriptSource()
{
    const auto enginePath = nativeEnginePath();
    if (std::filesystem::path(enginePath).stem().string() !=
        "micropython-vst-engine")
        return {};
    const auto overridePath = environmentValue("MPVST_SCRIPT_PATH");
    const auto path = overridePath.empty()
        ? std::filesystem::path(enginePath).parent_path() / "default_instrument.py"
        : std::filesystem::path(overridePath);
    return readScript(path);
}

void SidecarTransport::setScriptSource(std::string source, ScriptOrigin origin)
{
    scriptSource_ = std::move(source);
    scriptOrigin_ = origin;
}

std::string SidecarTransport::developerScriptPath()
{
    const auto enginePath = nativeEnginePath();
    if (std::filesystem::path(enginePath).stem().string() !=
        "micropython-vst-engine")
        return {};
    const auto overridePath = environmentValue("MPVST_SCRIPT_PATH");
    if (overridePath.empty())
        return {};
    std::error_code ignored;
    if (!std::filesystem::exists(overridePath, ignored))
        return {};
    return overridePath;
}

std::string SidecarTransport::refreshDeveloperScriptSource()
{
    if (scriptOrigin_ != ScriptOrigin::DeveloperFile)
        return scriptSource_;
    const auto path = developerScriptPath();
    if (path.empty())
        return scriptSource_;
    auto latest = readScript(path);
    if (!latest.empty())
        scriptSource_ = std::move(latest);
    return scriptSource_;
}

void SidecarTransport::configure(double sampleRate, std::uint32_t maxFrames,
                                 std::uint32_t latencySamples) noexcept
{
    sampleRate_ = sampleRate;
    sampleRateMillihz_ = static_cast<std::uint64_t>(std::llround(sampleRate * 1000.0));
    maxFrames_ = maxFrames;
    latencySamples_ = latencySamples;
}

std::string SidecarTransport::nativeEnginePath()
{
    const auto overridePath = environmentValue("MPVST_ENGINE_PATH");
    if (!overridePath.empty())
        return overridePath;

#if defined(_WIN32)
    HMODULE module = nullptr;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            reinterpret_cast<LPCSTR>(&SidecarTransport::nativeEnginePath),
                            &module))
        return {};
    std::string path(32768U, '\0');
    const auto length = GetModuleFileNameA(module, path.data(),
                                           static_cast<DWORD>(path.size()));
    if (length == 0U || length >= path.size())
        return {};
    path.resize(length);
    const auto directory = std::filesystem::path(path).parent_path();
    const auto micropythonEngine = directory / "micropython-vst-engine.exe";
    if (std::filesystem::exists(micropythonEngine))
        return micropythonEngine.string();
    return (directory / "micropython-vst-native-engine.exe").string();
#else
    Dl_info information {};
    if (dladdr(reinterpret_cast<const void*>(&SidecarTransport::nativeEnginePath),
               &information) == 0 || information.dli_fname == nullptr)
        return {};
    const auto directory = std::filesystem::path(information.dli_fname).parent_path();
    const auto micropythonEngine = directory / "micropython-vst-engine";
    if (std::filesystem::exists(micropythonEngine))
        return micropythonEngine.string();
    return (directory / "micropython-vst-native-engine").string();
#endif
}

bool SidecarTransport::start()
{
    stop();
    if (maxFrames_ == 0U)
        return false;

    const mpvst_layout_request request {maxFrames_, kSlotCount, kSlotCount,
                                        kEventCapacity, kCommandCapacity};
    mappingBytes_ = mpvst_compute_mapping_bytes(&request);
    mappingName_ = mpvst::uniqueMappingName();
    instanceNonce_ = static_cast<std::uint64_t>(
        std::chrono::steady_clock::now().time_since_epoch().count());
    if (!mapping_.create(mappingName_, mappingBytes_) ||
        !mpvst_initialize_mapping(mapping_.data(), mappingBytes_, &request,
                                  instanceNonce_))
    {
        stop();
        return false;
    }

    header_ = static_cast<mpvst_shared_header*>(mapping_.data());
    header_->sample_rate_millihz = sampleRateMillihz_;
    status_ = static_cast<mpvst_status*>(mpvst_region(mapping_.data(),
                                                       header_->status_offset));
    commands_ = static_cast<mpvst_command*>(mpvst_region(mapping_.data(),
                                                          header_->commands_offset));
    events_ = static_cast<mpvst_event*>(mpvst_region(mapping_.data(),
                                                      header_->events_offset));
    work_ = static_cast<mpvst_work_slot*>(mpvst_region(mapping_.data(),
                                                        header_->work_offset));

    if (!launchEngine())
    {
        stop();
        return false;
    }

    workPosition_ = 0U;
    commandPosition_ = 0U;
    eventPosition_ = 0U;
    outputPosition_ = 0U;
    outputOffset_ = 0U;
    streamPosition_ = 0;
    testTone_ = !environmentValue("MPVST_NATIVE_TEST_TONE").empty();
    mpvst::release_store_u32(&header_->lifecycle, MPVST_LIFECYCLE_RUNNING);
    supervisorStop_.store(false);
    restartCount_.store(0U);
    available_.store(true);
    supervisor_ = std::thread(&SidecarTransport::supervise, this);
    return true;
}

bool SidecarTransport::launchEngine()
{
    const auto enginePath = nativeEnginePath();
    std::vector<std::string> arguments;
    if (std::filesystem::path(enginePath).stem().string() == "micropython-vst-engine")
    {
        const auto directory = std::filesystem::path(enginePath).parent_path();
        const auto scriptOverride = environmentValue("MPVST_SCRIPT_PATH");
        std::string selectedScript;
        const auto developerPath = scriptOrigin_ == ScriptOrigin::DeveloperFile
            ? developerScriptPath()
            : std::string {};
        if (!developerPath.empty())
        {
            // Hand the engine the developer's own file so that toggling Reload
            // Script re-reads whatever is on disk now. Materialising a private
            // copy here would pin the instance to the source as it was when the
            // plug-in was created, which makes the documented edit-and-reload
            // loop silently replay stale code. Restored projects keep using
            // their embedded snapshot instead, so a saved project still opens
            // the same way after the original file moves or changes.
            selectedScript = developerPath;
        }
        else if (!scriptSource_.empty())
        {
            if (materializedScriptPath_.empty())
            {
                std::ostringstream name;
                name << "micropython-vst3-" << std::hex << instanceNonce_ << ".py";
                const auto path = std::filesystem::temp_directory_path() / name.str();
                std::ofstream output(path, std::ios::binary | std::ios::trunc);
                if (!output ||
                    !output.write(scriptSource_.data(),
                                  static_cast<std::streamsize> (scriptSource_.size())))
                    return false;
                materializedScriptPath_ = path.string();
            }
            selectedScript = materializedScriptPath_;
        }
        else
        {
            selectedScript = scriptOverride.empty()
                ? (directory / "default_instrument.py").string()
                : scriptOverride;
        }
        // MPVST_HEAP_BYTES constrains the MicroPython heap. A script that
        // allocates without bound should fail inside its own sidecar with a
        // MemoryError the host reports as a script error, never by growing
        // until it disturbs the DAW.
        const auto heapBytes = environmentValue("MPVST_HEAP_BYTES");
        if (!heapBytes.empty())
            arguments = {"-X", "heapsize=" + heapBytes};
        arguments.push_back((directory / "micropython_vst_bootstrap.py").string());
        arguments.push_back(mappingName_);
        arguments.push_back(std::to_string(mappingBytes_));
        arguments.push_back(selectedScript);
    }
    else
    {
        arguments = {mappingName_, std::to_string(mappingBytes_)};
    }
    if (enginePath.empty() || !std::filesystem::exists(enginePath) ||
        !child_.start(enginePath, arguments))
        return false;

    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::seconds(2);
    while (mpvst::acquire_load_u32(&header_->lifecycle) !=
           MPVST_LIFECYCLE_ENGINE_READY)
    {
        if (!child_.running() || std::chrono::steady_clock::now() >= deadline)
        {
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    return true;
}

void SidecarTransport::stop() noexcept
{
    available_.store(false);
    supervisorStop_.store(true);
    if (supervisor_.joinable())
        supervisor_.join();
    waitForCallbacks();
    if (header_ != nullptr)
        mpvst::release_store_u32(&header_->lifecycle, MPVST_LIFECYCLE_STOPPING);
    if (!child_.wait(1000U))
        child_.terminate();
    header_ = nullptr;
    status_ = nullptr;
    commands_ = nullptr;
    events_ = nullptr;
    work_ = nullptr;
    mapping_.close();
    if (!materializedScriptPath_.empty())
    {
        std::error_code ignored;
        (void)std::filesystem::remove(materializedScriptPath_, ignored);
        materializedScriptPath_.clear();
    }
    mappingName_.clear();
    mappingBytes_ = 0U;
    instanceNonce_ = 0U;
    workPosition_ = 0U;
    commandPosition_ = 0U;
    eventPosition_ = 0U;
    outputPosition_ = 0U;
    outputOffset_ = 0U;
    streamPosition_ = 0;
}

void SidecarTransport::waitForCallbacks() noexcept
{
    while (activeCallbacks_.load() != 0U)
        std::this_thread::yield();
}

std::uint64_t SidecarTransport::restartCount() const noexcept
{
    return restartCount_.load();
}

std::uint32_t SidecarTransport::errorCode() noexcept
{
    if (!available_.load() || status_ == nullptr)
        return 0U;
    activeCallbacks_.fetch_add(1U);
    const auto result = available_.load()
        ? mpvst::acquire_load_u32(&status_->error_code)
        : 0U;
    activeCallbacks_.fetch_sub(1U);
    return result;
}

SidecarTransport::Telemetry SidecarTransport::telemetry() noexcept
{
    Telemetry snapshot;
    snapshot.ready = available_.load();
    snapshot.restarts = restartCount_.load();
    snapshot.renderTimeLastNs = renderTimeLastNs_.load(std::memory_order_relaxed);
    snapshot.renderTimeHighWaterNs =
        renderTimeHighWaterNs_.load(std::memory_order_relaxed);
    snapshot.queueDepth = queueDepth_.load(std::memory_order_relaxed);
    snapshot.queueDepthHighWater =
        queueDepthHighWater_.load(std::memory_order_relaxed);
    snapshot.lastExitCode = lastExitCode_.load(std::memory_order_relaxed);
    snapshot.lastExitWasUnexpected =
        lastExitWasUnexpected_.load(std::memory_order_relaxed);
    if (status_ == nullptr)
        return snapshot;

    snapshot.blocksRequested = mpvst::acquire_load_u64(&status_->blocks_requested);
    snapshot.blocksRendered = mpvst::acquire_load_u64(&status_->blocks_rendered);
    snapshot.underruns = mpvst::acquire_load_u64(&status_->underruns);
    snapshot.eventDrops = mpvst::acquire_load_u64(&status_->event_drops);
    snapshot.eventsConsumed = mpvst::acquire_load_u64(&status_->events_consumed);
    snapshot.errorCode = mpvst::acquire_load_u32(&status_->error_code);
    snapshot.engineState = mpvst::acquire_load_u32(&status_->engine_state);
    return snapshot;
}

void SidecarTransport::resetTelemetryPeaks() noexcept
{
    renderTimeHighWaterNs_.store(0U, std::memory_order_relaxed);
    queueDepthHighWater_.store(0U, std::memory_order_relaxed);
}

std::string SidecarTransport::diagnostic()
{
    if (!available_.load() || status_ == nullptr)
        return {};
    activeCallbacks_.fetch_add(1U);
    std::string result;
    if (available_.load())
    {
        const auto size = std::min<std::uint32_t>(
            status_->diagnostic_size, MPVST_DIAGNOSTIC_BYTES - 1U);
        result.assign(status_->diagnostic, status_->diagnostic + size);
    }
    activeCallbacks_.fetch_sub(1U);
    return result;
}

bool SidecarTransport::requestReload() noexcept
{
    if (!available_.load() || header_ == nullptr || commands_ == nullptr)
        return false;
    lastCallbackTicks_.store(
        std::chrono::steady_clock::now().time_since_epoch().count(),
        std::memory_order_relaxed);
    activeCallbacks_.fetch_add(1U);
    if (!available_.load())
    {
        activeCallbacks_.fetch_sub(1U);
        return false;
    }
    auto* command = mpvst::try_acquire_producer(
        commands_, header_->command_capacity, commandPosition_);
    if (command == nullptr)
    {
        activeCallbacks_.fetch_sub(1U);
        return false;
    }
    command->generation = mpvst::acquire_load_u32(&header_->generation);
    command->type = MPVST_COMMAND_RELOAD;
    command->argument0 = 0U;
    command->argument1 = 0U;
    std::memset(command->payload, 0, sizeof(command->payload));
    mpvst::publish_producer(command, commandPosition_++);
    activeCallbacks_.fetch_sub(1U);
    return true;
}

bool SidecarTransport::resetMappingForRestart() noexcept
{
    const auto previousGeneration =
        mpvst::acquire_load_u32(&header_->generation);
    const auto nextRestart = restartCount_.load() + 1U;
    const mpvst_layout_request request {maxFrames_, kSlotCount, kSlotCount,
                                        kEventCapacity, kCommandCapacity};
    if (!mpvst_initialize_mapping(mapping_.data(), mappingBytes_, &request,
                                  instanceNonce_))
        return false;
    header_ = static_cast<mpvst_shared_header*>(mapping_.data());
    header_->sample_rate_millihz = sampleRateMillihz_;
    mpvst::release_store_u32(&header_->generation, previousGeneration + 1U);
    status_ = static_cast<mpvst_status*>(
        mpvst_region(mapping_.data(), header_->status_offset));
    commands_ = static_cast<mpvst_command*>(
        mpvst_region(mapping_.data(), header_->commands_offset));
    events_ = static_cast<mpvst_event*>(
        mpvst_region(mapping_.data(), header_->events_offset));
    mpvst::release_store_u64(&status_->restart_count, nextRestart);
    restartCount_.store(nextRestart);
    work_ = static_cast<mpvst_work_slot*>(
        mpvst_region(mapping_.data(), header_->work_offset));
    workPosition_ = 0U;
    commandPosition_ = 0U;
    eventPosition_ = 0U;
    outputPosition_ = 0U;
    outputOffset_ = 0U;
    return true;
}

void SidecarTransport::supervise() noexcept
{
    auto lastHeartbeat = mpvst::acquire_load_u64(&status_->engine_heartbeat);
    auto lastProgress = std::chrono::steady_clock::now();
    std::uint32_t failedRestarts = 0U;
    while (!supervisorStop_.load())
    {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        if (supervisorStop_.load())
            break;

        const auto heartbeat =
            mpvst::acquire_load_u64(&status_->engine_heartbeat);
        const auto requested =
            mpvst::acquire_load_u64(&status_->blocks_requested);
        const auto rendered =
            mpvst::acquire_load_u64(&status_->blocks_rendered);
        if (heartbeat != lastHeartbeat || requested == rendered)
        {
            lastHeartbeat = heartbeat;
            lastProgress = std::chrono::steady_clock::now();
        }
        // An engine that stops draining work looks exactly like an engine whose
        // host stopped calling it: once the host stops consuming output the
        // ring fills, the engine has nowhere to publish, and rendered stops
        // advancing while work is still outstanding. Blaming the engine for
        // that restarts a healthy sidecar and throws away the script's state
        // every time a user pauses the transport. Only count it as a stall
        // while the host is actually calling back.
        const auto now = std::chrono::steady_clock::now();
        const auto sinceCallback = now -
            std::chrono::steady_clock::time_point(
                std::chrono::steady_clock::duration(
                    lastCallbackTicks_.load(std::memory_order_relaxed)));
        const bool hostIsActive = sinceCallback < std::chrono::milliseconds(250);
        const bool stalled = requested > rendered && hostIsActive &&
            now - lastProgress > std::chrono::milliseconds(500);
        if (child_.running() && !stalled)
            continue;

        // Reaching here always means the engine went away while it was still
        // wanted, so the departure is unexpected whatever status it carried.
        // A stall is recorded distinctly because the supervisor is breaking a
        // hang rather than finding a process that ended on its own.
        int exitCode = 0;
        lastExitWasUnexpected_.store(true, std::memory_order_relaxed);
        if (stalled)
            lastExitCode_.store(kStalledExitCode, std::memory_order_relaxed);
        else if (child_.wait(0U, &exitCode))
            lastExitCode_.store(static_cast<std::int32_t>(exitCode),
                                std::memory_order_relaxed);

        available_.store(false);
        waitForCallbacks();
        child_.terminate();
        if (failedRestarts >= 3U || !resetMappingForRestart())
            break;
        if (!launchEngine())
        {
            child_.terminate();
            ++failedRestarts;
            continue;
        }
        failedRestarts = 0U;
        lastHeartbeat = 0U;
        lastProgress = std::chrono::steady_clock::now();
        mpvst::release_store_u32(&header_->lifecycle, MPVST_LIFECYCLE_RUNNING);
        available_.store(true);
    }
}

mpvst_output_slot* SidecarTransport::outputAt(std::uint64_t position) const noexcept
{
    auto* bytes = static_cast<std::uint8_t*>(
        mpvst_region(mapping_.data(), header_->outputs_offset));
    return reinterpret_cast<mpvst_output_slot*>(
        bytes + (position % header_->output_slot_count) *
                    mpvst_output_stride_bytes(header_));
}

void SidecarTransport::submitWork(std::int64_t startSample,
                                  std::uint32_t frames,
                                  const mpvst_event* events,
                                  std::uint32_t eventCount,
                                  const TransportInfo* transport) noexcept
{
    auto* slot = mpvst::try_acquire_producer(work_, header_->work_slot_count,
                                             workPosition_);
    if (slot == nullptr)
    {
        if (eventCount != 0U)
            (void)mpvst::relaxed_fetch_add_u64(&status_->event_drops, eventCount);
        return;
    }
    // Blocks handed to the engine but not yet consumed. This is the queue the
    // engine has to keep up with, so its peak is what matters when diagnosing
    // an instance that underruns only occasionally.
    const auto depth = static_cast<std::uint32_t>(workPosition_ - outputPosition_);
    queueDepth_.store(depth, std::memory_order_relaxed);
    if (depth > queueDepthHighWater_.load(std::memory_order_relaxed))
        queueDepthHighWater_.store(depth, std::memory_order_relaxed);

    slot->generation = mpvst::acquire_load_u32(&header_->generation);
    slot->frame_count = frames;
    slot->start_sample = startSample;
    slot->sample_rate_millihz = sampleRateMillihz_;
    slot->transport_sample = transport != nullptr ? transport->projectSample
                                                  : streamPosition_;
    const auto consumed = mpvst::acquire_load_u64(&status_->events_consumed);
    const auto used = eventPosition_ - consumed;
    const auto availableEvents = used < header_->event_capacity
        ? header_->event_capacity - static_cast<std::uint32_t>(used)
        : 0U;
    const auto accepted = std::min(eventCount, availableEvents);
    slot->event_first = static_cast<std::uint32_t>(
        eventPosition_ % header_->event_capacity);
    slot->event_count = accepted;
    for (std::uint32_t index = 0U; index < accepted; ++index)
    {
        auto event = events[index];
        event.sample_position += streamPosition_ + latencySamples_;
        events_[(eventPosition_ + index) % header_->event_capacity] = event;
    }
    eventPosition_ += accepted;
    if (accepted != eventCount)
        (void)mpvst::relaxed_fetch_add_u64(
            &status_->event_drops, eventCount - accepted);
    slot->flags = testTone_ ? MPVST_WORK_FLAG_TEST_TONE : 0U;
    if (transport != nullptr)
    {
        if (transport->playing)
            slot->flags |= MPVST_WORK_FLAG_PLAYING;
        if (transport->discontinuity)
            slot->flags |= MPVST_WORK_FLAG_DISCONTINUITY;
        slot->time_signature_numerator = transport->timeSignatureNumerator;
        slot->time_signature_denominator = transport->timeSignatureDenominator;
        slot->tempo_micro_bpm = transport->tempoMicroBpm;
    }
    else
    {
        slot->time_signature_numerator = 4U;
        slot->time_signature_denominator = 4U;
        slot->tempo_micro_bpm = UINT64_C(120000000);
    }
    mpvst::publish_producer(slot, workPosition_);
    ++workPosition_;
    (void)mpvst::relaxed_fetch_add_u64(&status_->blocks_requested, 1U);
}

bool SidecarTransport::consumeOutput(float* left, float* right,
                                     std::int64_t startSample,
                                     std::uint32_t frames,
                                     bool countUnderrun) noexcept
{
    const auto endSample = startSample + frames;
    auto target = startSample;
    std::uint32_t examined = 0U;
    bool wroteNonSilent = false;
    while (target < endSample && examined < header_->output_slot_count)
    {
        auto* slot = outputAt(outputPosition_);
        if (mpvst::acquire_load_u64(&slot->sequence) != outputPosition_ + 1U)
            break;
        ++examined;

        const auto generation = mpvst::acquire_load_u32(&header_->generation);
        const auto slotStart = slot->start_sample + outputOffset_;
        const auto slotEnd = slot->start_sample + slot->frame_count;
        if (slot->generation != generation || slotEnd <= target)
        {
            outputOffset_ = 0U;
            mpvst::release_consumer(slot, header_->output_slot_count, outputPosition_++);
            continue;
        }
        if (slotStart > target)
        {
            target = std::min<std::int64_t>(slotStart, endSample);
            continue;
        }

        const auto copyEnd = std::min<std::int64_t>(slotEnd, endSample);
        const auto count = static_cast<std::uint32_t>(copyEnd - target);
        const auto destinationOffset = static_cast<std::uint32_t>(target - startSample);
        if ((slot->flags & MPVST_OUTPUT_FLAG_SILENT) == 0U)
        {
            std::copy_n(mpvst_const_output_channel(slot, header_->max_frames, 0U) +
                            outputOffset_,
                        count, left + destinationOffset);
            std::copy_n(mpvst_const_output_channel(slot, header_->max_frames, 1U) +
                            outputOffset_,
                        count, right + destinationOffset);
            wroteNonSilent = true;
        }
        outputOffset_ += count;
        target = copyEnd;
        if (outputOffset_ == slot->frame_count)
        {
            // Sample how long the engine spent on this block as it is retired.
            // A plain load-compare-store is enough for a high-water mark: the
            // audio thread is the only writer, and a lost update would only
            // understate a peak that a later block will raise again.
            const auto renderTime = slot->render_time_ns;
            renderTimeLastNs_.store(renderTime, std::memory_order_relaxed);
            if (renderTime > renderTimeHighWaterNs_.load(std::memory_order_relaxed))
                renderTimeHighWaterNs_.store(renderTime, std::memory_order_relaxed);
            outputOffset_ = 0U;
            mpvst::release_consumer(slot, header_->output_slot_count, outputPosition_++);
        }
    }
    if (target < endSample && countUnderrun)
        (void)mpvst::relaxed_fetch_add_u64(&status_->underruns, 1U);
    return wroteNonSilent;
}

bool SidecarTransport::process(float* left, float* right, std::uint32_t frames,
                               bool bypassed, const mpvst_event* events,
                               std::uint32_t eventCount, bool offline,
                               const TransportInfo* transport) noexcept
{
    if (left == nullptr || right == nullptr || frames == 0U || frames > maxFrames_)
        return false;
    if (!available_.load() || header_ == nullptr)
    {
        streamPosition_ += frames;
        return false;
    }
    lastCallbackTicks_.store(
        std::chrono::steady_clock::now().time_since_epoch().count(),
        std::memory_order_relaxed);
    activeCallbacks_.fetch_add(1U);
    if (!available_.load())
    {
        activeCallbacks_.fetch_sub(1U);
        return false;
    }
    submitWork(streamPosition_ + latencySamples_, frames, events, eventCount,
               transport);
    bool wroteNonSilent = false;
    if (bypassed)
    {
        // Bypass still has to drain the pipeline. Work was submitted for this
        // block, so leaving its output in the ring leaks a slot every time;
        // after a handful of bypassed blocks the ring is full, the engine can
        // no longer publish, and the supervisor mistakes the jam for a hung
        // engine and restarts it, losing the script's state. Consume the audio
        // and throw it away instead. Underruns are not counted because falling
        // behind while muted has no audible meaning.
        (void)consumeOutput(left, right, streamPosition_, frames, false);
        std::fill_n(left, frames, 0.0F);
        std::fill_n(right, frames, 0.0F);
    }
    else
    {
        if (offline && streamPosition_ >= latencySamples_)
        {
            const auto deadline = std::chrono::steady_clock::now() +
                                  std::chrono::seconds(5);
            const auto initialOutputPosition = outputPosition_;
            do
            {
                wroteNonSilent = consumeOutput(left, right, streamPosition_,
                                                frames, false) || wroteNonSilent;
                if (outputPosition_ != initialOutputPosition)
                    break;
                std::this_thread::yield();
            }
            while (available_.load() &&
                   std::chrono::steady_clock::now() < deadline);
            if (outputPosition_ == initialOutputPosition)
                wroteNonSilent = consumeOutput(left, right, streamPosition_,
                                                frames, true) || wroteNonSilent;
        }
        else
        {
            wroteNonSilent = consumeOutput(left, right, streamPosition_, frames);
        }
    }
    streamPosition_ += frames;
    activeCallbacks_.fetch_sub(1U);
    return wroteNonSilent;
}

} // namespace PyDevices::MicroPythonVST3
