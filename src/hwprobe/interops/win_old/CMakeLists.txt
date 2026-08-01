cmake_minimum_required(VERSION 3.21)
project(WinDeviceInfo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif ()

# ---- Shared library (DLL) ----
add_library(device_info SHARED
        src/win_helpers.cpp
        src/gpu_info.cpp
)

# Force static linking of runtime libraries to avoid dependency issues in Python
target_link_options(device_info PRIVATE -static-libgcc -static-libstdc++ -static)

target_include_directories(device_info
        PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(device_info
        PRIVATE
        dxgi
        setupapi
        cfgmgr32
        advapi32
)

# Output the DLL next to the Python binding
set_target_properties(device_info PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME "device_info"
        PREFIX ""
)

# ---- Standalone test executable ----
add_executable(WinDeviceInfo main.cpp)

target_include_directories(WinDeviceInfo
        PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# No longer linking directly to device_info to allow dynamic loading from custom path
# target_link_libraries(WinDeviceInfo PRIVATE device_info)
