// Winsock FIRST (must be before windows.h)
#include <winsock2.h>
#include <ws2tcpip.h>

// Core Windows
#include <windows.h>

// IP Helper (depends on winsock + windows)
#include <iphlpapi.h>
#include <IPTypes.h>

// Setup / device enumeration
#include <setupapi.h>
#include <devguid.h>
#include <devpkey.h>

#include <cfgmgr32.h>

// DXGI
#include <dxgi1_6.h>

// Core Audio API
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>
#include <devicetopology.h>
#include <endpointvolume.h>

// COM / WMI
#include <WbemIdl.h>
#include <comutil.h>
#include <propvarutil.h>

// SHLW Api
#include <shlwapi.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <cwctype>

#include "hw_helper.hpp"

#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "wbemuuid.lib")
#pragma comment(lib, "comsuppw.lib")
#pragma comment(lib, "Propsys.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "setupapi.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "cfgmgr32.lib")

// Helper: get SMBIOS string by index
static char *GetSMBIOSString(const uint8_t *strings, uint8_t index)
{
    if (index == 0)
        return nullptr;

    const char *p = reinterpret_cast<const char *>(strings);
    while (--index && *p)
    {
        p += std::strlen(p) + 1;
    }

    return *p ? const_cast<char *>(p) : nullptr;
}

// Helper: convert wide string to char buffer
void ws2s(const WCHAR *wstr, char *buffer, int bufferSize)
{
    WideCharToMultiByte(CP_ACP, 0, wstr, -1, buffer, bufferSize, nullptr, nullptr);
}

// Helper: convert wide string to std::string
std::string WideToUtf8(PCWSTR src)
{
    if (!src || !*src)
        return {};

    int len = WideCharToMultiByte(
        CP_UTF8,
        0,
        src,
        -1,
        nullptr,
        0,
        nullptr,
        nullptr);

    if (len <= 1)
        return {};

    std::string out(len - 1, '\0');

    WideCharToMultiByte(
        CP_UTF8,
        0,
        src,
        -1,
        &out[0], // ✅ writable buffer
        len,
        nullptr,
        nullptr);

    return out;
}

// Helper: look up endpoint DataFlow from Core Audio API by matching friendly name
std::string GetEndpointDataFlow(const std::string &endpointName)
{
    std::string dataFlow = "Unknown";

    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE)
        return dataFlow;

    IMMDeviceEnumerator *pEnumerator = NULL;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL, IID_PPV_ARGS(&pEnumerator))))
    {
        if (hr == S_OK)
            CoUninitialize();
        return dataFlow;
    }

    EDataFlow flows[] = {eRender, eCapture};
    const char *flowNames[] = {"Render", "Capture"};

    for (int flow = 0; flow < 2; flow++)
    {
        IMMDeviceCollection *pDevices = NULL;
        if (FAILED(pEnumerator->EnumAudioEndpoints(flows[flow], DEVICE_STATE_ACTIVE, &pDevices)))
            continue;

        UINT count = 0;
        pDevices->GetCount(&count);

        for (UINT d = 0; d < count; d++)
        {
            IMMDevice *pDevice = NULL;
            if (FAILED(pDevices->Item(d, &pDevice)))
                continue;

            IPropertyStore *pProps = NULL;
            if (FAILED(pDevice->OpenPropertyStore(STGM_READ, &pProps)))
            {
                pDevice->Release();
                continue;
            }

            PROPVARIANT varName;
            PropVariantInit(&varName);

            if (FAILED(pProps->GetValue(PKEY_Device_FriendlyName, &varName)))
            {
                pProps->Release();
                pDevice->Release();
                continue;
            }

            std::string currentName = WideToUtf8(varName.pwszVal);

            // match by friendly name
            if (currentName == endpointName)
            {
                dataFlow = flowNames[flow];
                PropVariantClear(&varName);
                pProps->Release();
                pDevice->Release();
                pDevices->Release();
                pEnumerator->Release();
                if (hr == S_OK)
                    CoUninitialize();
                return dataFlow;
            }

            PropVariantClear(&varName);
            pProps->Release();
            pDevice->Release();
        }

        pDevices->Release();
    }

    pEnumerator->Release();
    if (hr == S_OK)
        CoUninitialize();

    return dataFlow;
}

