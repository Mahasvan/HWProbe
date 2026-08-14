#include "gpu_info.h"
#include "iokit_helpers.h"

#include <iostream>
#include <cstdint>
#include <string>
#include <cstring>
#include <vector>
#include <algorithm>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <sys/sysctl.h>

#define RESOLVE_PCIE_SPEED_PROPERTY(capability) (capability & 0xF)
#define RESOLVE_PCIE_WIDTH_PROPERTY(capability) ((capability >> 4) & 0x3F)

// ---- Internal helpers ----

static int getAppleGpuProperty(CFDictionaryRef gpuConfig, CFStringRef key) {
    int result = 0;
    CFTypeRef value = CFDictionaryGetValue(gpuConfig, key);
    if (value && CFGetTypeID(value) == CFNumberGetTypeID())
        CFNumberGetValue(static_cast<CFNumberRef>(value), kCFNumberIntType, &result);
    return result;
}

static uint64_t getSystemMemoryMB() {
    int mib[2] = {CTL_HW, HW_MEMSIZE};
    uint64_t mem = 0;
    size_t length = sizeof(mem);
    if (sysctl(mib, 2, &mem, &length, nullptr, 0) == 0)
        return mem / (1024 * 1024);
    return 0;
}

static CFDictionaryRef buildMatchingDict(bool is_arm) {
    if (is_arm) {
        const void *keys[] = {CFSTR("IONameMatched")};
        const void *values[] = {CFSTR("gpu*")};
        return CFDictionaryCreate(kCFAllocatorDefault, keys, values, 1,
                                  &kCFTypeDictionaryKeyCallBacks,
                                  &kCFTypeDictionaryValueCallBacks);
    } else {
        const void *keys[] = {CFSTR("IOProviderClass"), CFSTR("IOPCIClassMatch")};
        const void *values[] = {CFSTR("IOPCIDevice"), CFSTR("0x03000000&0xff000000")};
        return CFDictionaryCreate(kCFAllocatorDefault, keys, values, 2,
                                  &kCFTypeDictionaryKeyCallBacks,
                                  &kCFTypeDictionaryValueCallBacks);
    }
}

// ---- PCI / ACPI path helpers ----

static std::string constructPciPath(io_service_t service) {
    std::vector<std::string> segments;
    io_service_t entry = service;
    IOObjectRetain(entry);

    while (entry) {
        if (IOObjectConformsTo(entry, "IOPCIDevice")) {
            io_name_t location{};
            kern_return_t kr = IORegistryEntryGetLocationInPlane(entry, kIOServicePlane, location);
            if (kr != KERN_SUCCESS) {
                IOObjectRelease(entry);
                break;
            }
            std::string loc(location);
            try {
                unsigned long busVal = 0, funcVal = 0;
                auto comma = loc.find(',');
                if (comma != std::string::npos) {
                    busVal = std::stoul(loc.substr(0, comma), nullptr, 16);
                    funcVal = std::stoul(loc.substr(comma + 1), nullptr, 16);
                } else {
                    busVal = std::stoul(loc, nullptr, 16);
                }
                char seg[64];
                std::snprintf(seg, sizeof(seg), "Pci(0x%lx,0x%lx)", busVal, funcVal);
                segments.emplace_back(seg);
            } catch (...) {
                IOObjectRelease(entry);
                break;
            }
        } else if (IOObjectConformsTo(entry, "IOACPIPlatformDevice")) {
            int uid = 0;
            CFTypeRef uidRef = IORegistryEntryCreateCFProperty(entry, CFSTR("_UID"), kCFAllocatorDefault, kNilOptions);
            if (uidRef) {
                if (CFGetTypeID(uidRef) == CFNumberGetTypeID()) {
                    CFNumberGetValue(static_cast<CFNumberRef>(uidRef), kCFNumberIntType, &uid);
                } else if (CFGetTypeID(uidRef) == CFStringGetTypeID()) {
                    std::string uidStr = readCFString(static_cast<CFStringRef>(uidRef));
                    try { uid = std::stoi(uidStr); } catch (...) {
                    }
                }
                CFRelease(uidRef);
            }
            char seg[64];
            std::snprintf(seg, sizeof(seg), "PciRoot(0x%x)", uid);
            segments.emplace_back(seg);
            IOObjectRelease(entry);
            break;
        } else if (IOObjectConformsTo(entry, "IOPCIBridge")) {
            // Skip bridges, keep walking
        } else {
            segments.clear();
            IOObjectRelease(entry);
            break;
        }

        io_service_t parent = 0;
        kern_return_t kr = IORegistryEntryGetParentEntry(entry, kIOServicePlane, &parent);
        IOObjectRelease(entry);
        if (kr != KERN_SUCCESS)
            break;
        entry = parent;
    }

    if (segments.empty())
        return {};

    std::reverse(segments.begin(), segments.end());
    std::string result;
    for (size_t i = 0; i < segments.size(); ++i) {
        if (i > 0) result += '/';
        result += segments[i];
    }
    return result;
}

