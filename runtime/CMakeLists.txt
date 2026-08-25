add_library(mpvst_runtime STATIC)
target_include_directories(mpvst_runtime PUBLIC include)
target_compile_features(mpvst_runtime PUBLIC cxx_std_17)

if(WIN32)
    target_sources(mpvst_runtime PRIVATE src/shared_memory_win.cpp src/child_process_win.cpp)
else()
    target_sources(mpvst_runtime PRIVATE src/shared_memory_posix.cpp src/child_process_posix.cpp)
endif()

if(MSVC)
    target_compile_options(mpvst_runtime PRIVATE /W4 /permissive-)
else()
    target_compile_options(mpvst_runtime PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
endif()
