import ctypes
from ctypes import wintypes

from hwprobe.core.windows.win_enum import CPU_ARCHITECTURES, FEATURE_ID_MAP
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.status_models import StatusType
from hwprobe.interops.win.bindings import wmi

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.IsProcessorFeaturePresent.argtypes = [wintypes.DWORD]
kernel32.IsProcessorFeaturePresent.restype = wintypes.BOOL


def is_processor_feature_present(feature_id: int) -> bool:
    """
    Checks whether the specified processor feature is present.

    :param feature_id: One of the PF_* constants defined by Windows.
    :return: True if the feature is present, False otherwise.
    """
    return bool(kernel32.IsProcessorFeaturePresent(feature_id))


def get_arm_version() -> str:
    """
    We use instructions that were introduced in different ARM versions to determine the ARM version.

    Introduced in ARMv9:
    - SVE2 - FEAT_SSVE_FP8DOT2 (78), FEAT_SSVE_FP8DOT4 (79), and FEAT_SSVE_FP8FMA (80)

    Introduced in ARMv8:
    - Full AArch64 Instructions - FEAT_SME_FA64 (88)

    Otherwise
    - we can assume it's ARMv7 or lower.

    ref: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent
    """
    if any(is_processor_feature_present(i) for i in [78, 79, 80]):
        return "9"
    elif is_processor_feature_present(88):
        return "8"
    else:
        return "7 or lower"


def get_features() -> list[str]:
    """
    We use the Win32 API function IsProcessorFeaturePresent to check for SSE features.
    https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent

    Feature IDs:
    - SSE - 6
    - SSE2 - 10
    - SSE3 - 13
    - SSSE3 - 36
    - SSE4.1 - 37
    - SSE4.2 - 38
    """

    return [k for k, v in FEATURE_ID_MAP.items() if is_processor_feature_present(v)]


def fetch_cpu_info() -> CPUInfo:
    cpu_info = CPUInfo()

    wmi_data = wmi.get_wmi_data("Win32_Processor", ["Name", "Manufacturer", "Architecture", "AddressWidth", "MaxClockSpeed", "NumberOfCores", "NumberOfLogicalProcessors"])
    if wmi_data:
        cpu_info.name = wmi_data[0]["Name"].strip()
        cpu_info.vendor = "AMD" if "amd" in wmi_data[0]["Manufacturer"].lower() else "Intel" if "intel" in wmi_data[0]["Manufacturer"].lower() else wmi_data[0]["Manufacturer"].strip()
        cpu_info.architecture = CPU_ARCHITECTURES.get(int(wmi_data[0]["Architecture"]), "Unknown")
        cpu_info.bitness = int(wmi_data[0]["AddressWidth"])
        cpu_info.cores = int(wmi_data[0]["NumberOfCores"])
        cpu_info.threads = int(wmi_data[0]["NumberOfLogicalProcessors"])

        features = get_features()
        cpu_info.sse_flags = features

    else:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("Unable to obtain CPU Info: WMI query returned no data.")

    return cpu_info
