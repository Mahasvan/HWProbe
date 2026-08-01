#pragma once

#include <cstdint>
#include <string>

#ifdef __cplusplus
extern "C" {
#endif

// Convert a wide string to a UTF-8 char buffer.
void wide_to_utf8(const wchar_t *src, char *dst, int dst_size);

#ifdef __cplusplus
}
#endif

// C++ only helpers
#ifdef __cplusplus

#include <windows.h>
#include <cfgmgr32.h>
#include <devpkey.h>

std::string WideToUtf8(const wchar_t *src);

// DEVPROPKEY-based device property helpers
bool GetDevNodeLocationPaths(const std::wstring &pnp_device_id,
                             std::string &out_acpi_path,
                             std::string &out_pci_path);

bool GetDevNodePCIeInfo(const std::wstring &pnp_device_id,
                        int &out_pcie_gen,
                        int &out_pcie_width);

// Path formatting: raw PCIROOT(0)#PCI(1C05)#PCI(0000) -> PciRoot(0x0)/Pci(0x1C,0x5)/Pci(0x0,0x0)
std::string FormatPciPath(const std::string &raw);

// Path formatting: raw ACPI(_SB_)#ACPI(PCI0)#ACPI(RP05)#ACPI(PXSX) -> \_SB_.PCI0.RP05.PXSX
std::string FormatAcpiPath(const std::string &raw);

#endif
