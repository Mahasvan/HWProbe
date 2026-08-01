#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

// Raw GPU data from DXGI + SetupAPI. No parsing, no formatting — Python does
// all derivation (subsystem ID split, location paths, PCIe info, VRAM unit
// conversion, manufacturer name). C++ only does what Python can't: COM
// enumeration (DXGI) and SetupAPI handle flow.
//
// Fields:
//   name                       — DXGI Description, UTF-8
//   vendor_id                  — DXGI VendorId
//   device_id                  — DXGI DeviceId
//   subsystem_id               — DXGI SubSysId (raw uint32; high 16 = subsystem
//                                vendor, low 16 = subsystem device — Python splits)
//   dedicated_video_memory_bytes — DXGI DedicatedVideoMemory, raw bytes
//   pnp_device_id              — from SetupAPI, raw "PCI\VEN_...&DEV_...&SUBSYS_..."
//                                (empty if SetupAPI match failed)
//   vram_bytes                 — registry fallback for >4GB cards, raw bytes
//                                (0 if DXGI value was used or registry lookup failed)
typedef struct {
    char name[256];
    uint32_t vendor_id;
    uint32_t device_id;
    uint32_t subsystem_id;
    uint64_t dedicated_video_memory_bytes;
    char pnp_device_id[512];
    uint64_t vram_bytes;
} WinGPURaw;

// Fills `out` with GPU entries. Returns number of GPUs found, or -1 on error.
int get_gpu_info(WinGPURaw *out, int max_count);

#ifdef __cplusplus
}
#endif
