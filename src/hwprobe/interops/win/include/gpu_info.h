#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char name[256];
    char manufacturer[256];
    uint32_t vendor_id;
    uint32_t device_id;
    uint32_t subsystem_vendor_id;
    uint32_t subsystem_device_id;
    char acpi_path[512];
    char pci_path[512];
    uint64_t vram_mb;
    int pcie_gen;
    int pcie_width;
} WinGPUProperties;

typedef enum {
    GPU_STATUS_OK = 0,
    GPU_STATUS_FAILURE = 1,
    GPU_STATUS_INVALID_ARG = 2
} GPUStatus;

// Fills `out` with GPU entries. Returns number of GPUs found, or -1 on error.
int get_gpu_info(WinGPUProperties *out, int max_count);

#ifdef __cplusplus
}
#endif
