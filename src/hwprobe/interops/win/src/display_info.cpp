// Display info: monitor enumeration + CCD connectors + DXGI GPU match + SetupAPI EDID.
// Returns raw values — Python does all parsing (EDID decode, connector type mapping).
// See display_info.h for the ABI.

#include "display_info.h"
#include "win_util.h"

#include <windows.h>
#include <dxgi.h>
#include <setupapi.h>
#include <cfgmgr32.h>

#include <cstring>
#include <string>
#include <vector>

#ifdef _MSC_VER
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "setupapi.lib")
#endif

// =====================================================================
// get_monitor_devices — user32 monitor enumeration
// =====================================================================

struct MonitorEnumCtx {
    MonitorDevice *devices;
    int max_count;
    int count;
};

static BOOL CALLBACK _monitorEnumProc(HMONITOR hMonitor, HDC, LPRECT, LPARAM lparam) {
    auto *ctx = reinterpret_cast<MonitorEnumCtx *>(lparam);
    if (ctx->count >= ctx->max_count) return FALSE;

    MONITORINFOEXA mi = {};
    mi.cbSize = sizeof(mi);
    if (!GetMonitorInfoA(hMonitor, &mi)) return TRUE;
    if (mi.szDevice[0] == '\0') return TRUE;

    DEVMODEA dm = {};
    dm.dmSize = sizeof(dm);
    EnumDisplaySettingsA(mi.szDevice, ENUM_CURRENT_SETTINGS, &dm);

    DISPLAY_DEVICEA dd = {};
    dd.cb = sizeof(dd);
    EnumDisplayDevicesA(mi.szDevice, 0, &dd, 0);
    if (dd.DeviceID[0] == '\0') return TRUE;

    MonitorDevice &md = ctx->devices[ctx->count];
    std::memset(&md, 0, sizeof(md));
    std::strncpy(md.device_id, mi.szDevice, sizeof(md.device_id) - 1);
    std::strncpy(md.pnp_device_id, dd.DeviceID, sizeof(md.pnp_device_id) - 1);
    md.width = static_cast<int>(dm.dmPelsWidth);
    md.height = static_cast<int>(dm.dmPelsHeight);
    md.refresh_rate = static_cast<int>(dm.dmDisplayFrequency);
    ++ctx->count;

    return TRUE;
}

int get_monitor_devices(MonitorDevice *out, int max_count) {
    if (!out || max_count <= 0) return -1;

    MonitorEnumCtx ctx = {out, max_count, 0};
    EnumDisplayMonitors(nullptr, nullptr, _monitorEnumProc, reinterpret_cast<LPARAM>(&ctx));
    return ctx.count;
}

// =====================================================================
// get_display_connectors — CCD API (QueryDisplayConfig)
// =====================================================================

int get_display_connectors(ConnectorInfo *out, int max_count) {
    if (!out || max_count <= 0) return -1;

    UINT32 pathCount = 0, modeCount = 0;
    LONG rc = GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &pathCount, &modeCount);
    if (rc != ERROR_SUCCESS) return -1;

    std::vector<DISPLAYCONFIG_PATH_INFO> paths(pathCount);
    std::vector<DISPLAYCONFIG_MODE_INFO> modes(modeCount);

    rc = QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &pathCount, paths.data(),
                            &modeCount, modes.data(), nullptr);
    if (rc != ERROR_SUCCESS) return -1;

    int count = 0;
    for (UINT32 i = 0; i < pathCount && count < max_count; ++i) {
        const auto &path = paths[i];

        // Source device name (GDI device name like \\.\DISPLAY1)
        DISPLAYCONFIG_SOURCE_DEVICE_NAME srcName = {};
        srcName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
        srcName.header.size = sizeof(srcName);
        srcName.header.adapterId = path.sourceInfo.adapterId;
        srcName.header.id = path.sourceInfo.id;

        if (DisplayConfigGetDeviceInfo(&srcName.header) != ERROR_SUCCESS)
            continue;

        // Target device name (monitor device path like \\?\DISPLAY#...)
        DISPLAYCONFIG_TARGET_DEVICE_NAME tgtName = {};
        tgtName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME;
        tgtName.header.size = sizeof(tgtName);
        tgtName.header.adapterId = path.targetInfo.adapterId;
        tgtName.header.id = path.targetInfo.id;

        if (DisplayConfigGetDeviceInfo(&tgtName.header) != ERROR_SUCCESS)
            continue;

        ConnectorInfo &ci = out[count];
        std::memset(&ci, 0, sizeof(ci));

        std::string src = WideToUtf8(srcName.viewGdiDeviceName);
        std::strncpy(ci.display_id, src.c_str(), sizeof(ci.display_id) - 1);

        std::string tgt = WideToUtf8(tgtName.monitorDevicePath);
        std::strncpy(ci.display_path, tgt.c_str(), sizeof(ci.display_path) - 1);

        ci.output_technology = static_cast<int>(path.targetInfo.outputTechnology);
        ++count;
    }

    return count;
}

