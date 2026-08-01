from __future__ import annotations

import re
import subprocess
from typing import Optional

from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.status_models import StatusType


def _arm_cpu_cores() -> Optional[int]:
    try:
        result = subprocess.run(["lscpu", "-p"], capture_output=True, text=True, check=True).stdout
        lines = [x for x in result.splitlines() if not x.startswith("#")]
        # Format: CPU,Core,Socket,Node,,L1d,L1i,L2,L3
        core_ids = [x.split(",")[1] for x in lines]
        # The number of distinct Core IDs is the number of cores
        return len(set(core_ids))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _x86_cpu_cores(cpu_lines: str) -> Optional[int]:
    cores = re.search(r"cpu cores\s+:\s+(.+)", cpu_lines)
    if cores and cores.group(1).isnumeric():
        return int(cores.group(1))
    return None


def _arm_cpu_model(raw_cpu_info: str) -> Optional[str]:
    model = re.search(r"Hardware\s+:\s+(.+)", raw_cpu_info)
    model_alt = re.search(r"Model\s+:\s+(.+)", raw_cpu_info)
    name = None

    if model:
        name = model.group(1)
    elif model_alt:
        name = model_alt.group(1)

    return name


def _x86_cpu_model(cpu_lines: str) -> Optional[str]:
    model = re.search(r"model name\s+:\s+(.+)", cpu_lines)
    if model:
        return model.group(1)
    return None


def _arm_version(raw_cpu_info: str) -> Optional[str]:
    if arm_version := re.search(r"CPU architecture:\s+(.+)", raw_cpu_info):
        return arm_version.group(1)
    return None


def _cpu_threads(raw_cpu_info: str) -> Optional[int]:
    try:
        count = len(re.findall(r"^processor\s+:", raw_cpu_info, re.MULTILINE))
        return count if count > 0 else None
    except Exception:
        return None


def _x86_flags(cpu_lines: str) -> Optional[list[str]]:
    flags_match = re.search(r"flags\s+:\s+(.+)", cpu_lines)
    if not flags_match:
        return None

    flags = flags_match.group(1)
    flags = [x.lower().strip() for x in flags.split(" ")]
    flags = [flag.replace("_", ".").upper() for flag in flags if flag]
    return flags


def fetch_arm_cpu_info(raw_cpu_info: str) -> CPUInfo:
    cpu_info = CPUInfo()

    cpu_info.architecture = "ARM"

    cpu_info.name = _arm_cpu_model(raw_cpu_info)
    if not cpu_info.name:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find model name")

    cpu_info.arch_version = _arm_version(raw_cpu_info)
    if not cpu_info.arch_version:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find architecture")

    cpu_info.threads = _cpu_threads(raw_cpu_info)
    if not cpu_info.threads:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find CPU threads")

    cpu_info.cores = _arm_cpu_cores()
    if not cpu_info.cores:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find CPU cores")

    # nothing more can be retrieved from /proc/cpuinfo for ARM
    return cpu_info


def fetch_x86_cpu_info(raw_cpu_info: str) -> CPUInfo:
    cpu_info = CPUInfo()

    cpu_info.architecture = "x86"

    info_lines = [x for x in raw_cpu_info.split("\n\n") if x.strip("\n")]

    if not info_lines:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("Could not parse CPU info")
        return cpu_info

    # CPU Info is enumerated as many times as there are CPU Threads.
    # To get the info, we only need to parse the first entry - i.e. the first CPU Thread
    cpu_lines = info_lines[0]

    if name := _x86_cpu_model(cpu_lines):
        cpu_info.name = name
        cpu_info.vendor = "intel" if "intel" in name.lower() else "amd" if "amd" in name.lower() else "unknown"
    else:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find CPU name and vendor")

    # The CPU flags are in the format of "flags : sse sse2 sse3 ssse3 sse4_1 sse4_2 lm"
    flags = _x86_flags(cpu_lines)

    if flags:
        cpu_info.sse_flags = [f for f in flags if "SSE" in f]
        # If "lm" is in flags, then x86-64 Long Mode is supported
        # Which means it's a 64-bit CPU
        # https://superuser.com/questions/502605/is-my-cpu-32-bit-or-64-bit-output-from-lshw-lscpu-getconf-and-proc-cpuinfo
        cpu_info.bitness = 64 if "LM" in flags else 32
    else:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find CPU flags")
        cpu_info.bitness = 32

    # Cores are in the format of "cores : 6"
    if cores := _x86_cpu_cores(cpu_lines):
        cpu_info.cores = cores
    else:
        cpu_info.status.type = StatusType.PARTIAL
        cpu_info.status.messages.append("Could not find cpu cores")

    # The number of CPU Threads is the number of times the processor data is enumerated.
    cpu_info.threads = len(info_lines)

    return cpu_info


def fetch_cpu_info() -> CPUInfo:
    cpu_info = CPUInfo()

    # todo: Check if any of the regexes may suffer from string having two `\t`s
    try:
        with open("/proc/cpuinfo") as f:
            raw_cpu_info = f.read()
    except Exception as e:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append(f"Could not open /proc/cpuinfo: {e!s}")
        return cpu_info

    if not raw_cpu_info:
        cpu_info.status.type = StatusType.FAILED
        cpu_info.status.messages.append("/proc/cpuinfo has no content")
        return cpu_info

    architecture = subprocess.run(["uname", "-m"], capture_output=True, text=True, check=True)

    if ("aarch64" in architecture.stdout) or ("arm" in architecture.stdout):
        return fetch_arm_cpu_info(raw_cpu_info)

    return fetch_x86_cpu_info(raw_cpu_info)

    # todo: get CPU codename from CodenameManager
