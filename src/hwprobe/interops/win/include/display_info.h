#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

// Active monitor device from user32 enumeration.
// One entry per attached display.
typedef struct {
    char device_id[32];         // GDI device name, e.g. "\\.\DISPLAY1"
    char pnp_device_id[128];    // PNP hardware ID, e.g. "MONITOR\SAMxxxx\{...}"
    int  width;                 // Current resolution width (pixels)
    int  height;                // Current resolution height (pixels)
    int  refresh_rate;          // Current refresh rate (Hz)
} MonitorDevice;

// Display connector info from the CCD API (QueryDisplayConfig).
// One entry per active display path.
typedef struct {
    char display_id[32];        // Source GDI device name, e.g. "\\.\DISPLAY1"
    char display_path[512];     // Target monitor device path, e.g. "\\?\DISPLAY#..."
    int   output_technology;    // DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY enum value
} ConnectorInfo;

// Fill `out` with active monitor devices. Returns count, or -1 on error.
int get_monitor_devices(MonitorDevice *out, int max_count);

// Fill `out` with active display connector info. Returns count, or -1 on error.
int get_display_connectors(ConnectorInfo *out, int max_count);

// Find the GPU (adapter) name driving a given display device name.
// Returns 0 on success, -1 on failure. Writes a UTF-8 name into out_gpu_name.
int get_gpu_for_display(const char *device_name, char *out_gpu_name, int buf_size);

// Read raw EDID bytes from the registry for a monitor whose SetupAPI device
// path contains `key` (case-insensitive substring match). The device path has
// the form \\?\DISPLAY#SAMxxxx#5&...#{...}; pass the CCD display path
// (ConnectorInfo.display_path) or the monitor ID segment (e.g. "SAMxxxx").
// The full PNP device ID (MONITOR\SAMxxxx\{...}) does NOT match.
// Returns EDID byte count (>=128 on success), 0 if not found, -1 on error.
int get_edid(const char *key, unsigned char *out, int max_size);

#ifdef __cplusplus
}
#endif