// Core function
HardwareHelper_RESULT GetGPUForDisplayInternal(const char *deviceName, char *outGPUName, unsigned int bufSize)
{
    if (deviceName == nullptr || strlen(deviceName) == 0)
        return STATUS_INVALID_ARG;

    if (outGPUName == nullptr)
        return STATUS_INVALID_ARG;

    if (bufSize <= 0)
        return STATUS_INVALID_ARG;

    IDXGIFactory6 *factory = nullptr;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))))
    {
        if (outGPUName && bufSize > 0)
            outGPUName[0] = 0;
        return STATUS_FAILURE;
    }

    IDXGIAdapter1 *adapter = nullptr;
    for (UINT a = 0; factory->EnumAdapters1(a, &adapter) != DXGI_ERROR_NOT_FOUND; ++a)
    {
        DXGI_ADAPTER_DESC1 descAdapter;
        if (FAILED(adapter->GetDesc1(&descAdapter)))
        {
            adapter->Release();
            continue;
        }

        IDXGIOutput *output = nullptr;
        for (UINT o = 0; adapter->EnumOutputs(o, &output) != DXGI_ERROR_NOT_FOUND; ++o)
        {
            DXGI_OUTPUT_DESC descOutput;
            if (FAILED(output->GetDesc(&descOutput)))
            {
                output->Release();
                continue;
            }

            char outName[128] = {};
            ws2s(descAdapter.Description, outName, sizeof(outName));

            char devName[32] = {};
            ws2s(descOutput.DeviceName, devName, sizeof(devName));

            if (strcmp(devName, deviceName) != 0)
            {
                output->Release();
                continue;
            }

            // Found matching device
            if (outGPUName && bufSize > 0)
            {
                strncpy(outGPUName, outName, bufSize - 1);
                outGPUName[bufSize - 1] = 0;
            }
            output->Release();
            adapter->Release();
            factory->Release();
            return STATUS_OK;
        }

        adapter->Release();
    }

    if (factory)
        factory->Release();
    if (outGPUName && bufSize > 0)
        outGPUName[0] = 0;

    // Parent GPU not found, return failure code
    return STATUS_FAILURE;
}

// DLL export
extern "C" __declspec(dllexport) HardwareHelper_RESULT GetGPUForDisplay(const char *deviceName, char *outGPUName, int bufSize)
{
    return GetGPUForDisplayInternal(deviceName, outGPUName, bufSize);
}

extern "C" __declspec(dllexport) HardwareHelper_RESULT GetDisplayPathInfo(char *connectorOut, int bufSize)
{
    long retCode;
    std::string outputStr;
    uint32_t pathCount, modeCount;

    retCode = GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &pathCount, &modeCount);
    if (retCode != ERROR_SUCCESS)
        return STATUS_FAILURE;

    DISPLAYCONFIG_PATH_INFO *pathInfo = new DISPLAYCONFIG_PATH_INFO[pathCount];
    DISPLAYCONFIG_MODE_INFO *modeInfo = new DISPLAYCONFIG_MODE_INFO[modeCount];
    retCode = QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &pathCount, pathInfo, &modeCount, modeInfo, nullptr);
    if (retCode != ERROR_SUCCESS)
        return STATUS_FAILURE;

    for (uint32_t i = 0; i < pathCount; i++)
    {
        DISPLAYCONFIG_PATH_INFO &path = pathInfo[i];

        DISPLAYCONFIG_SOURCE_DEVICE_NAME sourceDeviceName = {};
        sourceDeviceName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
        sourceDeviceName.header.size = sizeof(sourceDeviceName);
        sourceDeviceName.header.adapterId = path.sourceInfo.adapterId;
        sourceDeviceName.header.id = path.sourceInfo.id;

        retCode = DisplayConfigGetDeviceInfo(&sourceDeviceName.header);
        if (retCode != ERROR_SUCCESS)
            continue;

        DISPLAYCONFIG_TARGET_DEVICE_NAME targetDeviceName = {};
        targetDeviceName.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME;
        targetDeviceName.header.size = sizeof(targetDeviceName);
        targetDeviceName.header.adapterId = path.targetInfo.adapterId;
        targetDeviceName.header.id = path.targetInfo.id;

        retCode = DisplayConfigGetDeviceInfo(&targetDeviceName.header);
        if (retCode != ERROR_SUCCESS)
            continue;

        std::string displayId = WideToUtf8(sourceDeviceName.viewGdiDeviceName);
        std::string displayPath = WideToUtf8(targetDeviceName.monitorDevicePath);
        outputStr += "DisplayID=" + displayId + "|" +
                     "DisplayPath=" + displayPath + "|" +
                     "OutputTechnology=" + std::to_string(path.targetInfo.outputTechnology) + "\n";
    }

    if (outputStr.length() > 0)
    {
        strncpy_s(connectorOut, bufSize, outputStr.c_str(), _TRUNCATE);
        retCode = STATUS_OK;
    }
    else
    {
        retCode = STATUS_FAILURE;
    }

    delete[] pathInfo;
    delete[] modeInfo;
    return static_cast<HardwareHelper_RESULT>(retCode);
}

