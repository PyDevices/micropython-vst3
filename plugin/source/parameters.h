#pragma once

#include "pluginterfaces/vst/vsttypes.h"

#include <cstddef>
#include <cstdint>

namespace PyDevices::MicroPythonVST3 {

constexpr Steinberg::Vst::ParamID kBypassParameter = 0;
constexpr Steinberg::Vst::ParamID kReloadParameter = 1;
constexpr Steinberg::Vst::ParamID kEngineReadyParameter = 2;
constexpr Steinberg::Vst::ParamID kEngineErrorParameter = 3;
// Doubles as the ProgramListID for the patch program list (see
// Controller::initialize): VST3 has no native "program change" input
// event, so a host maps an incoming MIDI Program Change message onto
// this kIsProgramChange-flagged parameter instead.
constexpr Steinberg::Vst::ParamID kPatchParameter = 4;
constexpr std::size_t kPatchCount = 128;
constexpr Steinberg::Vst::ParamID kFirstMacroParameter = 100;
constexpr std::size_t kMacroParameterCount = 16;
constexpr Steinberg::Vst::ParamID kFirstMidiParameter = 0x10000;
constexpr std::size_t kMidiChannelCount = 16;
constexpr std::size_t kMidiControllerCount = 130;
constexpr Steinberg::int32 kLegacyStateVersion = 1;
constexpr Steinberg::int32 kStateVersion = 2;
constexpr Steinberg::int32 kDefaultPipelineBlocks = 4;
constexpr Steinberg::int32 kMaximumPipelineBlocks = 16;
constexpr Steinberg::int32 kMaximumEmbeddedScriptBytes = 1024 * 1024;

constexpr bool isMacroParameter (Steinberg::Vst::ParamID id) noexcept
{
    return id >= kFirstMacroParameter &&
           id < kFirstMacroParameter + kMacroParameterCount;
}

constexpr std::size_t macroIndex (Steinberg::Vst::ParamID id) noexcept
{
    return static_cast<std::size_t> (id - kFirstMacroParameter);
}

constexpr Steinberg::Vst::ParamID midiParameterId (std::size_t channel,
                                                    std::size_t controller) noexcept
{
    return kFirstMidiParameter +
           static_cast<Steinberg::Vst::ParamID> (channel * 256U + controller);
}

constexpr bool decodeMidiParameter (Steinberg::Vst::ParamID id,
                                    std::uint16_t& channel,
                                    std::uint16_t& controller) noexcept
{
    if (id < kFirstMidiParameter)
        return false;
    const auto encoded = id - kFirstMidiParameter;
    const auto decodedChannel = encoded / 256U;
    const auto decodedController = encoded % 256U;
    if (decodedChannel >= kMidiChannelCount ||
        decodedController >= kMidiControllerCount)
        return false;
    channel = static_cast<std::uint16_t> (decodedChannel);
    controller = static_cast<std::uint16_t> (decodedController);
    return true;
}

} // namespace PyDevices::MicroPythonVST3
