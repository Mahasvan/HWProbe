#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char     name[256];
    uint32_t vendor_id;
    uint32_t device_id;
    uint64_t vram_total_mb;
    uint64_t vram_used_mb;
    int      pcie_gen;
    int      pcie_width;
    char     pci_slot[32];
    char     driver[64];
} GPUProperties;

int get_gpu_info(GPUProperties *out, int max_count);

#ifdef __cplusplus
}
#endif
