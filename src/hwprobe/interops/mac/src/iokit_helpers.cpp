#include "iokit_helpers.h"

#include <cstring>
#include <algorithm>

std::string readCFString(CFStringRef cfStr) {
    if (!cfStr) return {};
    if (const char *cStr = CFStringGetCStringPtr(cfStr, kCFStringEncodingUTF8))
        return {cStr};
    CFIndex length = CFStringGetLength(cfStr);
    if (length == 0) return {};
    CFIndex maxSize = CFStringGetMaximumSizeForEncoding(length, kCFStringEncodingUTF8) + 1;
    std::string result(static_cast<size_t>(maxSize), '\0');
    if (CFStringGetCString(cfStr, result.data(), maxSize, kCFStringEncodingUTF8)) {
        result.resize(std::strlen(result.c_str()));
        return result;
    }
    return {};
}

uint32_t readUInt32(CFDictionaryRef dict, CFStringRef key) {
    CFTypeRef ref = CFDictionaryGetValue(dict, key);
    if (!ref) {
        return 0;
    }

    CFTypeID typeId = CFGetTypeID(ref);

    if (typeId == CFNumberGetTypeID()) {
        uint32_t value = 0;
        if (CFNumberGetValue(static_cast<CFNumberRef>(ref), kCFNumberSInt32Type, &value)) {
            return value;
        }
        return 0;
    }

    if (typeId == CFDataGetTypeID()) {
        auto data = static_cast<CFDataRef>(ref);
        CFIndex len = CFDataGetLength(data);
        if (len <= 0) {
            return 0;
        }

        uint32_t value = 0;
        CFDataGetBytes(
            data,
            CFRangeMake(0, std::min<CFIndex>(len, sizeof(value))),
            reinterpret_cast<UInt8 *>(&value)
        );

        return value;
    }

    return 0;
}

uint64_t readCFTypeAsUInt64(CFTypeRef ref) {
    if (!ref) return 0;
    if (CFGetTypeID(ref) == CFNumberGetTypeID()) {
        uint64_t val = 0;
        CFNumberGetValue(static_cast<CFNumberRef>(ref), kCFNumberSInt64Type, &val);
        return val;
    }
    if (CFGetTypeID(ref) == CFDataGetTypeID()) {
        auto data = static_cast<CFDataRef>(ref);
        CFIndex len = CFDataGetLength(data);
        if (len <= 0) return 0;
        uint64_t val = 0;
        CFDataGetBytes(data,
                       CFRangeMake(0, std::min(len, static_cast<CFIndex>(sizeof(val)))),
                       reinterpret_cast<UInt8 *>(&val));
        return val;
    }
    return 0;
}

mach_port_t getIOKitMainPort() {
    if (__builtin_available(macOS 12.0, *))
        return kIOMainPortDefault;
    return kIOMasterPortDefault;
}

std::string readCFStringFromDict(CFDictionaryRef dict, CFStringRef key) {
    CFTypeRef ref = CFDictionaryGetValue(dict, key);
    if (!ref) return {};
    if (CFGetTypeID(ref) == CFStringGetTypeID())
        return readCFString(static_cast<CFStringRef>(ref));
    return {};
}
