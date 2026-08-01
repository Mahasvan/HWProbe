#pragma once

#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

// ABI caps. Raising any of these is a recompile on both sides.
// Fixed caps avoid heap ownership across the FFI boundary.
//   16 fields covers every WMI class hwprobe queries (max today: 9).
//   512 chars per field covers PNPDeviceID paths and uint64 string forms.
//   64 rows covers memory modules, disks, NICs on any realistic machine.
#define WMI_MAX_FIELDS 16
#define WMI_FIELD_LEN  512
#define WMI_MAX_ROWS   64

// One WMI row. values[i] corresponds to the i-th entry in the `fields` array
// passed to get_wmi_data. Missing/null/empty properties are written as "".
// Each slot is null-terminated and never overflows WMI_FIELD_LEN-1.
typedef struct {
    char values[WMI_MAX_FIELDS][WMI_FIELD_LEN];
} WmiRow;

// Run a WQL query of the form `SELECT f1,f2,... FROM <wmi_class>` against
// `namespace_str` (e.g. "ROOT\\CIMV2") and fill `out` with up to `max_rows`
// rows. Returns the number of rows written, or -1 on any COM/WMI failure.
//
// `fields` is an array of `field_count` null-terminated UTF-8 strings, in the
// order the caller wants the values back. `field_count` must be <=
// WMI_MAX_FIELDS. `max_rows` must be <= WMI_MAX_ROWS.
//
// Trust boundary: `wmi_class`, `fields`, `namespace_str` are identifiers, not
// free text — they come from hardcoded literals in core/windows/*.py, never
// from end users. No escaping is applied.
int get_wmi_data(const char *wmi_class,
                 const char *const *fields,
                 int field_count,
                 const char *namespace_str,
                 WmiRow *out,
                 int max_rows);

#ifdef __cplusplus
}
#endif
