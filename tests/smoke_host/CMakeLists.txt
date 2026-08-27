add_executable(mpvst_smoke_host
    main.cpp
    ${VST3_SDK_ROOT}/public.sdk/source/common/memorystream.cpp
)
if(WIN32)
    target_sources(mpvst_smoke_host PRIVATE
        ${VST3_SDK_ROOT}/public.sdk/source/vst/hosting/module_win32.cpp)
elseif(APPLE)
    target_sources(mpvst_smoke_host PRIVATE
        ${VST3_SDK_ROOT}/public.sdk/source/vst/hosting/module_mac.mm)
else()
    target_sources(mpvst_smoke_host PRIVATE
        ${VST3_SDK_ROOT}/public.sdk/source/vst/hosting/module_linux.cpp)
endif()
# The editor test opens the plug-in's UI mapping itself and drives it as the
# view would, so it needs the same layout and the same shared-memory helper
# the real view uses. Reimplementing either in the test would let the test and
# the product drift into agreeing with each other about the wrong thing.
target_link_libraries(mpvst_smoke_host PRIVATE sdk_hosting mpvst_protocol
                                               mpvst_runtime)
target_include_directories(mpvst_smoke_host
    PRIVATE ${CMAKE_SOURCE_DIR}/src/plugin/source)
target_compile_features(mpvst_smoke_host PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_smoke_host PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_smoke_host PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()