static std::string parseAcpiPath(CFDictionaryRef props) {
    CFTypeRef ref = CFDictionaryGetValue(props, CFSTR("acpi-path"));
    if (!ref) return {};

    std::string raw;
    if (CFGetTypeID(ref) == CFStringGetTypeID()) {
        raw = readCFString(static_cast<CFStringRef>(ref));
    } else if (CFGetTypeID(ref) == CFDataGetTypeID()) {
        auto data = static_cast<CFDataRef>(ref);
        CFIndex len = CFDataGetLength(data);
        if (len <= 0) return {};
        raw.resize(static_cast<size_t>(len));
        CFDataGetBytes(data, CFRangeMake(0, len), reinterpret_cast<UInt8 *>(raw.data()));
        auto nul = raw.find('\0');
        if (nul != std::string::npos)
            raw.resize(nul);
    } else {
        return {};
    }

    // Format: "IOACPIPlane:/_SB/PC00/RP05/PXSX" -> "\_SB.PC00.RP05.PXSX"
    auto colon = raw.find(':');
    if (colon == std::string::npos) return {};

    std::string tail = raw.substr(colon + 1);
    std::string result;
    size_t pos = 0;
    while (pos < tail.size()) {
        if (tail[pos] == '/') {
            ++pos;
            continue;
        }
        auto next = tail.find('/', pos);
        std::string segment = (next == std::string::npos) ? tail.substr(pos) : tail.substr(pos, next - pos);

        // Strip @... suffix
        auto at = segment.find('@');
        if (at != std::string::npos)
            segment = segment.substr(0, at);

        if (!segment.empty()) {
            // Check if the lowercased segment contains "sb"
            std::string lower = segment;
            std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
            if (lower.find("sb") != std::string::npos)
                result += '\\';
            else
                result += '.';
            result += segment;
        }

        pos = (next == std::string::npos) ? tail.size() : next + 1;
    }

    return result;
}

static void processPCIeInformationForGpu(GPUProperties *gpu, uint32_t capabilities, uint32_t negotiated) {
    gpu->capable_pcie_gen = RESOLVE_PCIE_SPEED_PROPERTY(capabilities);
    gpu->capable_pcie_width = RESOLVE_PCIE_WIDTH_PROPERTY(capabilities);

    gpu->negotiated_pcie_gen = RESOLVE_PCIE_SPEED_PROPERTY(negotiated);
    gpu->negotiated_pcie_width = RESOLVE_PCIE_WIDTH_PROPERTY(negotiated);
}

static bool readRecursiveUInt32Property(io_service_t service, CFStringRef key, uint32_t *value) {
    if (!service || !value) {
        return false;
    }

    CFTypeRef ref = IORegistryEntrySearchCFProperty(
        service, kIOServicePlane, key,
        kCFAllocatorDefault, kIORegistryIterateRecursively);
    if (!ref) {
        return false;
    }

    *value = static_cast<uint32_t>(readCFTypeAsUInt64(ref));
    CFRelease(ref);
    return true;
}

// ---- VRAM helper ----

static uint64_t getDiscreteVramMB(io_service_t service) {
    // Try "VRAM,totalMB" first (directly in MB).
    // IOKit may store this as CFNumber or CFData depending on the GPU driver.
    // Search the service and its children recursively.
    CFTypeRef ref = IORegistryEntrySearchCFProperty(
        service, kIOServicePlane, CFSTR("VRAM,totalMB"),
        kCFAllocatorDefault, kIORegistryIterateRecursively);
    if (ref) {
        uint64_t mb = readCFTypeAsUInt64(ref);
        CFRelease(ref);
        if (mb > 0) return mb;
    }
    return 0;
}

// ---- Public API ----