extern "C" __declspec(dllexport) void GetWmiInfo(char *wmiQuery, char *cimServer, char *outBuffer, int maxLen)
{
    if (cimServer == nullptr || strlen(cimServer) == 0)
        cimServer = "ROOT\\CIMV2";

    HRESULT hr = CoInitializeEx(0, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE)
        return;

    hr = CoInitializeSecurity(NULL, -1, NULL, NULL, RPC_C_AUTHN_LEVEL_DEFAULT,
                              RPC_C_IMP_LEVEL_IMPERSONATE, NULL, EOAC_NONE, NULL);

    IWbemLocator *pLoc = NULL;
    hr = CoCreateInstance(CLSID_WbemLocator, 0, CLSCTX_INPROC_SERVER, IID_IWbemLocator, (LPVOID *)&pLoc);
    if (FAILED(hr))
    {
        CoUninitialize();
        return;
    }

    IWbemServices *pSvc = NULL;
    hr = pLoc->ConnectServer(_bstr_t(cimServer), NULL, NULL, 0, NULL, 0, 0, &pSvc);
    if (FAILED(hr))
    {
        pLoc->Release();
        CoUninitialize();
        return;
    }

    hr = CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, NULL,
                           RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, NULL, EOAC_NONE);

    IEnumWbemClassObject *pEnumerator = NULL;
    hr = pSvc->ExecQuery(bstr_t("WQL"),
                         bstr_t(wmiQuery),
                         WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY, NULL, &pEnumerator);

    if (FAILED(hr))
    {
        pSvc->Release();
        pLoc->Release();
        CoUninitialize();
        return;
    }

    IWbemClassObject *pclsObj = NULL;
    ULONG uReturn = 0;
    std::string result = "";

    while (pEnumerator)
    {
        hr = pEnumerator->Next(WBEM_INFINITE, 1, &pclsObj, &uReturn);
        if (0 == uReturn)
            break;

        SAFEARRAY *pNames = nullptr;
        hr = pclsObj->GetNames(
            nullptr,
            WBEM_FLAG_NONSYSTEM_ONLY,
            nullptr,
            &pNames);

        if (FAILED(hr) || !pNames)
        {
            pclsObj->Release();
            continue;
        }

        LONG lBound = 0, uBound = -1;
        SafeArrayGetLBound(pNames, 1, &lBound);
        SafeArrayGetUBound(pNames, 1, &uBound);

        for (LONG i = lBound; i <= uBound; i++)
        {
            BSTR propName = nullptr;
            SafeArrayGetElement(pNames, &i, &propName);

            VARIANT vtProp;
            VariantInit(&vtProp);

            if (SUCCEEDED(pclsObj->Get(propName, 0, &vtProp, nullptr, nullptr)))
            {
                WCHAR variantStr[1024] = {};
                VariantToString(vtProp, variantStr, 1024);

                result += (const char *)_bstr_t(propName);
                result += "=";
                result += WideToUtf8(variantStr);
                result += "|";
            }

            VariantClear(&vtProp);
            SysFreeString(propName);
        }

        result += "\n";
        SafeArrayDestroy(pNames);
        pclsObj->Release();
    }

    strncpy_s(outBuffer, maxLen, result.c_str(), _TRUNCATE);

    // Cleanup
    if (pEnumerator)
        pEnumerator->Release();
    pSvc->Release();
    pLoc->Release();
    CoUninitialize();
}

