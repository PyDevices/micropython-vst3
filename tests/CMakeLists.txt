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
