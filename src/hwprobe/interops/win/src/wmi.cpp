// WMI wrapper for the new Windows interop. One generic function, no
// delimiter-based text format. See include/wmi.h for the ABI.

#include "wmi.h"

#include <windows.h>
#include <ole2.h>
#include <wbemidl.h>
#include <comdef.h>

#include <string>

// #pragma comment(lib, ...) is MSVC-only; mingw ignores it. Linking is
// handled by CMakeLists.txt (target_link_libraries ... ole32 oleaut32 wbemuuid).
#ifdef _MSC_VER
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "wbemuuid.lib")
#endif

// ---- VARIANT -> fixed UTF-8 slot ----
// Writes a null-terminated UTF-8 rendering of vt into dst[0..dst_size-1].
// Missing/null/empty -> "". Never overflows.
static void VariantToUtf8Slot(VARIANT &vt, char *dst, int dst_size) {
    if (dst_size <= 0) return;
    dst[0] = '\0';
    if (vt.vt == VT_NULL || vt.vt == VT_EMPTY) return;

    HRESULT hr;
    BSTR bstr = nullptr;

    if (vt.vt == VT_BSTR) {
        bstr = vt.bstrVal;
    } else {
        VARIANT vtBstr;
        VariantInit(&vtBstr);
        hr = VariantChangeType(&vtBstr, &vt, 0, VT_BSTR);
        if (FAILED(hr)) {
            VariantClear(&vtBstr);
            return;
        }
        bstr = vtBstr.bstrVal;
        // Convert into dst, then clear.
        if (bstr) {
            int len = WideCharToMultiByte(CP_UTF8, 0, bstr, -1, nullptr, 0, nullptr, nullptr);
            if (len > 0) {
                if (len > dst_size) len = dst_size;
                WideCharToMultiByte(CP_UTF8, 0, bstr, -1, dst, len, nullptr, nullptr);
                dst[dst_size - 1] = '\0';
            }
        }
        VariantClear(&vtBstr);
        return;
    }

    // VT_BSTR fast path.
    if (bstr) {
        int len = WideCharToMultiByte(CP_UTF8, 0, bstr, -1, nullptr, 0, nullptr, nullptr);
        if (len > 0) {
            if (len > dst_size) len = dst_size;
            WideCharToMultiByte(CP_UTF8, 0, bstr, -1, dst, len, nullptr, nullptr);
            dst[dst_size - 1] = '\0';
        }
    }
}

// ---- public entry ----
extern "C" __declspec(dllexport) int get_wmi_data(const char *wmi_class,
                                                   const char *const *fields,
                                                   int field_count,
                                                   const char *namespace_str,
                                                   WmiRow *out,
                                                   int max_rows)
{
    if (!wmi_class || !fields || !out || field_count <= 0 || max_rows <= 0)
        return -1;
    if (field_count > WMI_MAX_FIELDS) return -1;
    if (max_rows > WMI_MAX_ROWS) max_rows = WMI_MAX_ROWS;
    if (!namespace_str || !*namespace_str) namespace_str = "ROOT\\CIMV2";

    // ponytail: per-call CoInitializeEx. Idempotent via RPC_E_CHANGED_MODE.
    //   Switch to a process-wide RAII guard if profiling shows COM init in the
    //   hot path; today it isn't.
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) return -1;
    bool did_init = (hr != RPC_E_CHANGED_MODE && hr != S_FALSE);

    // CoInitializeSecurity may legitimately already be set on this thread;
    // RPC_E_TOO_LATE is harmless.
    CoInitializeSecurity(nullptr, -1, nullptr, nullptr,
                         RPC_C_AUTHN_LEVEL_DEFAULT,
                         RPC_C_IMP_LEVEL_IMPERSONATE,
                         nullptr, EOAC_NONE, nullptr);

    IWbemLocator *pLoc = nullptr;
    hr = CoCreateInstance(CLSID_WbemLocator, 0, CLSCTX_INPROC_SERVER,
                          IID_IWbemLocator, reinterpret_cast<LPVOID *>(&pLoc));
    if (FAILED(hr)) {
        if (did_init) CoUninitialize();
        return -1;
    }

    // ConnectServer signature:
    //   HRESULT ConnectServer(BSTR strNetworkResource, BSTR strUser,
    //                          BSTR strPassword, BSTR strLocale,
    //                          LONG lSecurityFlags, BSTR strAuthority,
    //                          IWbemContext *pCtx, IWbemServices **ppNamespace)
    // lSecurityFlags is LONG — pass 0, not nullptr. nullptr won't convert to
    // long under mingw (MSVC tolerates it via NULL==0, mingw does not).
    IWbemServices *pSvc = nullptr;
    hr = pLoc->ConnectServer(_bstr_t(namespace_str),
                             nullptr,   // strUser
                             nullptr,   // strPassword
                             nullptr,   // strLocale
                             0,         // lSecurityFlags
                             nullptr,   // strAuthority
                             nullptr,   // pCtx
                             &pSvc);    // ppNamespace
    if (FAILED(hr)) {
        pLoc->Release();
        if (did_init) CoUninitialize();
        return -1;
    }

    CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
                      RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE,
                      nullptr, EOAC_NONE);

    // Build "SELECT f1,f2,... FROM <class>". Identifiers only — no escaping.
    std::string wql = "SELECT ";
    for (int i = 0; i < field_count; ++i) {
        if (i) wql += ",";
        wql += fields[i];
    }
    wql += " FROM ";
    wql += wmi_class;

    // _bstr_t (not bstr_t — the lowercase typedef is MSVC-only, mingw does
    // not define it). _bstr_t is the actual class in both MSVC and mingw-w64.
    IEnumWbemClassObject *pEnum = nullptr;
    hr = pSvc->ExecQuery(_bstr_t("WQL"), _bstr_t(wql.c_str()),
                         WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY,
                         nullptr, &pEnum);
    if (FAILED(hr)) {
        pSvc->Release();
        pLoc->Release();
        if (did_init) CoUninitialize();
        return -1;
    }

    int rows = 0;
    while (rows < max_rows) {
        IWbemClassObject *pObj = nullptr;
        ULONG uReturn = 0;
        hr = pEnum->Next(WBEM_INFINITE, 1, &pObj, &uReturn);
        if (uReturn == 0) break;
        if (FAILED(hr)) {
            if (pObj) pObj->Release();
            break;
        }

        WmiRow &row = out[rows];
        for (int i = 0; i < field_count; ++i) {
            VARIANT vtProp;
            VariantInit(&vtProp);
            hr = pObj->Get(_bstr_t(fields[i]), 0, &vtProp, nullptr, nullptr);
            if (SUCCEEDED(hr)) {
                VariantToUtf8Slot(vtProp, row.values[i], WMI_FIELD_LEN);
            } else {
                row.values[i][0] = '\0';
            }
            VariantClear(&vtProp);
        }
        // Zero any unused slots beyond field_count for clean dict-building on
        // the Python side (it zips only field_count entries, but defensive).
        for (int i = field_count; i < WMI_MAX_FIELDS; ++i) {
            row.values[i][0] = '\0';
        }

        pObj->Release();
        ++rows;
    }

    pEnum->Release();
    pSvc->Release();
    pLoc->Release();
    if (did_init) CoUninitialize();
    return rows;
}
