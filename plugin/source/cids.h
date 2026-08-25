#pragma once

#include "pluginterfaces/base/funknown.h"

namespace PyDevices::MicroPythonVST3 {

static const Steinberg::FUID kProcessorUID (
    0x60A40168, 0x727C4E7D, 0xAAF808B7, 0x90961DAA);

static const Steinberg::FUID kControllerUID (
    0x04B27009, 0x082444D4, 0x8FE82CB5, 0xA7C810FD);

static const Steinberg::FUID kEffectProcessorUID (
    0x910677E2, 0x85944109, 0x85AD7A76, 0xCA68106C);

static const Steinberg::FUID kEffectControllerUID (
    0x16695D06, 0xFA2F4F95, 0x85FE0B71, 0x65515F68);

} // namespace PyDevices::MicroPythonVST3

