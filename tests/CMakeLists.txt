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

add_executable(mpvst_sidecar_tests sidecar_tests.cpp)
target_link_libraries(mpvst_sidecar_tests PRIVATE mpvst_protocol mpvst_runtime)
target_compile_features(mpvst_sidecar_tests PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_sidecar_tests PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_sidecar_tests PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

add_test(NAME mpvst_sidecar_tests COMMAND mpvst_sidecar_tests
    $<TARGET_FILE:micropython-vst-native-engine>)

add_executable(mpvst_transport_tests transport_tests.cpp)
target_link_libraries(mpvst_transport_tests PRIVATE mpvst_sidecar_transport)
target_compile_features(mpvst_transport_tests PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_transport_tests PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_transport_tests PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

add_test(NAME mpvst_transport_tests COMMAND mpvst_transport_tests
    $<TARGET_FILE:micropython-vst-native-engine>)

if(WIN32 AND TARGET mpvst-stage-micropython-engine)
    add_executable(mpvst_reload_tests reload_tests.cpp)
    target_link_libraries(mpvst_reload_tests PRIVATE mpvst_sidecar_transport)
    target_compile_features(mpvst_reload_tests PRIVATE cxx_std_17)
    target_compile_options(mpvst_reload_tests PRIVATE /W4 /permissive-)
    add_dependencies(mpvst_reload_tests mpvst-stage-micropython-engine)
    add_test(NAME mpvst_reload_tests COMMAND mpvst_reload_tests
        $<TARGET_FILE_DIR:MicroPythonVST3>/micropython-vst-engine.exe)
    add_test(NAME mpvst_embedded_state_smoke COMMAND mpvst_smoke_host
        $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-embedded-state)
endif()

add_test(NAME mpvst_lifecycle_smoke COMMAND mpvst_smoke_host
    $<TARGET_FILE_DIR:MicroPythonVST3>/../..)
add_test(NAME mpvst_reload_fade_smoke COMMAND mpvst_smoke_host
    $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-reload-fade)
add_test(NAME mpvst_macro_resync_smoke COMMAND mpvst_smoke_host
    $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-macro-resync)
add_test(NAME mpvst_transport_discontinuity_smoke COMMAND mpvst_smoke_host
    $<TARGET_FILE_DIR:MicroPythonVST3>/../.. --expect-transport)

add_executable(mpvst_soak_tests soak_tests.cpp)
target_link_libraries(mpvst_soak_tests PRIVATE mpvst_sidecar_transport)
target_compile_features(mpvst_soak_tests PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_soak_tests PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_soak_tests PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()

# The short soak guards the scenario itself. Run mpvst_soak_tests directly with
# a longer duration for the multi-minute soaks.
add_test(NAME mpvst_soak_short COMMAND mpvst_soak_tests
    $<TARGET_FILE:micropython-vst-native-engine> 5)
set_tests_properties(mpvst_soak_short PROPERTIES TIMEOUT 120)

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
