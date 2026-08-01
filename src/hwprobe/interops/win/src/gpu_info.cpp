#include "gpu_info.h"
#include "win_helpers.h"

#include <windows.h>
#include <dxgi.h>
#include <setupapi.h>
#include <devguid.h>

#include <cstring>
#include <string>
#include <regex>
#include <vector>
#include <set>

#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "setupapi.lib")

// ---- WMI-free GPU enumeration via DXGI + SetupAPI ----

static std::wstring PnpDeviceIdFromDXGI(const DXGI_ADAPTER_DESC1 &desc) {
    // DXGI gives us VendorId / DeviceId / SubSysId / Revision.
    // We need to find the matching PNP device instance via SetupAPI.
    wchar_t match_hw_id[128];
    swprintf_s(match_hw_id, L"PCI\\VEN_%04X&DEV_%04X", desc.VendorId, desc.DeviceId);

    HDEVINFO devInfo = SetupDiGetClassDevsW(&GUID_DEVCLASS_DISPLAY, nullptr, nullptr, DIGCF_PRESENT);
    if (devInfo == INVALID_HANDLE_VALUE) return {};

    SP_DEVINFO_DATA devData = {sizeof(SP_DEVINFO_DATA)};
    std::wstring result;

    for (DWORD i = 0; SetupDiEnumDeviceInfo(devInfo, i, &devData); ++i) {
        wchar_t pnpBuffer[MAX_DEVICE_ID_LEN];
        if (!SetupDiGetDeviceInstanceIdW(devInfo, &devData, pnpBuffer, MAX_DEVICE_ID_LEN, nullptr))
            continue;

        std::wstring pnp(pnpBuffer);
        // Case-insensitive prefix match for VEN_XXXX&DEV_XXXX
        std::wstring upper_pnp = pnp;
        for (auto &ch : upper_pnp) ch = towupper(ch);
        std::wstring upper_match = match_hw_id;
        for (auto &ch : upper_match) ch = towupper(ch);

        if (upper_pnp.find(upper_match) != std::wstring::npos) {
            // Further match SubSysId if there are multiple GPUs with the same vendor+device
            wchar_t subsys_match[64];
            swprintf_s(subsys_match, L"SUBSYS_%08X", desc.SubSysId);
            std::wstring upper_subsys = subsys_match;
            for (auto &ch : upper_subsys) ch = towupper(ch);

            if (upper_pnp.find(upper_subsys) != std::wstring::npos) {
                result = pnp;
                break;
            }
            // If no subsys match yet, keep this as a fallback
            if (result.empty()) result = pnp;
        }
    }

    SetupDiDestroyDeviceInfoList(devInfo);
    return result;
}

// ---- Registry VRAM fallback for >4GB cards ----

static uint64_t FetchVramFromRegistry(const std::string &device_name, const std::string &driver_version) {
    const char *key_path = "SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}";
    HKEY hKey;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, key_path, 0, KEY_READ, &hKey) != ERROR_SUCCESS)
        return 0;

    for (DWORD i = 0; i < 100; ++i) {
        char sub_key_name[32];
        DWORD name_size = sizeof(sub_key_name);
        if (RegEnumKeyExA(hKey, i, sub_key_name, &name_size, nullptr, nullptr, nullptr, nullptr) != ERROR_SUCCESS)
            continue;

        HKEY hSubKey;
        if (RegOpenKeyExA(hKey, sub_key_name, 0, KEY_READ, &hSubKey) != ERROR_SUCCESS)
            continue;

        char drv_desc[256] = {};
        DWORD drv_desc_size = sizeof(drv_desc);
        char drv_ver[256] = {};
        DWORD drv_ver_size = sizeof(drv_ver);

        bool got_desc = (RegQueryValueExA(hSubKey, "DriverDesc", nullptr, nullptr,
                         reinterpret_cast<LPBYTE>(drv_desc), &drv_desc_size) == ERROR_SUCCESS);
        bool got_ver = (RegQueryValueExA(hSubKey, "DriverVersion", nullptr, nullptr,
                        reinterpret_cast<LPBYTE>(drv_ver), &drv_ver_size) == ERROR_SUCCESS);

        if (got_desc && got_ver &&
            device_name == drv_desc && driver_version == drv_ver) {

            uint64_t vram_bytes = 0;
            DWORD vram_size = sizeof(vram_bytes);
            if (RegQueryValueExA(hSubKey, "HardwareInformation.qwMemorySize", nullptr, nullptr,
                                 reinterpret_cast<LPBYTE>(&vram_bytes), &vram_size) == ERROR_SUCCESS && vram_bytes > 0) {
                RegCloseKey(hSubKey);
                RegCloseKey(hKey);
                return vram_bytes / (1024 * 1024);
            }

            DWORD alt_vram = 0;
            DWORD alt_size = sizeof(alt_vram);
            if (RegQueryValueExA(hSubKey, "HardwareInformation.MemorySize", nullptr, nullptr,
                                 reinterpret_cast<LPBYTE>(&alt_vram), &alt_size) == ERROR_SUCCESS && alt_vram > 0) {
                RegCloseKey(hSubKey);
                RegCloseKey(hKey);
                return static_cast<uint64_t>(alt_vram) / (1024 * 1024);
            }
        }

        RegCloseKey(hSubKey);
    }

    RegCloseKey(hKey);
    return 0;
}