extern "C" __declspec(dllexport) int GetNetworkHardwareInfo(char *outData, int outDataLen)
{
    if (outData == nullptr || outDataLen <= 0)
        return STATUS_INVALID_ARG;

    ULONG outBufLen = 15000;
    PIP_ADAPTER_ADDRESSES pAddresses = NULL;
    DWORD dwRetVal = 0;
    ULONG iterations = 0;

    do
    {
        pAddresses = (PIP_ADAPTER_ADDRESSES)malloc(outBufLen);
        if (pAddresses == NULL)
            return STATUS_FAILURE; // OOM

        dwRetVal = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_INCLUDE_ALL_INTERFACES, NULL, pAddresses, &outBufLen);
        if (dwRetVal == ERROR_BUFFER_OVERFLOW)
        {
            free(pAddresses);
            pAddresses = NULL;
        }
        else
        {
            break;
        }
        iterations++;
    } while ((dwRetVal == ERROR_BUFFER_OVERFLOW) && (iterations < 3));

    if (dwRetVal != NO_ERROR)
    {
        if (pAddresses)
            free(pAddresses);
        return STATUS_FAILURE;
    }

    HDEVINFO devInfo = SetupDiGetClassDevs(&GUID_DEVCLASS_NET, NULL, NULL, DIGCF_PRESENT);
    std::string result = "";

    for (PIP_ADAPTER_ADDRESSES aa = pAddresses; aa; aa = aa->Next)
    {
        if (aa->IfType == IF_TYPE_SOFTWARE_LOOPBACK)
            continue;

        std::wstring wDesc = (const wchar_t *)_bstr_t(aa->Description);
        std::wstring wFriendly = (const wchar_t *)_bstr_t(aa->FriendlyName);
        std::wstring wAdapterGuid = (const wchar_t *)_bstr_t(aa->AdapterName);

        std::wstring wManufacturer = L"Unknown";
        std::wstring wPnpInstanceId = wAdapterGuid; // Fallback to GUID if PnP ID not found

        bool foundInRegistry = false;

        if (devInfo != INVALID_HANDLE_VALUE)
        {
            SP_DEVINFO_DATA devData = {sizeof(SP_DEVINFO_DATA)};
            for (DWORD i = 0; SetupDiEnumDeviceInfo(devInfo, i, &devData); i++)
            {
                HKEY hKey = SetupDiOpenDevRegKey(devInfo, &devData, DICS_FLAG_GLOBAL, 0, DIREG_DRV, KEY_READ);
                if (hKey == INVALID_HANDLE_VALUE)
                    continue;

                WCHAR netCfgId[128];
                DWORD dwSize = sizeof(netCfgId);

                if (RegQueryValueExW(hKey, L"NetCfgInstanceId", NULL, NULL, (LPBYTE)netCfgId, &dwSize) != ERROR_SUCCESS)
                {
                    RegCloseKey(hKey);
                    continue;
                }

                if (_wcsicmp(netCfgId, wAdapterGuid.c_str()) != 0)
                {
                    RegCloseKey(hKey);
                    continue;
                }

                // Found matching adapter
                WCHAR pnpBuffer[MAX_DEVICE_ID_LEN];
                if (SetupDiGetDeviceInstanceIdW(devInfo, &devData, pnpBuffer, MAX_DEVICE_ID_LEN, NULL))
                    wPnpInstanceId = pnpBuffer;

                WCHAR mfgBuffer[256];
                if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_MFG, NULL, (PBYTE)mfgBuffer, sizeof(mfgBuffer), NULL))
                    wManufacturer = mfgBuffer;

                foundInRegistry = true;
                RegCloseKey(hKey);
                break;
            }
        }

        std::wstring upperPnp = wPnpInstanceId;
        for (auto &ch : upperPnp)
            ch = towupper(ch);

        if (upperPnp.find(L"PCI") == std::wstring::npos && upperPnp.find(L"USB") == std::wstring::npos)
            continue;

        result += "Manufacturer=" + WideToUtf8(wManufacturer.c_str()) + "|";
        result += "PNPDeviceID=" + WideToUtf8(wPnpInstanceId.c_str()) + "|";
        result += "Name=" + WideToUtf8(wDesc.c_str()) + "\n";
    }

    if (devInfo != INVALID_HANDLE_VALUE)
        SetupDiDestroyDeviceInfoList(devInfo);
    if (pAddresses)
        free(pAddresses);

    // Safety: if result is still empty, the machine has no adapters or permissions
    if (result.empty())
    {
        std::string err = "Error: No adapters found. RetVal=" + std::to_string(dwRetVal);
        strncpy_s(outData, outDataLen, err.c_str(), _TRUNCATE);
        return STATUS_FAILURE;
    }

    strncpy_s(outData, outDataLen, result.c_str(), _TRUNCATE);
    return STATUS_OK;
}

