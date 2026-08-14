#pragma once

// Common wide-string <-> UTF-8 helpers shared across the Windows interop DLLs.
// Header-only (inline) so each DLL compiles its own copy without a shared
// static library or CMake target changes.

#ifdef _WIN32

#include <windows.h>
#include <string>
#include <cstring>

// Convert a wide string to a UTF-8 std::string. Returns "" for null/empty.
inline std::string WideToUtf8(const wchar_t *src) {
    if (!src || !*src) return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, src, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 1) return {};
    std::string out(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, src, -1, out.data(), len, nullptr, nullptr);
    return out;
}

// Convert a wide string into a fixed-size UTF-8 buffer (null-terminated).
// Overlong values are truncated at a UTF-8 boundary (no split multi-byte seq).
// Missing/null/empty -> "".
inline void WideToUtf8Slot(const wchar_t *src, char *dst, int dst_size) {
    if (!dst || dst_size <= 0) return;

    int written = 0;
    if (src) {
        int needed = WideCharToMultiByte(CP_UTF8, 0, src, -1, nullptr, 0, nullptr, nullptr);
        if (needed > 0) {
            if (needed <= dst_size) {
                int rc = WideCharToMultiByte(CP_UTF8, 0, src, -1, dst, dst_size, nullptr, nullptr);
                if (rc > 0) return;  // success — null-terminated by WideCharToMultiByte
                // fall through: dst[0] = '\0'
            } else {
                // Value exceeds the slot: convert fully into a temp buffer, then copy
                // the prefix. Walk back from the cut point to avoid splitting a UTF-8
                // multi-byte sequence (continuation bytes have the high bits 10xxxxxx).
                std::string tmp(needed - 1, '\0');
                int rc = WideCharToMultiByte(CP_UTF8, 0, src, -1, tmp.data(), needed, nullptr, nullptr);
                if (rc > 0) {
                    int cut = dst_size - 1;
                    while (cut > 0 && (static_cast<unsigned char>(tmp[cut]) & 0xC0) == 0x80)
                        --cut;
                    std::memcpy(dst, tmp.data(), cut);
                    written = cut;
                }
            }
        }
    }
    dst[written] = '\0';
}

#endif // _WIN32
