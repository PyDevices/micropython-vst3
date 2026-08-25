add_library(mpvst_protocol STATIC
    src/protocol.cpp
)

target_include_directories(mpvst_protocol PUBLIC include)
target_compile_features(mpvst_protocol PUBLIC cxx_std_17)

if(MSVC)
    target_compile_options(mpvst_protocol PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_protocol PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()
