add_executable(micropython-vst-native-engine native_engine.cpp)
target_link_libraries(micropython-vst-native-engine PRIVATE mpvst_protocol mpvst_runtime)
target_compile_features(micropython-vst-native-engine PRIVATE cxx_std_17)

if(MSVC)
    target_compile_options(micropython-vst-native-engine PRIVATE /W4 /permissive-)
else()
    target_compile_options(micropython-vst-native-engine PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()