// ---- Get driver version from registry for a PNP device ----

static std::string GetDriverVersion(const std::wstring &pnp_device_id) {
    const char *key_path = "SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}";
    HKEY hKey;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, key_path, 0, KEY_READ, &hKey) != ERROR_SUCCESS)
        return {};

    std::string pnp_utf8 = WideToUtf8(pnp_device_id.c_str());
    // Extract VEN_XXXX&DEV_XXXX portion for matching
    std::string upper_pnp = pnp_utf8;
    for (auto &ch : upper_pnp) ch = toupper(ch);

    for (DWORD i = 0; i < 100; ++i) {
        char sub_key_name[32];
        DWORD name_size = sizeof(sub_key_name);
        if (RegEnumKeyExA(hKey, i, sub_key_name, &name_size, nullptr, nullptr, nullptr, nullptr) != ERROR_SUCCESS)
            continue;

        HKEY hSubKey;
        if (RegOpenKeyExA(hKey, sub_key_name, 0, KEY_READ, &hSubKey) != ERROR_SUCCESS)
            continue;

        char matching_id[512] = {};
        DWORD mid_size = sizeof(matching_id);
        if (RegQueryValueExA(hSubKey, "MatchingDeviceId", nullptr, nullptr,
                             reinterpret_cast<LPBYTE>(matching_id), &mid_size) == ERROR_SUCCESS) {
            std::string upper_mid = matching_id;
            for (auto &ch : upper_mid) ch = toupper(ch);
            if (upper_pnp.find(upper_mid) != std::string::npos || upper_mid.find("VEN_") != std::string::npos) {
                char drv_ver[256] = {};
                DWORD ver_size = sizeof(drv_ver);
                if (RegQueryValueExA(hSubKey, "DriverVersion", nullptr, nullptr,
                                     reinterpret_cast<LPBYTE>(drv_ver), &ver_size) == ERROR_SUCCESS) {
                    RegCloseKey(hSubKey);
                    RegCloseKey(hKey);
                    return drv_ver;
                }
            }
        }
        RegCloseKey(hSubKey);
    }

    RegCloseKey(hKey);
    return {};
}

// ---- Vendor/Device/Subsystem ID parsing from PNP Device ID ----

struct PciIds {
    uint32_t vendor_id;
    uint32_t device_id;
    uint32_t subsystem_vendor_id;
    uint32_t subsystem_device_id;
};

static PciIds ParsePnpDeviceId(const std::string &pnp) {
    PciIds ids = {};
    std::regex re(R"(VEN_([0-9A-Fa-f]{4}).*DEV_([0-9A-Fa-f]{4}).*SUBSYS_([0-9A-Fa-f]{4})([0-9A-Fa-f]{4}))",
                  std::regex::icase);
    std::smatch m;
    if (std::regex_search(pnp, m, re)) {
        ids.vendor_id = std::stoul(m[1].str(), nullptr, 16);
        ids.device_id = std::stoul(m[2].str(), nullptr, 16);
        ids.subsystem_device_id = std::stoul(m[3].str(), nullptr, 16);
        ids.subsystem_vendor_id = std::stoul(m[4].str(), nullptr, 16);
    }
    return ids;
}

// ---- Public API ----

