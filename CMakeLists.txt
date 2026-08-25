cmake_minimum_required(VERSION 3.25)

project(MicroPythonVST3
    VERSION 0.2.0
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
add_subdirectory(protocol)
add_subdirectory(runtime)
add_subdirectory(engine)
add_subdirectory(plugin)

include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tools/smoke_host)
    add_subdirectory(tests)
endif()
