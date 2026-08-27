# The minimal VST3 host the smoke tests and the script probes drive. Built
# first so mpvst_smoke_host exists by the time the add_test calls below
# reference it.
add_subdirectory(smoke_host)

# The Python that runs the test scripts. The repository's own .venv is
# searched first, for the same reason flake8 is found there below: these
# scripts import audioif, which is a dependency installed from PyPI (or as an
# editable install of a sibling checkout), and a distribution Python is
# usually externally managed and cannot have it installed into it.
#
# This used to fall to whatever python3 was on PATH, and worked only because
# tools/harness.py put a sibling audioif checkout on sys.path itself. That
# hid which copy of audioif was under test -- it beat both the installed
# package and PYTHONPATH -- so the scripts now just import it.
find_program(MPVST_PYTHON
    NAMES python3 python
    HINTS "${CMAKE_SOURCE_DIR}/.venv/bin" "${CMAKE_SOURCE_DIR}/.venv/Scripts"
    NO_CMAKE_SYSTEM_PATH)
if(NOT MPVST_PYTHON)
    find_package(Python3 COMPONENTS Interpreter)
    set(MPVST_PYTHON "${Python3_EXECUTABLE}")
    message(STATUS "no .venv Python; falling back to ${MPVST_PYTHON}. The "
        "Python tests need pydevices-audioif installed into it.")
endif()