extern "C" __declspec(dllexport) int GetAudioHardwareInfo(char *outData, int outDataLen)
{
    if (outData == nullptr || outDataLen <= 0)
        return STATUS_INVALID_ARG;

    std::string finalResult = "";

    // enumerate audio hardware devices
    HDEVINFO devInfo = SetupDiGetClassDevs(&GUID_DEVCLASS_MEDIA, NULL, NULL, DIGCF_PRESENT);
    if (devInfo == INVALID_HANDLE_VALUE)
        return STATUS_FAILURE;

    SP_DEVINFO_DATA devData = {sizeof(SP_DEVINFO_DATA)};

    for (DWORD i = 0; SetupDiEnumDeviceInfo(devInfo, i, &devData); i++)
    {
        // get PNP Device ID
        WCHAR pnpBuffer[MAX_DEVICE_ID_LEN];
        if (!SetupDiGetDeviceInstanceIdW(devInfo, &devData, pnpBuffer, MAX_DEVICE_ID_LEN, NULL))
            continue;

        std::wstring wPnpDeviceID = pnpBuffer;

        // filter: skip virtual/software devices
        std::wstring upperPnp = wPnpDeviceID;
        for (auto &ch : upperPnp)
            ch = towupper(ch);

        // skip software devices (SWD), virtual devices (ROOT), and non-audio buses
        if (upperPnp.find(L"SWD\\") == 0 ||
            upperPnp.find(L"ROOT\\") == 0 ||
            upperPnp.find(L"SCPVBUS\\") != std::wstring::npos)
            continue;

        // only include real hardware buses
        if (upperPnp.find(L"HDAUDIO") == std::wstring::npos &&
            upperPnp.find(L"USB") == std::wstring::npos &&
            upperPnp.find(L"PCI") == std::wstring::npos)
            continue;

        // check if device is actually enabled/active
        DWORD status = 0, problem = 0;
        if (CM_Get_DevNode_Status(&status, &problem, devData.DevInst, 0) == CR_SUCCESS)
        {
            // skip disabled devices
            if (problem != 0 || !(status & DN_DRIVER_LOADED))
                continue;
        }

        // get device description (friendly name)
        WCHAR nameBuffer[256] = {0};
        std::wstring wName = L"Unknown";
        if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_DEVICEDESC,
                                              NULL, (PBYTE)nameBuffer, sizeof(nameBuffer), NULL))
        {
            wName = nameBuffer;
        }
        else if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_FRIENDLYNAME,
                                                   NULL, (PBYTE)nameBuffer, sizeof(nameBuffer), NULL))
        {
            wName = nameBuffer;
        }

        // get device class
        WCHAR classBuffer[32] = {0};
        std::wstring wDeviceClass = L"";
        if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_CLASS,
                                              NULL, (PBYTE)classBuffer, sizeof(classBuffer), NULL))
        {
            wDeviceClass = classBuffer;
        }

        // only include actual audio codec/controller devices
        std::wstring upperClass = wDeviceClass;
        for (auto &ch : upperClass)
            ch = towupper(ch);

        if (upperClass.find(L"SOFTWAREDEVICE") != std::wstring::npos ||
            upperClass.find(L"SYSTEM") != std::wstring::npos ||
            upperClass.find(L"VOLUMESHADOWCOPY") != std::wstring::npos)
            continue;

        // get Hardware IDs - physical devices have proper hardware IDs
        WCHAR hwIdBuffer[512] = {0};
        DWORD hwIdSize = 0;
        bool hasValidHwId = false;
        if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_HARDWAREID,
                                              NULL, (PBYTE)hwIdBuffer, sizeof(hwIdBuffer), &hwIdSize))
        {
            if (hwIdSize > 0)
            {
                std::wstring hwId = hwIdBuffer;
                if (hwId.find(L"VEN_") != std::wstring::npos ||
                    hwId.find(L"VID_") != std::wstring::npos)
                {
                    hasValidHwId = true;
                }
            }
        }

        // only include devices that have actual hardware vendor IDs
        if (!hasValidHwId)
            continue;

        // get manufacturer
        WCHAR mfgBuffer[256] = {0};
        std::wstring wManufacturer = L"Unknown";
        if (SetupDiGetDeviceRegistryPropertyW(devInfo, &devData, SPDRP_MFG,
                                              NULL, (PBYTE)mfgBuffer, sizeof(mfgBuffer), NULL))
        {
            wManufacturer = mfgBuffer;
        }

        // output hardware device
        std::string hwLine = "Type=Hardware|Name=" + WideToUtf8(wName.c_str()) + "|";
        hwLine += "Manufacturer=" + WideToUtf8(wManufacturer.c_str()) + "|";
        hwLine += "PNPDeviceID=" + WideToUtf8(wPnpDeviceID.c_str());
        finalResult += hwLine + "\n";

        DEVINST childDevInst = 0;
        if (CM_Get_Child(&childDevInst, devData.DevInst, 0) != CR_SUCCESS)
            continue;

        // enumerate all children of this hardware device
        while (true)
        {
            WCHAR childPnpBuffer[MAX_DEVICE_ID_LEN];
            if (CM_Get_Device_IDW(childDevInst, childPnpBuffer, MAX_DEVICE_ID_LEN, 0) == CR_SUCCESS)
            {
                // get child device friendly name
                WCHAR childNameBuffer[256] = {0};
                ULONG childNameSize = sizeof(childNameBuffer);
                if (CM_Get_DevNode_Registry_PropertyW(childDevInst, CM_DRP_FRIENDLYNAME,
                                                      NULL, childNameBuffer, &childNameSize, 0) == CR_SUCCESS)
                {
                    std::string childName = WideToUtf8(childNameBuffer);

                    // lookup dataflow from core audio api by matching endpoint name
                    std::string dataFlow = GetEndpointDataFlow(childName);

                    // assumption: if the data flown isn't known, the endpoint is not active/usable
                    if (dataFlow != "Unknown")
                    {
                        // output child endpoint
                        std::string epLine = "Type=Endpoint|Name=" + childName + "|";
                        epLine += "DataFlow=" + dataFlow + "|";
                        epLine += "ParentPNPDeviceID=" + WideToUtf8(wPnpDeviceID.c_str());
                        finalResult += epLine + "\n";
                    }
                }
            }

            // get next sibling
            DEVINST nextSiblingDevInst = 0;
            if (CM_Get_Sibling(&nextSiblingDevInst, childDevInst, 0) != CR_SUCCESS)
                break;

            childDevInst = nextSiblingDevInst;
        }
    }

    SetupDiDestroyDeviceInfoList(devInfo);

    if (finalResult.empty())
    {
        std::string err = "Error: No audio hardware or endpoints found";
        strncpy_s(outData, outDataLen, err.c_str(), _TRUNCATE);
        return STATUS_FAILURE;
    }

    strncpy_s(outData, outDataLen, finalResult.c_str(), _TRUNCATE);
    return STATUS_OK;
}

