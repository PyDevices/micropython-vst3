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
    source/editor.cpp
    source/editor.h
    source/editor_message.h
    source/factory.cpp
    source/parameters.h
    source/plugin_catalog.cpp
    source/plugin_catalog.h
    source/processor.cpp
    source/processor.h
    source/script_metadata.h
    source/version.h
)
smtg_target_add_library_main(${MPVST_PLUGIN_TARGET})

# The SDK's own moduleinfo.json reader. The factory learns which plug-ins to
# offer from that file, and reading it with the parser that defines the format
# is what keeps "what the scanner wrote" and "what the host will read" the
# same question. It is not part of the `sdk` target, so it is named here.
target_sources(${MPVST_PLUGIN_TARGET} PRIVATE
    "${VST3_SDK_ROOT}/public.sdk/source/vst/moduleinfo/moduleinfoparser.cpp")

target_link_libraries(${MPVST_PLUGIN_TARGET}
    PRIVATE
        mpvst_protocol
        mpvst_runtime
        mpvst_sidecar_transport
        sdk
)

if(UNIX AND NOT APPLE)
    # The editor's window on Linux is a plain X11 child of the frame the host
    # gives us, driven by the host's own run loop. No VSTGUI, no toolkit.
    find_package(X11 REQUIRED)
    target_link_libraries(${MPVST_PLUGIN_TARGET} PRIVATE X11::X11)
endif()

if(WIN32)
    set(MPVST_ENGINE_NAME micropython-vst-engine.exe)
    set(MPVST_ENGINE_DEFAULT
        "${CMAKE_SOURCE_DIR}/.deps/engine/micropython-vst-engine.exe")
else()
    set(MPVST_ENGINE_NAME micropython-vst-engine)
    set(MPVST_ENGINE_DEFAULT
        "${CMAKE_SOURCE_DIR}/.deps/engine/micropython-vst-engine")
endif()
set(MPVST_MICROPYTHON_ENGINE "${MPVST_ENGINE_DEFAULT}"
    CACHE FILEPATH "Optional prebuilt MicroPython VST engine for this platform")
# The instruments and the effects library live in audiocomponents, as
# ordinary pure-Python packages (audioif keeps the DSP nodes they are built
# on, and the C usermod the engine build links). They are staged beside
# this repository's own lib/ so `import audioinstruments` resolves in the
# sidecar, which puts the bootstrap's directory on sys.path and nothing
# else. Same layout rule as the engine build, which expects audioif as a
# workspace sibling: audiocomponents sits beside it.
set(MPVST_COMPONENTS_LIB_DEFAULT "${CMAKE_SOURCE_DIR}/../audiocomponents/lib")
set(MPVST_COMPONENTS_LIB "${MPVST_COMPONENTS_LIB_DEFAULT}"
    CACHE PATH "audiocomponents' pure-Python packages (audioinstruments, audioeffects)")
# MPVST_AUDIOIF_LIB was this variable's name while the packages lived in
# audioif. Honoured for one release when it is set and the new name is
# not, so an existing cache or build script keeps working - loudly. The
# cache remembers the old name too, so a build directory configured
# before the move keeps staging from audioif until it is told otherwise:
# `-U MPVST_AUDIOIF_LIB` drops the stale entry.
if(MPVST_AUDIOIF_LIB AND MPVST_COMPONENTS_LIB STREQUAL MPVST_COMPONENTS_LIB_DEFAULT)
    message(WARNING
        "MPVST_AUDIOIF_LIB is deprecated and goes away after this release: "
        "the instruments and effects moved from audioif to audiocomponents. "
        "Using it as MPVST_COMPONENTS_LIB (${MPVST_AUDIOIF_LIB}). Set "
        "MPVST_COMPONENTS_LIB instead, or reconfigure with "
        "-U MPVST_AUDIOIF_LIB to drop a cached value.")
    set(MPVST_COMPONENTS_LIB "${MPVST_AUDIOIF_LIB}")