add_executable(mpvst_protocol_tests protocol_tests.cpp)
target_link_libraries(mpvst_protocol_tests PRIVATE mpvst_protocol)
target_compile_features(mpvst_protocol_tests PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_protocol_tests PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_protocol_tests PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

add_test(NAME mpvst_protocol_tests COMMAND mpvst_protocol_tests)

# These need a real MicroPython sidecar, which is staged on any platform that
# has one built.
if(TARGET mpvst-stage-micropython-engine)
    if(WIN32)
        set(mpvst_engine_name micropython-vst-engine.exe)
    else()
        set(mpvst_engine_name micropython-vst-engine)
    endif()
    # LVGL and the PyDevices integration are a permanent part of the engine,
    # not an option, so a build that quietly drops one has to fail here rather
    # than at the first editor open. display_driver is deliberately absent
    # from this list: importing it builds a display, which needs a board -
    # mpvst_editor_smoke covers it, through the real one.
    add_test(NAME mpvst_engine_modules COMMAND
        $<TARGET_FILE_DIR:MicroPythonVST3>/${mpvst_engine_name}
        -c "import lvgl, vstaudio, vstui, displaydev, appdev, multimer, events")

    add_executable(mpvst_reload_tests reload_tests.cpp)
    target_link_libraries(mpvst_reload_tests PRIVATE mpvst_sidecar_transport)
    target_compile_features(mpvst_reload_tests PRIVATE cxx_std_17)
    if(MSVC)
        target_compile_options(mpvst_reload_tests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(mpvst_reload_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
    endif()
    add_dependencies(mpvst_reload_tests mpvst-stage-micropython-engine)
    add_test(NAME mpvst_reload_tests COMMAND mpvst_reload_tests
        $<TARGET_FILE_DIR:MicroPythonVST3>/${mpvst_engine_name})
    add_test(NAME mpvst_embedded_state_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-embedded-state)
    add_test(NAME mpvst_micropython_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-micropython)
    add_test(NAME mpvst_effect_audio_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-effect-audio)
    add_test(NAME mpvst_patch_select_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-patch-select)
    # The editor end to end: the controller learns the mapping, the engine
    # paints only while it is open, injected input reaches the panel, and the
    # gestures come back as parameter edits pointing the right way.
    add_test(NAME mpvst_editor_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-editor)
    set_tests_properties(mpvst_editor_smoke PROPERTIES TIMEOUT 300)
    # Every class in the shared effects library, through the real sidecar.
    if(MPVST_PYTHON)
        add_test(NAME mpvst_effects_library COMMAND ${MPVST_PYTHON}
            ${CMAKE_SOURCE_DIR}/tools/test-effects-lib.py
            $<TARGET_FILE:mpvst_smoke_host>
            $<TARGET_FILE_DIR:MicroPythonVST3>/../..)
        set_tests_properties(mpvst_effects_library PROPERTIES TIMEOUT 600)

        # Every lib/instruments/*.py script, through the real VST3 plug-in
        # class and protocol.
        add_test(NAME mpvst_instruments_plugin COMMAND ${MPVST_PYTHON}
            ${CMAKE_SOURCE_DIR}/tools/test-instruments-plugin.py
            $<TARGET_FILE:mpvst_smoke_host>
            $<TARGET_FILE_DIR:MicroPythonVST3>/../..)
        set_tests_properties(mpvst_instruments_plugin PROPERTIES TIMEOUT 900)
    endif()
endif()

# The same instrument scripts against the audioif CPython wheel directly
# (no compiled engine needed) -- fast enough to run on every configure.
if(MPVST_PYTHON)
    add_test(NAME mpvst_instruments_library COMMAND ${MPVST_PYTHON}
        ${CMAKE_SOURCE_DIR}/tools/test-instruments-lib.py)
    set_tests_properties(mpvst_instruments_library PROPERTIES TIMEOUT 300)

    # lib/instruments/*.py are generated from audioinstruments and
    # committed, because a REAPER project embeds the bytes of the script
    # it loads. A stale shim would keep working and quietly disagree with
    # the instrument about its macro labels, so regenerate and diff.
    add_test(NAME mpvst_instrument_shims COMMAND ${MPVST_PYTHON}
        ${CMAKE_SOURCE_DIR}/tools/generate_shims.py --check)

    # Defect linting for the Python half of the repository - the tools, the
    # instrument and effect scripts, the composition modules. Configured in
    # .flake8 to pyflakes-level checks only, so it reports bugs rather than
    # layout. There is no hosted CI for this repository; ctest is the gate.
    #
    # The repository's own .venv is searched first, because a distribution
    # Python is usually externally managed and cannot have flake8 installed
    # into it. Skipped rather than failed when there is none - it is a lint,
    # not a build dependency.
    find_program(MPVST_FLAKE8 flake8 HINTS "${CMAKE_SOURCE_DIR}/.venv/bin")
    if(MPVST_FLAKE8)
        add_test(NAME mpvst_lint COMMAND ${MPVST_FLAKE8}
            WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
    else()
        message(STATUS "flake8 not found (try .venv/bin/pip install flake8); "
                       "skipping the mpvst_lint test")
    endif()
endif()

# Fuzz targets. The portable driver runs on every toolchain as an ordinary
# test; MPVST_ENABLE_LIBFUZZER builds the same entry points for clang's
# coverage-guided engine instead.
add_executable(mpvst_fuzz_driver fuzz/fuzz_targets.cpp fuzz/fuzz_driver.cpp)
target_link_libraries(mpvst_fuzz_driver PRIVATE mpvst_protocol)
target_compile_features(mpvst_fuzz_driver PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_fuzz_driver PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_fuzz_driver PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

add_test(NAME mpvst_fuzz_smoke COMMAND mpvst_fuzz_driver 20000
    ${CMAKE_CURRENT_SOURCE_DIR}/fuzz/corpus)

option(MPVST_ENABLE_LIBFUZZER "Build coverage-guided fuzz targets (clang only)" OFF)
if(MPVST_ENABLE_LIBFUZZER)
    foreach(target mapping state)
        string(TOUPPER ${target} target_upper)
        add_executable(mpvst_fuzz_${target} fuzz/fuzz_targets.cpp)
        target_link_libraries(mpvst_fuzz_${target} PRIVATE mpvst_protocol)
        target_compile_features(mpvst_fuzz_${target} PRIVATE cxx_std_17)
        target_compile_definitions(mpvst_fuzz_${target}
            PRIVATE MPVST_LIBFUZZER_${target_upper})
        target_compile_options(mpvst_fuzz_${target}
            PRIVATE -fsanitize=fuzzer,address,undefined)
        target_link_options(mpvst_fuzz_${target}
            PRIVATE -fsanitize=fuzzer,address,undefined)
    endforeach()
endif()
