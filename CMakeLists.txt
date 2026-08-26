cmake_minimum_required(VERSION 3.25)

# VERSION at the repo root is the single source of truth for the release
# version: CMake, scripts/package-linux.sh and scripts/package-windows.sh
# all read it, so a release cannot ship a binary and an archive that
# disagree about which version they are.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" MPVST_VERSION)
string(STRIP "${MPVST_VERSION}" MPVST_VERSION)
if(NOT MPVST_VERSION MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+$")
    message(FATAL_ERROR "VERSION must hold a bare X.Y.Z, got '${MPVST_VERSION}'")
endif()

project(MicroPythonVST3
    VERSION ${MPVST_VERSION}
    DESCRIPTION "Programmable MicroPython VST3 instrument"
    LANGUAGES C CXX
)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(VST3_SDK_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/.deps/vst3sdk" CACHE PATH
    "Path to the Steinberg VST3 SDK checkout")

if(NOT EXISTS "${VST3_SDK_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR
        "VST3 SDK not found at ${VST3_SDK_ROOT}. "
        "Run scripts/fetch-vst3-sdk.sh or set VST3_SDK_ROOT.")
endif()

set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL
    "Build Steinberg hosting tools, including the validator")
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)

set(public_sdk_SOURCE_DIR "${VST3_SDK_ROOT}/public.sdk")
add_subdirectory("${VST3_SDK_ROOT}" "${CMAKE_BINARY_DIR}/vst3sdk" EXCLUDE_FROM_ALL)
add_subdirectory(src/protocol)
add_subdirectory(src/runtime)
add_subdirectory(src/plugin)

include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tools/smoke_host)
    add_subdirectory(tests)
endif()
