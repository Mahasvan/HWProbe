cmake_minimum_required(VERSION 3.21)
project(WinWmi LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif ()

# ---- Shared library (DLL) ----
add_library(device_info SHARED
        src/wmi.cpp
)

# Static runtime to avoid dependency issues when loaded by Python.
target_link_options(device_info PRIVATE -static-libgcc -static-libstdc++ -static)

target_include_directories(device_info
        PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(device_info
        PRIVATE
        ole32
        oleaut32
        wbemuuid
)

# Drop the DLL next to the Python binding.
set_target_properties(device_info PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME "device_info"
        PREFIX ""
)

# ---- Standalone test executable ----
add_executable(WinWmiTest main.cpp)

target_include_directories(WinWmiTest
        PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Load the DLL at runtime like the Python binding does, so the test exe does
# not need a matching import lib.
target_compile_definitions(WinWmiTest PRIVATE WINWMI_TEST_RUNTIME_LOAD)
