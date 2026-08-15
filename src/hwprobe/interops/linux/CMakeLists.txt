cmake_minimum_required(VERSION 3.21)
project(LinuxDeviceInfo LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBDRM REQUIRED libdrm)

# ---------------------------------------------------------------------
# Shared library
# ---------------------------------------------------------------------

add_library(
    device_info
    SHARED
    src/gpu_info.cpp
)

target_include_directories(
    device_info
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${LIBDRM_INCLUDE_DIRS}
)

target_link_libraries(
    device_info
    PRIVATE
        ${LIBDRM_LIBRARIES}
        dl
)

target_compile_options(
    device_info
    PRIVATE
        ${LIBDRM_CFLAGS_OTHER}
)

if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(
        device_info
        PRIVATE
            -g
            -fno-omit-frame-pointer
    )
endif()

add_executable(LinuxDeviceInfo main.c)
target_link_libraries(LinuxDeviceInfo PRIVATE device_info)

set_target_properties(
    device_info
    PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bindings
        OUTPUT_NAME device_info
)