int get_gpu_info(WinGPUProperties *out, int max_count) {
    if (!out || max_count <= 0) return -1;

    IDXGIFactory1 *factory = nullptr;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))))
        return -1;

    int count = 0;
    IDXGIAdapter1 *adapter = nullptr;
    std::set<std::wstring> seen_pnp_ids;

    for (UINT a = 0; factory->EnumAdapters1(a, &adapter) != DXGI_ERROR_NOT_FOUND && count < max_count; ++a) {
        DXGI_ADAPTER_DESC1 desc;
        if (FAILED(adapter->GetDesc1(&desc))) {
            adapter->Release();
            continue;
        }

        // Skip software/remote adapters (DXGI_ADAPTER_FLAG_SOFTWARE = 2, defined in DXGI 1.2+)
        // On Windows 7 no adapter sets this flag, so the check is a safe no-op.
        if (desc.Flags & 2u) {
            adapter->Release();
            continue;
        }

        // Deduplicate: DXGI can enumerate the same physical GPU multiple times (common on AMD APUs)
        std::wstring pnp_id_early = PnpDeviceIdFromDXGI(desc);
        if (!pnp_id_early.empty()) {
            std::wstring upper_pnp = pnp_id_early;
            for (auto &ch : upper_pnp) ch = towupper(ch);
            if (seen_pnp_ids.count(upper_pnp)) {
                adapter->Release();
                continue;
            }
            seen_pnp_ids.insert(upper_pnp);
        }

        WinGPUProperties gpu = {};

        // Name from DXGI
        char name_buf[256];
        WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, name_buf, sizeof(name_buf), nullptr, nullptr);
        strncpy_s(gpu.name, name_buf, _TRUNCATE);

        // IDs from DXGI
        gpu.vendor_id = desc.VendorId;
        gpu.device_id = desc.DeviceId;

        // PNP device instance already resolved above for dedup
        const std::wstring &pnp_id = pnp_id_early;
        std::string pnp_utf8 = WideToUtf8(pnp_id.c_str());

        // Parse subsystem IDs from PNP device ID string
        if (!pnp_utf8.empty()) {
            PciIds ids = ParsePnpDeviceId(pnp_utf8);
            gpu.subsystem_vendor_id = ids.subsystem_vendor_id;
            gpu.subsystem_device_id = ids.subsystem_device_id;
        }

        // VRAM: DXGI reports DedicatedVideoMemory in bytes
        uint64_t vram_mb = desc.DedicatedVideoMemory / (1024 * 1024);

        // WMI/DXGI may report capped VRAM for >4GB cards; fall back to registry
        if (vram_mb == 0 || desc.DedicatedVideoMemory >= 4194304000ULL) {
            std::string drv_ver = GetDriverVersion(pnp_id);
            uint64_t reg_vram = FetchVramFromRegistry(std::string(gpu.name), drv_ver);
            if (reg_vram > 0) vram_mb = reg_vram;
        }
        gpu.vram_mb = vram_mb;

        // Location paths (ACPI + PCI) and PCIe info via Configuration Manager
        if (!pnp_id.empty()) {
            std::string acpi, pci;
            if (GetDevNodeLocationPaths(pnp_id, acpi, pci)) {
                strncpy_s(gpu.acpi_path, acpi.c_str(), _TRUNCATE);
                strncpy_s(gpu.pci_path, pci.c_str(), _TRUNCATE);
            }

            int gen = 0, width = 0;
            if (GetDevNodePCIeInfo(pnp_id, gen, width)) {
                gpu.pcie_gen = gen;
                gpu.pcie_width = width;
            }
        }

        // Manufacturer: map common vendor IDs
        switch (gpu.vendor_id) {
            case 0x10DE: strncpy_s(gpu.manufacturer, "NVIDIA", _TRUNCATE); break;
            case 0x1002: strncpy_s(gpu.manufacturer, "AMD", _TRUNCATE); break;
            case 0x8086: strncpy_s(gpu.manufacturer, "Intel", _TRUNCATE); break;
            default: {
                char hex[16];
                snprintf(hex, sizeof(hex), "0x%04X", gpu.vendor_id);
                strncpy_s(gpu.manufacturer, hex, _TRUNCATE);
                break;
            }
        }

        out[count++] = gpu;
        adapter->Release();
    }

    factory->Release();
    return count;
}