int get_gpu_info(GPUProperties *out, int max_count) {
    if (!out || max_count <= 0) return -1;

#if defined(__arm64__)
    constexpr bool is_arm = true;
#else
    constexpr bool is_arm = false;
#endif

    mach_port_t ioPort = getIOKitMainPort();

    // NOTE: IOServiceGetMatchingServices takes ownership of the matching dict
    // (it always calls CFRelease internally), so we must not release it ourselves.
    CFDictionaryRef matching = buildMatchingDict(is_arm);
    io_iterator_t iterator = 0;
    kern_return_t kr = IOServiceGetMatchingServices(ioPort, matching, &iterator);
    if (kr != KERN_SUCCESS)
        return -1;

    int count = 0;
    io_service_t service;

    while ((service = IOIteratorNext(iterator)) != 0 && count < max_count) {
        CFMutableDictionaryRef props = nullptr;
        if (IORegistryEntryCreateCFProperties(service, &props, kCFAllocatorDefault, kNilOptions) != KERN_SUCCESS) {
            IOObjectRelease(service);
            continue;
        }

        // Filter non-GPU entries on ARM
        if (is_arm) {
            std::string ioName = readCFString(
                static_cast<CFStringRef>(CFDictionaryGetValue(props, CFSTR("IONameMatched"))));
            std::string bundle = readCFString(
                static_cast<CFStringRef>(CFDictionaryGetValue(props, CFSTR("CFBundleIdentifierKernel"))));
            if (ioName.find("gpu") == std::string::npos && bundle.find("AGX") == std::string::npos) {
                CFRelease(props);
                IOObjectRelease(service);
                continue;
            }
        }

        GPUProperties gpu{};
        gpu.vendor_id = readUInt32(props, CFSTR("vendor-id"));
        gpu.device_id = readUInt32(props, CFSTR("device-id"));

        if (!is_arm) {
            uint32_t capabilities = 0;
            uint32_t negotiated = 0;
            bool hasCapabilities = readRecursiveUInt32Property(
                service, CFSTR("IOPCIExpressLinkCapabilities"), &capabilities);
            bool hasNegotiated = readRecursiveUInt32Property(
                service, CFSTR("IOPCIExpressLinkStatus"), &negotiated);

            std::cout << "Capable PCIe Link: " << capabilities << "\n";
            std::cout << "Negotiated PCIe Link: " << negotiated << "\n";

            if (hasCapabilities && hasNegotiated) {
                processPCIeInformationForGpu(&gpu, capabilities, negotiated);
            }
        }

        CFTypeRef modelRef = CFDictionaryGetValue(props, CFSTR("model"));
        if (modelRef) {
            if (CFGetTypeID(modelRef) == CFStringGetTypeID()) {
                // Apple Silicon / some entries expose model as CFString
                std::string n = readCFString(static_cast<CFStringRef>(modelRef));
                std::strncpy(gpu.name, n.c_str(), sizeof(gpu.name) - 1);
            } else if (CFGetTypeID(modelRef) == CFDataGetTypeID()) {
                // PCI GPUs (AMD, NVIDIA, Intel) store model as a null-terminated
                // byte sequence inside a CFData blob
                auto data = static_cast<CFDataRef>(modelRef);
                CFIndex len = CFDataGetLength(data);
                if (len > 0) {
                    CFIndex copy = std::min(len, static_cast<CFIndex>(sizeof(gpu.name) - 1));
                    CFDataGetBytes(data, CFRangeMake(0, copy),
                                   reinterpret_cast<UInt8 *>(gpu.name));
                    gpu.name[copy] = '\0';
                }
            }
        }

        if (gpu.name[0] != '\0' || gpu.vendor_id != 0) {
            if (is_arm) {
                gpu.is_apple_silicon = 1;
                gpu.apple_gpu.unified_memory_mb = getSystemMemoryMB();

                CFTypeRef configRef = CFDictionaryGetValue(props, CFSTR("GPUConfigurationVariable"));
                if (configRef && CFGetTypeID(configRef) == CFDictionaryGetTypeID()) {
                    auto gpuConfig = static_cast<CFDictionaryRef>(configRef);
                    gpu.apple_gpu.core_count = getAppleGpuProperty(gpuConfig, CFSTR("num_cores"));
                    gpu.apple_gpu.gpu_perf_shaders = getAppleGpuProperty(gpuConfig, CFSTR("num_gps"));
                    gpu.apple_gpu.gpu_gen = getAppleGpuProperty(gpuConfig, CFSTR("gpu_gen"));
                }
            } else {
                gpu.is_apple_silicon = 0;

                std::string pciPath = constructPciPath(service);
                if (!pciPath.empty())
                    std::strncpy(gpu.pci_path, pciPath.c_str(), sizeof(gpu.pci_path) - 1);

                std::string acpiPath = parseAcpiPath(props);
                if (!acpiPath.empty())
                    std::strncpy(gpu.acpi_path, acpiPath.c_str(), sizeof(gpu.acpi_path) - 1);

                gpu.vram_mb = getDiscreteVramMB(service);
            }
            out[count++] = gpu;
        }

        CFRelease(props);
        IOObjectRelease(service);
    }

    IOObjectRelease(iterator);
    return count;
}

