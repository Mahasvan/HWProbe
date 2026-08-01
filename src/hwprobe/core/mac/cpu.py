import subprocess

from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.status_models import StatusType


def fetch_cpu_info() -> CPUInfo:
    cpu_info = CPUInfo()

    try:
        data = subprocess.check_output(["sysctl", "machdep.cpu"]).decode()
        """
        Sample output:
        machdep.cpu.cores_per_package: 8
        machdep.cpu.core_count: 8
        machdep.cpu.logical_per_package: 8
        machdep.cpu.thread_count: 8
        machdep.cpu.brand_string: Apple M3
        """
        # we split it into lines, and make a dictionary with key:value pairs
        data = dict(x.split(": ", 1) for x in data.splitlines() if ": " in x)
    except Exception as e:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("Error while parsing sysctl: " + str(e))
        return cpu_info

    try:
        arch = subprocess.check_output(["uname", "-m"]).decode()
        """
        Output:
        x86_64 for late-model Intel Macs
        i386 for earlier Intel Macs
        arm64 for Apple Silicon
        """
    except Exception as e:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("Error while getting architecture: " + str(e))
        return cpu_info

    if not arch:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("No output from uname -m")
        arch = ""

    if "arm" in arch.lower():
        cpu_info.architecture = "ARM"
        cpu_info.bitness = 64
    elif "i386" in arch.lower() or "x86" in arch.lower():
        cpu_info.architecture = "x86"
    else:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Unknown CPU architecture")

    try:
        bitness_64 = subprocess.check_output(["sysctl", "hw.cpu64bit_capable"]).decode()
        bitness_64 = bitness_64.split(": ")[1].strip() == "1"

        if bitness_64:
            cpu_info.bitness = 64
        else:
            cpu_info.bitness = 32

    except Exception as e:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Error when checking CPU Architecture: " + str(e))

    if "machdep.cpu.brand_string" in data:
        cpu_info.name = data["machdep.cpu.brand_string"]
    else:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Unable to determine CPU model")

    if "machdep.cpu.vendor" in data:
        """
        Common outputs:
        AuthenticAMD - AMD CPUs
        GenuineIntel - Intel CPUs
        This field doesnt exist for Apple M series CPUs
        """
        if "amd" in data["machdep.cpu.vendor"].lower():
            cpu_info.vendor = "AMD"
        elif "intel" in data["machdep.cpu.vendor"].lower():
            cpu_info.vendor = "Intel"
        else:
            # Python 3.9 won't run on PowerPC, so we can be sure that it's an Apple CPU
            # Apple Silicon machines usually dont have the machdep.cpu.vendor string
            # So, this branch will likely not execute. This is defined just in case.
            cpu_info.vendor = "Apple"
    elif "apple" in data.get("machdep.cpu.brand_string", "").lower():
        # Apple Silicon devices do not have machdep.cpu.vendor defined.
        cpu_info.vendor = "Apple"

    # Apple Silicon machines do not have this field defined.
    # todo: check if we can get this info another way.
    if "machdep.cpu.features" in data:
        sse_features = [f.upper() for f in data["machdep.cpu.features"].split(" ") if "SSE" in f.upper()]
        if sse_features:
            cpu_info.sse_flags = sse_features
        else:
            cpu_info.status.type = StatusType.PARTIAL
            cpu_info.status.messages.append("Unable to determine SSE Flags")

    try:
        if "machdep.cpu.core_count" in data:
            cpu_info.cores = int(data["machdep.cpu.core_count"])
        else:
            cpu_info.status.type = StatusType.PARTIAL
            cpu_info.status.messages.append(f"Invalid CPU Cores: {data.get('machdep.cpu.core_count')}")
        if "machdep.cpu.thread_count" in data:
            cpu_info.threads = int(data["machdep.cpu.thread_count"])
        else:
            cpu_info.status.type = StatusType.PARTIAL
            cpu_info.status.messages.append(f"Invalid CPU Threads: {data.get('machdep.cpu.thread_count')}")
    except Exception as e:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Unable to determine CPU Info: " + str(e))

    # Attempt to get ARM version
    """
    in macOS, ARM can be of version 8 or 9.
    We can differentiate between v8 and v9 based on the presence of v9 capabilities,
    such as SME and SME2. Apple has not implemented SVE2 capabilities to their CPUs, so we cannot use those. 
    """
    # todo: Detect minor ARM versions as well, like 8.X and 9.X ?
    if "arm" in arch.lower():
        try:
            sme_presence = subprocess.check_output(["sysctl", "hw.optional.arm.FEAT_SME"]).decode()
            sme_presence = sme_presence.split(": ")[1].strip() == "1"

            sme2_presence = subprocess.check_output(["sysctl", "hw.optional.arm.FEAT_SME2"]).decode()
            sme2_presence = sme2_presence.split(": ")[1].strip() == "1"

            if sme_presence or sme2_presence:
                cpu_info.arch_version = "9"
            else:
                cpu_info.arch_version = "8"
        except Exception as e:
            cpu_info.status.type = StatusType.PARTIAL
            cpu_info.status.messages.append("Unable to determine ARM Version: " + str(e))

    return cpu_info
