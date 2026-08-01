// Display info: one-pass monitor enumeration (user32 + CCD + DXGI) + SetupAPI EDID.
// Returns raw values — Python does EDID parsing and connector type mapping.
// See display_info.h for the ABI.

#include "display_info.h"

#include <windows.h>
#include <dxgi.h>
#include <setupapi.h>

#include <cstring>
#include <string>
#include <vector>

#ifdef _MSC_VER
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "setupapi.lib")
#endif

// ---- wide -> UTF-8 ----

static std::string WideToUtf8(const wchar_t *src) {
    if (!src || !*src) return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, src, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 1) return {};
    std::string out(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, src, -1, out.data(), len, nullptr, nullptr);
    return out;
}

static void copy_str(char *dst, int dst_size, const std::string &src) {
    std::strncpy(dst, src.c_str(), dst_size - 1);
    dst[dst_size - 1] = '\0';
}

// =====================================================================
// get_display_devices — user32 + CCD + DXGI in one pass
// =====================================================================

struct MonitorEnumCtx {
    DisplayDeviceInfo *devices;
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

    DisplayDeviceInfo &dev = ctx->devices[ctx->count];
    std::memset(&dev, 0, sizeof(dev));
    copy_str(dev.device_id, sizeof(dev.device_id), mi.szDevice);
    copy_str(dev.pnp_device_id, sizeof(dev.pnp_device_id), dd.DeviceID);
    dev.width = static_cast<int>(dm.dmPelsWidth);
    dev.height = static_cast<int>(dm.dmPelsHeight);
    dev.refresh_rate = static_cast<int>(dm.dmDisplayFrequency);
    ++ctx->count;

    return TRUE;
}

int get_display_devices(DisplayDeviceInfo *out, int max_count) {
    if (!out || max_count <= 0) return -1;

    // 1. user32 — base monitor list (device_id, pnp_device_id, resolution)
    MonitorEnumCtx ctx = {out, max_count, 0};
    EnumDisplayMonitors(nullptr, nullptr, _monitorEnumProc, reinterpret_cast<LPARAM>(&ctx));
    int count = ctx.count;

    // 2. CCD — connector info (display_path, monitor_name, output_technology)
    //    Match by GDI device name (\\.\DISPLAY1).
    UINT32 pathCount = 0, modeCount = 0;
    if (GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &pathCount, &modeCount) == ERROR_SUCCESS) {
        std::vector<DISPLAYCONFIG_PATH_INFO> paths(pathCount);
        std::vector<DISPLAYCONFIG_MODE_INFO> modes(modeCount);

        if (QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &pathCount, paths.data(),
                               &modeCount, modes.data(), nullptr) == ERROR_SUCCESS) {
            for (UINT32 i = 0; i < pathCount; ++i) {
                const auto &path = paths[i];

                DISPLAYCONFIG_SOURCE_DEVICE_NAME srcName = {};
                srcName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
                srcName.header.size = sizeof(srcName);
                srcName.header.adapterId = path.sourceInfo.adapterId;
                srcName.header.id = path.sourceInfo.id;
                if (DisplayConfigGetDeviceInfo(&srcName.header) != ERROR_SUCCESS) continue;

                DISPLAYCONFIG_TARGET_DEVICE_NAME tgtName = {};
                tgtName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME;
                tgtName.header.size = sizeof(tgtName);
                tgtName.header.adapterId = path.targetInfo.adapterId;
                tgtName.header.id = path.targetInfo.id;
                if (DisplayConfigGetDeviceInfo(&tgtName.header) != ERROR_SUCCESS) continue;

                std::string src = WideToUtf8(srcName.viewGdiDeviceName);
                for (int d = 0; d < count; ++d) {
                    if (out[d].device_id[0] != '\0' && src == out[d].device_id) {
                        copy_str(out[d].display_path, sizeof(out[d].display_path),
                                 WideToUtf8(tgtName.monitorDevicePath));
                        copy_str(out[d].monitor_name, sizeof(out[d].monitor_name),
                                 WideToUtf8(tgtName.monitorFriendlyName));
                        out[d].output_technology = static_cast<int>(path.targetInfo.outputTechnology);
                        break;
                    }
                }
            }
        }
    }

    // 3. DXGI — GPU name for each display. One factory, match by device name.
    IDXGIFactory1 *factory = nullptr;
    if (SUCCEEDED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) {
        IDXGIAdapter1 *adapter = nullptr;
        for (UINT a = 0; factory->EnumAdapters1(a, &adapter) != DXGI_ERROR_NOT_FOUND; ++a) {
            DXGI_ADAPTER_DESC1 adesc;
            if (FAILED(adapter->GetDesc1(&adesc))) { adapter->Release(); continue; }

            IDXGIOutput *output = nullptr;
            for (UINT o = 0; adapter->EnumOutputs(o, &output) != DXGI_ERROR_NOT_FOUND; ++o) {
                DXGI_OUTPUT_DESC odesc;
                if (FAILED(output->GetDesc(&odesc))) { output->Release(); continue; }

                std::string devName = WideToUtf8(odesc.DeviceName);
                for (int d = 0; d < count; ++d) {
                    if (out[d].gpu_name[0] == '\0' && devName == out[d].device_id) {
                        copy_str(out[d].gpu_name, sizeof(out[d].gpu_name),
                                 WideToUtf8(adesc.Description));
                        break;
                    }
                }
                output->Release();
            }
            adapter->Release();
        }
        factory->Release();
    }

    return count;
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

        DWORD requiredSize = 0;
        SetupDiGetDeviceInterfaceDetailW(devInfoSet, &ifaceData, nullptr, 0,
                                         &requiredSize, nullptr);
        if (requiredSize == 0) continue;

        std::vector<BYTE> detailBuf(requiredSize);
        auto *detail = reinterpret_cast<PSP_DEVICE_INTERFACE_DETAIL_DATA_W>(detailBuf.data());
        // cbSize must be 8 on 64-bit, 6 on 32-bit — a well-known SetupAPI quirk.
        detail->cbSize = sizeof(void *) == 8 ? 8 : 6;

        SP_DEVINFO_DATA devData = {};
        devData.cbSize = sizeof(devData);

        if (!SetupDiGetDeviceInterfaceDetailW(devInfoSet, &ifaceData, detail,
             requiredSize, nullptr, &devData))
            continue;

        std::string devPath = WideToUtf8(detail->DevicePath);
        for (auto &ch : devPath) ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));

        if (key.find(devPath) == std::string::npos && devPath.find(key) == std::string::npos)
            continue;

        HKEY hKey = SetupDiOpenDevRegKey(devInfoSet, &devData, DICS_FLAG_GLOBAL,
                                         0, DIREG_DEV, KEY_READ);
        if (hKey == INVALID_HANDLE_VALUE || hKey == nullptr) continue;

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
