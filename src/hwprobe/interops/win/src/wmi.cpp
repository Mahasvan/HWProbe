// WMI wrapper for the new Windows interop. One generic function, no
// delimiter-based text format. See include/wmi.h for the ABI.

#include "wmi.h"

#include <windows.h>
#include <ole2.h>
#include <oleauto.h>
#include <wbemidl.h>

#include <string>
#include <cstring>

// #pragma comment(lib, ...) is MSVC-only; mingw ignores it. Linking is
// handled by CMakeLists.txt (target_link_libraries ... ole32 oleaut32 wbemuuid).
#ifdef _MSC_VER
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "wbemuuid.lib")
#endif

// ---- RAII BSTR from UTF-8 ----
// _bstr_t's const-char* constructor calls _com_util::ConvertStringToBSTR,
// which lives in libcomsupp — a separate lib MSVC auto-links via pragma and
// mingw does not (and whose name varies across mingw distributions). Roll the
// one thing we need: SysAllocString from a wide string. No comsupp, no comdef.
class Bstr {
public:
    explicit Bstr(const char *utf8) {
        if (!utf8 || !*utf8) { b_ = SysAllocString(L""); return; }
        int wlen = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);
        if (wlen <= 0) { b_ = nullptr; return; }
        std::wstring w(wlen - 1, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, utf8, -1, w.data(), wlen);
        b_ = SysAllocString(w.c_str());
    }
    ~Bstr() { if (b_) SysFreeString(b_); }
    Bstr(const Bstr &) = delete;
    Bstr &operator=(const Bstr &) = delete;
    operator BSTR() const { return b_; }
private:
    BSTR b_;
};

// ---- VARIANT -> fixed UTF-8 slot ----
// Writes a null-terminated UTF-8 rendering of vt into dst[0..dst_size-1].
// Missing/null/empty -> "". Overlong values are truncated cleanly at
// dst_size-1 (WideCharToMultiByte fails rather than truncates when the
// output doesn't fit, so we convert into a temp buffer first).
static void WideToUtf8Slot(const wchar_t *src, char *dst, int dst_size) {
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

static void VariantToUtf8Slot(VARIANT &vt, char *dst, int dst_size) {
    if (!dst || dst_size <= 0) return;

    const wchar_t *src = nullptr;
    VARIANT vtBstr;
    VariantInit(&vtBstr);

    if (vt.vt == VT_BSTR) {
        src = vt.bstrVal;
    } else if (vt.vt != VT_NULL && vt.vt != VT_EMPTY) {
        HRESULT hr = VariantChangeType(&vtBstr, &vt, 0, VT_BSTR);
        if (SUCCEEDED(hr)) src = vtBstr.bstrVal;
    }

    WideToUtf8Slot(src, dst, dst_size);
    VariantClear(&vtBstr);
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

    // Per-call CoInitializeEx. Idempotent via RPC_E_CHANGED_MODE.
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
    Bstr nsBstr(namespace_str);
    hr = pLoc->ConnectServer(nsBstr,
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

    IEnumWbemClassObject *pEnum = nullptr;
    Bstr lang("WQL"), query(wql.c_str());
    hr = pSvc->ExecQuery(lang, query,
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
            Bstr field(fields[i]);
            hr = pObj->Get(field, 0, &vtProp, nullptr, nullptr);
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
