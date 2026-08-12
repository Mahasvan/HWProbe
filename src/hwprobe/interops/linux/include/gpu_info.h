#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C"
{
#endif

#define AMD_VENDOR_ID 0x1002
#define INTEL_VENDOR_ID 0x8086
#define NVIDIA_VENDOR_ID 0x10DE

typedef struct
{
    uint16_t domain;    //!< PCI domain number
    uint8_t bus;        //!< PCI bus number
    uint8_t device;     //!< PCI device number
    uint8_t function;   //!< PCI function number
} PCIAddress;

typedef struct
{
    char name[256];         //!< GPU name or description, if available.
    uint64_t vram_total_mb; //!< Total VRAM capacity in MB: 0 if unavailable, greater than 0 otherwise.
    uint64_t vram_used_mb;  //!< Total VRAM used by all processes: 0 if available, greater than 0 otherwise.
} GPUProperties;

int get_gpu_info(const char *bdf, uint32_t vendor_id, GPUProperties *out);

#ifdef __cplusplus
}
#endif
