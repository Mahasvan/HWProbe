import ctypes
from ctypes import wintypes

from hwprobe.core.windows.win_enum import CPU_ARCHITECTURES, FEATURE_ID_MAP
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.status_models import StatusType
from hwprobe.interops.win.bindings import wmi

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.IsProcessorFeaturePresent.argtypes = [wintypes.DWORD]
kernel32.IsProcessorFeaturePresent.restype = wintypes.BOOL

# ARM processor feature IDs for IsProcessorFeaturePresent.
# ref: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent
PF_SSVE_FP8DOT2 = 78   # ARMv9 — FEAT_SSVE_FP8DOT2
PF_SSVE_FP8DOT4 = 79   # ARMv9 — FEAT_SSVE_FP8DOT4
PF_SSVE_FP8FMA = 80    # ARMv9 — FEAT_SSVE_FP8FMA
PF_SME_FA64 = 88       # ARMv8 — FEAT_SME_FA64


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
    if any(is_processor_feature_present(i) for i in [PF_SSVE_FP8DOT2, PF_SSVE_FP8DOT4, PF_SSVE_FP8FMA]):
        return "9"
    elif is_processor_feature_present(PF_SME_FA64):
        return "8"
    else:
        return "7 or lower"


def get_features() -> list[str]:
    """
    We use the Win32 API function IsProcessorFeaturePresent to check for SSE features.
    https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent
    """

    return [k for k, v in FEATURE_ID_MAP.items() if is_processor_feature_present(v)]


def fetch_cpu_info() -> CPUInfo:
    cpu_info = CPUInfo()

    try:
        wmi_data = wmi.get_wmi_data("Win32_Processor", ["Name", "Manufacturer", "Architecture", "AddressWidth", "MaxClockSpeed", "NumberOfCores", "NumberOfLogicalProcessors"])
    except Exception as e:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append(f"Unable to obtain CPU Info: WMI query failed: {e}")
        return cpu_info

    if wmi_data:
        row = wmi_data[0]
        cpu_info.name = row["Name"].strip()
        cpu_info.vendor = "AMD" if "amd" in row["Manufacturer"].lower() else "Intel" if "intel" in row["Manufacturer"].lower() else row["Manufacturer"].strip()

        # WMI returns "" for missing/null properties; int("") raises ValueError.
        # Guard with .isdigit(), matching memory.py and storage.py.
        arch = row["Architecture"]
        cpu_info.architecture = CPU_ARCHITECTURES.get(int(arch), "Unknown") if arch and arch.isdigit() else "Unknown"
        addr_width = row["AddressWidth"]
        cpu_info.bitness = int(addr_width) if addr_width and addr_width.isdigit() else None
        cores = row["NumberOfCores"]
        cpu_info.cores = int(cores) if cores and cores.isdigit() else None
        threads = row["NumberOfLogicalProcessors"]
        cpu_info.threads = int(threads) if threads and threads.isdigit() else None

        features = get_features()
        cpu_info.sse_flags = features

    else:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("Unable to obtain CPU Info: WMI query returned no data.")

    return cpu_info
