#include "win_helpers.h"

#include <windows.h>
#include <cfgmgr32.h>
#include <devpkey.h>

#include <string>
#include <vector>
#include <regex>
#include <sstream>
#include <cstdio>

#pragma comment(lib, "cfgmgr32.lib")

// ---- Wide-to-UTF8 ----

std::string WideToUtf8(const wchar_t *src) {
    if (!src || !*src) return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, src, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 1) return {};
    std::string out(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, src, -1, &out[0], len, nullptr, nullptr);
    return out;
}

extern "C" void wide_to_utf8(const wchar_t *src, char *dst, int dst_size) {
    if (!src || !dst || dst_size <= 0) return;
    WideCharToMultiByte(CP_UTF8, 0, src, -1, dst, dst_size, nullptr, nullptr);
}

// ---- DEVPROPKEY definitions ----

static const DEVPROPKEY DEVPKEY_LocationPaths = {
    {0xA45C254E, 0xDF1C, 0x4EFD, {0x80, 0x20, 0x67, 0xD1, 0x46, 0xA8, 0x50, 0xE0}}, 37
};

static const DEVPROPKEY DEVPKEY_PCIe_CurrentLinkSpeed = {
    {0x3AB22E31, 0x8264, 0x4B4E, {0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62}}, 9
};

static const DEVPROPKEY DEVPKEY_PCIe_CurrentLinkWidth = {
    {0x3AB22E31, 0x8264, 0x4B4E, {0x9A, 0xF5, 0xA8, 0xD2, 0xD8, 0xE3, 0x3E, 0x62}}, 10
};

// ---- Internal helpers ----

static DEVINST LocateDevNode(const std::wstring &pnp_device_id) {
    DEVINST dn = 0;
    CONFIGRET cr = CM_Locate_DevNodeW(&dn, const_cast<DEVINSTID_W>(pnp_device_id.c_str()), CM_LOCATE_DEVNODE_NORMAL);
    return (cr == CR_SUCCESS) ? dn : 0;
}

static bool GetDevNodeStringListProperty(DEVINST dn, const DEVPROPKEY &key, std::vector<std::string> &out) {
    DEVPROPTYPE propType = 0;
    ULONG bufSize = 0;

    CONFIGRET cr = CM_Get_DevNode_PropertyW(dn, &key, &propType, nullptr, &bufSize, 0);
    if (cr != CR_BUFFER_SMALL && cr != CR_SUCCESS) return false;

    std::vector<BYTE> buf(bufSize);
    cr = CM_Get_DevNode_PropertyW(dn, &key, &propType, buf.data(), &bufSize, 0);
    if (cr != CR_SUCCESS) return false;

    const wchar_t *p = reinterpret_cast<const wchar_t *>(buf.data());
    const wchar_t *end = p + (bufSize / sizeof(wchar_t));

    while (p < end && *p) {
        std::wstring ws(p);
        out.push_back(WideToUtf8(ws.c_str()));
        p += ws.size() + 1;
    }
    return !out.empty();
}

static bool GetDevNodeUInt32Property(DEVINST dn, const DEVPROPKEY &key, uint32_t &out) {
    DEVPROPTYPE propType = 0;
    ULONG bufSize = sizeof(uint32_t);
    CONFIGRET cr = CM_Get_DevNode_PropertyW(dn, &key, &propType, reinterpret_cast<PBYTE>(&out), &bufSize, 0);
    return (cr == CR_SUCCESS);
}

// ---- Path formatting ----

std::string FormatPciPath(const std::string &raw) {
    if (raw.empty()) return {};

    std::string result;
    std::istringstream ss(raw);
    std::string segment;
    bool first = true;

    while (std::getline(ss, segment, '#')) {
        if (!first) result += '/';
        first = false;

        // PCIROOT(N)
        std::smatch m;
        std::regex rootRe(R"(PCIROOT\((\d+)\))");
        if (std::regex_match(segment, m, rootRe)) {
            int val = std::stoi(m[1].str());
            char buf[64];
            std::snprintf(buf, sizeof(buf), "PciRoot(0x%X)", val);
            result += buf;
            continue;
        }

        // PCI(XXYY) or USB(XXYY)
        std::regex pciRe(R"((PCI|USB)\(([0-9A-Fa-f]+)\))");
        if (std::regex_match(segment, m, pciRe)) {
            std::string prefix = m[1].str();
            int full_val = std::stoi(m[2].str(), nullptr, 16);
            int device = full_val >> 8;
            int function = full_val & 0xFF;
            // Capitalize first letter, lowercase rest
            prefix[0] = toupper(prefix[0]);
            for (size_t i = 1; i < prefix.size(); ++i) prefix[i] = tolower(prefix[i]);
            char buf[64];
            std::snprintf(buf, sizeof(buf), "%s(0x%X,0x%X)", prefix.c_str(), device, function);
            result += buf;
            continue;
        }

        result += segment;
    }
    return result;
}

std::string FormatAcpiPath(const std::string &raw) {
    if (raw.empty()) return {};

    std::string result;
    std::regex re(R"((ACPI|USB)\(([^)]+)\))");
    auto begin = std::sregex_iterator(raw.begin(), raw.end(), re);
    auto end = std::sregex_iterator();

    bool first = true;
    for (auto it = begin; it != end; ++it) {
        std::string val = (*it)[2].str();
        if (first) {
            result += '\\';
            first = false;
        } else {
            result += '.';
        }
        result += val;
    }
    return result;
}

// ---- Public API ----

bool GetDevNodeLocationPaths(const std::wstring &pnp_device_id,
                             std::string &out_acpi_path,
                             std::string &out_pci_path) {
    DEVINST dn = LocateDevNode(pnp_device_id);
    if (!dn) return false;

    std::vector<std::string> paths;
    if (!GetDevNodeStringListProperty(dn, DEVPKEY_LocationPaths, paths))
        return false;

    for (const auto &path : paths) {
        if (path.find("ACPI") == 0 && out_acpi_path.empty())
            out_acpi_path = FormatAcpiPath(path);
        if (path.find("PCIROOT") == 0 && out_pci_path.empty())
            out_pci_path = FormatPciPath(path);
    }
    return !out_acpi_path.empty() || !out_pci_path.empty();
}

bool GetDevNodePCIeInfo(const std::wstring &pnp_device_id,
                        int &out_pcie_gen,
                        int &out_pcie_width) {
    DEVINST dn = LocateDevNode(pnp_device_id);
    if (!dn) return false;

    uint32_t speed = 0, width = 0;
    bool got_speed = GetDevNodeUInt32Property(dn, DEVPKEY_PCIe_CurrentLinkSpeed, speed);
    bool got_width = GetDevNodeUInt32Property(dn, DEVPKEY_PCIe_CurrentLinkWidth, width);

    if (got_speed) out_pcie_gen = static_cast<int>(speed);
    if (got_width) out_pcie_width = static_cast<int>(width);

    return got_speed || got_width;
}