endif()
if(NOT IS_DIRECTORY "${MPVST_COMPONENTS_LIB}")
    message(FATAL_ERROR
        "audiocomponents' lib/ is not at ${MPVST_COMPONENTS_LIB}.\n"
        "Every instrument script loads audioinstruments from there. Run "
        "scripts/fetch-sibling-repos.sh, or point MPVST_COMPONENTS_LIB at a "
        "checkout.")
endif()

if(EXISTS "${MPVST_MICROPYTHON_ENGINE}")
    # stage_lib.cmake clears only the top-level entries its own source
    # owns, so these two invocations compose rather than erasing each
    # other's output.
    add_custom_target(mpvst-stage-micropython-engine ALL
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${MPVST_MICROPYTHON_ENGINE}"
            $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
        COMMAND ${CMAKE_COMMAND}
            -DMPVST_LIB_SRC=${CMAKE_SOURCE_DIR}/lib
            -DMPVST_LIB_DST=$<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
            -P "${CMAKE_CURRENT_SOURCE_DIR}/stage_lib.cmake"
        # MPVST_LIB_RETIRED names the path this source had before the move,
        # so a build directory that staged from audioif drops what only
        # that stage put in the bundle (audiorender/, which nothing in the
        # sidecar imports) instead of shipping it forever.
        COMMAND ${CMAKE_COMMAND}
            -DMPVST_LIB_SRC=${MPVST_COMPONENTS_LIB}
            -DMPVST_LIB_DST=$<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
            -DMPVST_LIB_RETIRED=${CMAKE_SOURCE_DIR}/../audioif/lib
            -P "${CMAKE_CURRENT_SOURCE_DIR}/stage_lib.cmake"
        # Same command the install instructions give a user, run here so a
        # fresh build has a moduleinfo.json describing the library rather than
        # none at all - the factory reads it, so without this a just-built
        # plug-in offers only its four compiled-in classes.
        COMMAND ${CMAKE_COMMAND} -E chdir
            $<TARGET_FILE_DIR:${MPVST_PLUGIN_TARGET}>
            ./${MPVST_ENGINE_NAME} scan_plugins.py --write
        DEPENDS
            ${MPVST_PLUGIN_TARGET}
            "${MPVST_MICROPYTHON_ENGINE}"
            "${CMAKE_SOURCE_DIR}/lib/micropython_vst_bootstrap.py"
            "${CMAKE_SOURCE_DIR}/lib/default_instrument.py"
            "${CMAKE_SOURCE_DIR}/lib/default_effect.py"
            "${CMAKE_SOURCE_DIR}/lib/mpvst_adapter.py"
        COMMENT "Bundling the headless MicroPython engine and script library")
else()
    # Unlike MPVST_COMPONENTS_LIB above, a missing engine is not fatal: the
    # plug-in target still builds and links without it. But tests/CMakeLists.txt
    # gates its entire engine-dependent suite (mpvst_engine_modules,
    # mpvst_reload_tests, every mpvst_smoke_host test, mpvst_effects_library,
    # mpvst_named_plugins) on TARGET mpvst-stage-micropython-engine, which
    # this branch never defines - so a silent skip here means most of the
    # test matrix silently vanishes instead of failing loudly. Warn instead
    # of staying quiet.
    message(WARNING
        "No MicroPython engine found at ${MPVST_MICROPYTHON_ENGINE}. The "
        "plug-in will build, but it will ship with no engine to stage, and "
        "every engine-dependent ctest (mpvst_engine_modules, "
        "mpvst_reload_tests, the mpvst_smoke_host tests, "
        "mpvst_effects_library, mpvst_named_plugins) will be silently "
        "absent from the suite rather than failing. Run "
        "scripts/build-micropython-engine.sh (--port windows or --port "
        "unix) to build one, or set MPVST_MICROPYTHON_ENGINE to point at "
        "an existing build.")
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
