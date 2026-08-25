set(MPVST_PLUGIN_TARGET MicroPythonVST3)

add_library(mpvst_sidecar_transport STATIC
    source/sidecar_transport.cpp
    source/sidecar_transport.h
)
set_target_properties(mpvst_sidecar_transport PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(mpvst_sidecar_transport PUBLIC source)
target_link_libraries(mpvst_sidecar_transport PUBLIC mpvst_protocol mpvst_runtime)
target_compile_features(mpvst_sidecar_transport PUBLIC cxx_std_17)

smtg_add_vst3plugin(${MPVST_PLUGIN_TARGET}
    source/cids.h
    source/controller.cpp
    source/controller.h
    source/factory.cpp
    source/parameters.h
    source/processor.cpp
    source/processor.h
    source/script_metadata.h
    source/version.h
)
smtg_target_add_library_main(${MPVST_PLUGIN_TARGET})

target_link_libraries(${MPVST_PLUGIN_TARGET}
    PRIVATE
        mpvst_protocol
        mpvst_runtime
        mpvst_sidecar_transport
        sdk
)

add_custom_target(mpvst-stage-native-engine ALL
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:micropython-vst-native-engine>
        $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
    DEPENDS ${MPVST_PLUGIN_TARGET} micropython-vst-native-engine
    COMMENT "Bundling the native Phase 2 sidecar")

if(WIN32)
    set(MPVST_ENGINE_DEFAULT
        "${CMAKE_SOURCE_DIR}/.deps/engine/micropython-vst-engine.exe")
else()
    set(MPVST_ENGINE_DEFAULT
        "${CMAKE_SOURCE_DIR}/.deps/engine/micropython-vst-engine")
endif()
set(MPVST_MICROPYTHON_ENGINE "${MPVST_ENGINE_DEFAULT}"
    CACHE FILEPATH "Optional prebuilt MicroPython VST engine for this platform")
if(EXISTS "${MPVST_MICROPYTHON_ENGINE}")
    add_custom_target(mpvst-stage-micropython-engine ALL
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${MPVST_MICROPYTHON_ENGINE}"
            $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_SOURCE_DIR}/engine/micropython_vst_bootstrap.py"
            $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_SOURCE_DIR}/engine/default_instrument.py"
            $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
        DEPENDS
            ${MPVST_PLUGIN_TARGET}
            "${MPVST_MICROPYTHON_ENGINE}"
            "${CMAKE_SOURCE_DIR}/engine/micropython_vst_bootstrap.py"
            "${CMAKE_SOURCE_DIR}/engine/default_instrument.py"
        COMMENT "Bundling the headless MicroPython Phase 3 engine")
endif()

target_compile_features(${MPVST_PLUGIN_TARGET} PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_sidecar_transport PRIVATE /W4 /permissive-)
    target_compile_options(${MPVST_PLUGIN_TARGET} PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_sidecar_transport PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
    target_compile_options(${MPVST_PLUGIN_TARGET} PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

smtg_target_configure_version_file(${MPVST_PLUGIN_TARGET})
target_include_directories(${MPVST_PLUGIN_TARGET} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
smtg_target_set_bundle(${MPVST_PLUGIN_TARGET}
    BUNDLE_IDENTIFIER "org.pydevices.micropython-vst3"
    COMPANY_NAME "PyDevices"
)
