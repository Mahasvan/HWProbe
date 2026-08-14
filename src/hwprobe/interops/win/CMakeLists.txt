cmake_minimum_required(VERSION 3.21)
project(WinDeviceInfo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif ()

# Static runtime to avoid dependency issues when loaded by Python.
set(_STATIC_RUNTIME_OPTS -static-libgcc -static-libstdc++ -static)

# ---- gpu_info.dll : GPU enumeration (DXGI + SetupAPI + registry VRAM) ----
add_library(gpu_info SHARED
        src/gpu_info.cpp
)

target_link_options(gpu_info PRIVATE ${_STATIC_RUNTIME_OPTS})

target_include_directories(gpu_info
        PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(gpu_info
        PRIVATE
        dxgi
        setupapi
        advapi32
)

set_target_properties(gpu_info PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME "gpu_info"
        PREFIX ""
)

# ---- wmi.dll : generic WMI wrapper (COM + WbemLocator) ----
add_library(wmi SHARED
        src/wmi.cpp
)

target_link_options(wmi PRIVATE ${_STATIC_RUNTIME_OPTS})

target_include_directories(wmi
        PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(wmi
        PRIVATE
        ole32
        oleaut32
        wbemuuid
)

set_target_properties(wmi PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME "wmi"
        PREFIX ""
)

# ---- display_info.dll : CCD connectors + DXGI GPU match + SetupAPI EDID ----
add_library(display_info SHARED
        src/display_info.cpp
)

target_link_options(display_info PRIVATE ${_STATIC_RUNTIME_OPTS})

target_include_directories(display_info
        PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(display_info
        PRIVATE
        dxgi
        setupapi
        advapi32
        user32
)

set_target_properties(display_info PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME "display_info"
        PREFIX ""
)

# ---- Standalone test executable (loads all DLLs at runtime) ----
add_executable(WinDeviceInfo main.cpp)

target_include_directories(WinDeviceInfo
        PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Load both DLLs at runtime like the Python bindings do, so the test exe does
# not need matching import libs.
