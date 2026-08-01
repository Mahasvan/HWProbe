#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

// One active display device. Filled by get_display_devices which merges
// user32 monitor enumeration, CCD connector info, and DXGI GPU association
// in a single pass — no Python-side correlation needed.
typedef struct {
    char device_id[32];         // GDI device name, e.g. "\\.\DISPLAY1"
    char pnp_device_id[128];    // PNP hardware ID, e.g. "MONITOR\BOE0936\{...}"
    char monitor_name[128];     // CCD monitorFriendlyName (may be empty)
    char display_path[512];     // CCD target device path, e.g. "\\?\DISPLAY#..."
    char gpu_name[256];         // DXGI adapter name (may be empty)
    int  width;                 // Current resolution width (pixels)
    int  height;                // Current resolution height (pixels)
    int  refresh_rate;          // Current refresh rate (Hz)
    int  output_technology;     // DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY enum value
} DisplayDeviceInfo;

// Fill `out` with active display devices. Returns count, or -1 on error.
int get_display_devices(DisplayDeviceInfo *out, int max_count);

// Read raw EDID bytes from the registry for a monitor matching `pnp_device_id`.
// Returns EDID byte count (>=128 on success), 0 if not found, -1 on error.
int get_edid(const char *pnp_device_id, unsigned char *out, int max_size);

#ifdef __cplusplus
}
#endif
