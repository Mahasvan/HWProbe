#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

// Apple Silicon-specific GPU properties
typedef struct {
    int core_count;
    int gpu_perf_shaders; // num_gps: GPU performance shader count
    int gpu_gen;
    uint64_t unified_memory_mb; // Total system (unified) memory in MB
} AppleGPUProperties;

// Generic GPU properties
typedef struct {
    char name[256];
    uint32_t vendor_id;
    uint32_t device_id;

    // non-apple-silicon properties
    char acpi_path[512];
    char pci_path[512];
    uint64_t vram_mb;
    uint32_t capable_pcie_gen;
    uint32_t capable_pcie_width;
    uint32_t negotiated_pcie_gen;
    uint32_t negotiated_pcie_width;

    // exclusively apple-silicon properties
    int is_apple_silicon;
    AppleGPUProperties apple_gpu;
} GPUProperties;

// Fills `out` with GPU entries. Returns number of GPUs found, or -1 on error.
// Caller does NOT need to free — output is written into a caller-supplied buffer.
int get_gpu_info(GPUProperties *out, int max_count);

#ifdef __cplusplus
}
#endif

