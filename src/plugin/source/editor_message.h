#pragma once

// The one message the processor sends the controller: which shared mapping
// the editor lives in, and which engine generation created it.
//
// The controller may be in another process, so it cannot read the processor's
// members and has no other way to learn this. IConnectionPoint is the SDK's
// answer and this is standard plumbing; what is worth stating is why the name
// travels as *binary* rather than a string. Attribute strings are UTF-16, and
// a mapping name is an OS identifier - a POSIX shm path or a Win32 object
// name - that has to arrive byte for byte. Converting it twice to make a
// message look tidy is a way to lose it.

namespace PyDevices::MicroPythonVST3 {

constexpr const char* kUiMappingMessageId = "MPVSTUiMapping";
constexpr const char* kUiMappingNameAttribute = "name";
constexpr const char* kUiMappingGenerationAttribute = "generation";

} // namespace PyDevices::MicroPythonVST3