/**
 * Fetches the following information:
    - Motherboard Manufacturer
    - Motherboard Model
    - Chassis Type
    - CPU Socket Type
 */
extern "C" __declspec(dllexport)
HardwareHelper_RESULT
FetchSMBIOSData(SMBIOSHwInfo *outInfo)
{
    if (!outInfo)
        return STATUS_FAILURE;

    memset(outInfo, 0, sizeof(SMBIOSHwInfo));

    DWORD size = GetSystemFirmwareTable('RSMB', 0, nullptr, 0);
    if (!size)
        return STATUS_FAILURE;

    std::vector<uint8_t> buffer(size);
    if (!GetSystemFirmwareTable('RSMB', 0, buffer.data(), size))
        return STATUS_FAILURE;

    const uint8_t *p = buffer.data() + 8; // Skip SMBIOS entry header

    while (true)
    {
        const auto *hdr = reinterpret_cast<const SMBIOSHeader *>(p);
        if (hdr->Type == 127)
            break;

        const uint8_t *strings = p + hdr->Length;

        switch (hdr->Type)
        {
        case 2: // Baseboard
        {
            const auto *bb = reinterpret_cast<const SMBIOSBaseboard *>(p);

            const char *man =
                GetSMBIOSString(strings, bb->Manufacturer);
            const char *prod =
                GetSMBIOSString(strings, bb->Product);

            if (man)
                strncpy_s(outInfo->motherboardManufacturer,
                          man, _TRUNCATE);

            if (prod)
                strncpy_s(outInfo->motherboardModel,
                          prod, _TRUNCATE);
            break;
        }

        case 3: // Chassis
        {
            const auto *ch = reinterpret_cast<const SMBIOSChassis *>(p);

            if (ch->ChassisType >= 0x25u)
            {
                strncpy_s(outInfo->chassisType,
                          "Unknown", _TRUNCATE);
                break;
            }
            const char *typeStr = CHASSIS_TYPE_MAPPING[ch->ChassisType];

            if (typeStr != nullptr && strlen(typeStr) > 0)
                strncpy_s(outInfo->chassisType,
                          typeStr, _TRUNCATE);
            break;
        }

        case 4: // Processor
        {
            const auto *cpu = reinterpret_cast<const SMBIOSProcessor *>(p);

            // Are we dealing with SMBIOS 3.6+ structure?
            if (hdr->Length >= 0x33)
            {
                const char *socketType = GetSMBIOSString(strings, cpu->SocketType);
                if (socketType && strlen(socketType) > 0)
                {
                    strncpy_s(outInfo->cpuSocket, socketType, _TRUNCATE);
                    break;
                }
            }

            // If not, try SocketDesignation string
            const char *socketDesignation = GetSMBIOSString(strings, cpu->SocketDesignation);
            if (socketDesignation && strlen(socketDesignation) > 0)
            {
                strncpy_s(outInfo->cpuSocket, socketDesignation, _TRUNCATE);
            }
            // If SocketDesignation is empty, try ProcessorUpgrade field
            // This enumeration is not the most reliable, but it can be useful as a last resort
            else if (cpu->ProcessorUpgrade < 0xFFu)
            {
                const char *socketStr = PROCESSOR_UPGRADE_MAPPING[cpu->ProcessorUpgrade];
                strncpy_s(outInfo->cpuSocket, socketStr, _TRUNCATE);
            }

            // If all enumeration methods fail, set to Unknown
            else
            {
                strncpy_s(outInfo->cpuSocket, "Unknown", _TRUNCATE);
            }
            break;
        }

        default:
            break;
        }

        // Advance to next SMBIOS structure
        const uint8_t *next = strings;
        while (!(next[0] == 0 && next[1] == 0))
            ++next;
        p = next + 2;
    }

    return STATUS_OK;
}