// =====================================================================
// get_gpu_for_display — DXGI output -> adapter name match
// =====================================================================

int get_gpu_for_display(const char *device_name, char *out_gpu_name, int buf_size) {
    if (!device_name || !out_gpu_name || buf_size <= 0) return -1;
    out_gpu_name[0] = '\0';

    IDXGIFactory1 *factory = nullptr;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))))
        return -1;

    int result = -1;
    IDXGIAdapter1 *adapter = nullptr;

    for (UINT a = 0; factory->EnumAdapters1(a, &adapter) != DXGI_ERROR_NOT_FOUND; ++a) {
        DXGI_ADAPTER_DESC1 adesc;
        if (FAILED(adapter->GetDesc1(&adesc))) {
            adapter->Release();
            continue;
        }

        IDXGIOutput *output = nullptr;
        for (UINT o = 0; adapter->EnumOutputs(o, &output) != DXGI_ERROR_NOT_FOUND; ++o) {
            DXGI_OUTPUT_DESC odesc;
            if (FAILED(output->GetDesc(&odesc))) {
                output->Release();
                continue;
            }

            std::string devName = WideToUtf8(odesc.DeviceName);
            if (devName == device_name) {
                std::string gpuName = WideToUtf8(adesc.Description);
                std::strncpy(out_gpu_name, gpuName.c_str(), buf_size - 1);
                out_gpu_name[buf_size - 1] = '\0';
                result = 0;
                output->Release();
                adapter->Release();
                factory->Release();
                return result;
            }
            output->Release();
        }
        adapter->Release();
    }

    factory->Release();
    return result;
}

// =====================================================================
// get_edid — SetupAPI + registry EDID lookup
// =====================================================================

// {E6F07B5F-EE97-4A90-B076-33F57B4F4EA7}
static const GUID GUID_DEVINTERFACE_MONITOR = {
    0xE6F07B5F, 0xEE97, 0x4A90,
    {0xB0, 0x76, 0x33, 0xF5, 0x7B, 0xF4, 0xEA, 0xA7}
};

int get_edid(const char *pnp_device_id, unsigned char *out, int max_size) {
    if (!pnp_device_id || !out || max_size <= 0) return -1;

    // Convert the search key to uppercase wide string for case-insensitive matching.
    std::string key(pnp_device_id);
    for (auto &ch : key) ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));

    HDEVINFO devInfoSet = SetupDiGetClassDevsW(
        &GUID_DEVINTERFACE_MONITOR, nullptr, nullptr,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (devInfoSet == INVALID_HANDLE_VALUE) return -1;

    int result = 0;
    SP_DEVICE_INTERFACE_DATA ifaceData = {};
    ifaceData.cbSize = sizeof(ifaceData);

    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(devInfoSet, nullptr,
         &GUID_DEVINTERFACE_MONITOR, i, &ifaceData); ++i) {

        // Get required buffer size for interface detail.
        DWORD requiredSize = 0;
        SetupDiGetDeviceInterfaceDetailW(devInfoSet, &ifaceData, nullptr, 0,
                                         &requiredSize, nullptr);
        if (requiredSize == 0) continue;

        std::vector<BYTE> detailBuf(requiredSize);
        auto *detail = reinterpret_cast<PSP_DEVICE_INTERFACE_DETAIL_DATA_W>(detailBuf.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);

        SP_DEVINFO_DATA devData = {};
        devData.cbSize = sizeof(devData);

        if (!SetupDiGetDeviceInterfaceDetailW(devInfoSet, &ifaceData, detail,
             requiredSize, nullptr, &devData))
            continue;

        // Device path is a wide string starting after the cbSize field.
        std::string devPath = WideToUtf8(detail->DevicePath);
        for (auto &ch : devPath) ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));

        // Match against the search key (substring match — the PNP ID is
        // typically a portion of the full device path).
        if (key.find(devPath) == std::string::npos && devPath.find(key) == std::string::npos)
            continue;

        // Open the device registry key and read EDID.
        HKEY hKey = SetupDiOpenDevRegKey(devInfoSet, &devData, DICS_FLAG_GLOBAL,
                                         0, DIREG_DEV, KEY_READ);
        if (hKey == INVALID_HANDLE_VALUE || hKey == nullptr)
            continue;

        DWORD edidSize = 0;
        if (RegQueryValueExW(hKey, L"EDID", nullptr, nullptr, nullptr, &edidSize) == ERROR_SUCCESS) {
            if (edidSize > 0 && static_cast<int>(edidSize) <= max_size) {
                if (RegQueryValueExW(hKey, L"EDID", nullptr, nullptr, out, &edidSize) == ERROR_SUCCESS) {
                    result = static_cast<int>(edidSize);
                }
            }
        }

        RegCloseKey(hKey);
        if (result > 0) break;
    }

    SetupDiDestroyDeviceInfoList(devInfoSet);
    return result;
}
