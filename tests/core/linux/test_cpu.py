import builtins
import subprocess

from hwprobe.core.linux.cpu import (
    _arm_cpu_cores,
    _arm_cpu_model,
    _arm_version,
    _cpu_threads,
    _x86_cpu_cores,
    _x86_cpu_model,
    _x86_flags,
    fetch_arm_cpu_info,
    fetch_cpu_info,
    fetch_x86_cpu_info,
)
from hwprobe.models.status_models import StatusType


class TestArmCpuCores:
    """Tests for _arm_cpu_cores function."""

    def test_arm_cpu_cores_success(self, monkeypatch):
        output = "# comment\n0,0,0,0\n1,0,0,0\n2,1,0,0\n3,1,0,0\n"

        def mock_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=output)

        monkeypatch.setattr(subprocess, "run", mock_run)

        cores = _arm_cpu_cores()
        assert cores == 2

    def test_arm_cpu_cores_single_core(self, monkeypatch):
        output = "# comment\n0,0,0,0\n"

        def mock_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=output)

        monkeypatch.setattr(subprocess, "run", mock_run)

        cores = _arm_cpu_cores()
        assert cores == 1

    def test_arm_cpu_cores_failure(self, monkeypatch):
        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "lscpu")

        monkeypatch.setattr(subprocess, "run", mock_run)

        assert _arm_cpu_cores() is None


class TestX86CpuCores:
    """Tests for _x86_cpu_cores function."""

    def test_x86_cpu_cores_success(self):
        cpu_lines = "cpu cores\t: 4\n"
        assert _x86_cpu_cores(cpu_lines) == 4

    def test_x86_cpu_cores_with_other_info(self):
        cpu_lines = "model name\t: Intel CPU\ncpu cores\t: 6\nflags\t\t: sse\n"
        assert _x86_cpu_cores(cpu_lines) == 6

    def test_x86_cpu_cores_missing(self):
        cpu_lines = "model name\t: Intel CPU\n"
        assert _x86_cpu_cores(cpu_lines) is None

    def test_x86_cpu_cores_non_numeric(self):
        cpu_lines = "cpu cores\t: abc\n"
        assert _x86_cpu_cores(cpu_lines) is None


class TestArmCpuModel:
    """Tests for _arm_cpu_model function."""

    def test_arm_cpu_model_hardware(self):
        raw = "Hardware\t: BCM2711\n"
        assert _arm_cpu_model(raw) == "BCM2711"

    def test_arm_cpu_model_model_field(self):
        raw = "Model\t: Raspberry Pi 4 Model B Rev 1.5\n"
        assert _arm_cpu_model(raw) == "Raspberry Pi 4 Model B Rev 1.5"

    def test_arm_cpu_model_hardware_priority(self):
        raw = "Hardware\t: BCM2711\nModel\t: Raspberry Pi 4\n"
        # Hardware takes priority over Model
        assert _arm_cpu_model(raw) == "BCM2711"

    def test_arm_cpu_model_missing(self):
        raw = "processor\t: 0\n"
        assert _arm_cpu_model(raw) is None


class TestX86CpuModel:
    """Tests for _x86_cpu_model function."""

    def test_x86_cpu_model_intel(self):
        cpu_lines = "model name\t: Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz\n"
        assert _x86_cpu_model(cpu_lines) == "Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz"

    def test_x86_cpu_model_amd(self):
        cpu_lines = "model name\t: AMD Ryzen 5 3600 6-Core Processor\n"
        assert _x86_cpu_model(cpu_lines) == "AMD Ryzen 5 3600 6-Core Processor"

    def test_x86_cpu_model_missing(self):
        cpu_lines = "processor\t: 0\n"
        assert _x86_cpu_model(cpu_lines) is None


class TestArmVersion:
    """Tests for _arm_version function."""

    def test_arm_version_v8(self):
        raw = "CPU architecture: 8\n"
        assert _arm_version(raw) == "8"

    def test_arm_version_v7(self):
        raw = "CPU architecture: 7\n"
        assert _arm_version(raw) == "7"

    def test_arm_version_missing(self):
        raw = "processor\t: 0\n"
        assert _arm_version(raw) is None


class TestCpuThreads:
    """Tests for _cpu_threads function."""

    def test_cpu_threads_single(self):
        raw = "processor\t: 0\n"
        assert _cpu_threads(raw) == 1

    def test_cpu_threads_multiple(self):
        raw = "processor\t: 0\nother info\nprocessor\t: 1\nother info\nprocessor\t: 2\nother info\nprocessor\t: 3\n"
        assert _cpu_threads(raw) == 4

    def test_cpu_threads_empty(self):
        raw = ""
        assert _cpu_threads(raw) is None


class TestX86Flags:
    """Tests for _x86_flags function."""

    def test_x86_flags_sse_variants(self):
        cpu_lines = "flags\t\t: sse sse2 sse3 ssse3 sse4_1 sse4_2\n"
        flags = _x86_flags(cpu_lines)
        assert "SSE" in flags
        assert "SSE2" in flags
        assert "SSE3" in flags
        assert "SSSE3" in flags
        assert "SSE4.1" in flags
        assert "SSE4.2" in flags

    def test_x86_flags_with_lm(self):
        cpu_lines = "flags\t\t: sse lm\n"
        flags = _x86_flags(cpu_lines)
        assert "LM" in flags

    def test_x86_flags_missing(self):
        cpu_lines = "model name\t: Intel CPU\n"
        flags = _x86_flags(cpu_lines)
        # Should return None when flags not found
        assert flags is None

    def test_x86_flags_empty(self):
        cpu_lines = "flags\t\t: \n"
        flags = _x86_flags(cpu_lines)
        # Empty flags value doesn't match regex (.+ requires at least one char)
        assert flags is None


class TestFetchArmCpuInfo:
    """Tests for fetch_arm_cpu_info function."""

    def test_fetch_arm_cpu_info_success(self, monkeypatch):
        raw = "processor\t: 0\nprocessor\t: 1\nCPU architecture: 8\nHardware\t: BCM2711\n"

        monkeypatch.setattr(
            "hwprobe.core.linux.cpu._arm_cpu_cores",
            lambda: 4,
        )

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.architecture == "ARM"
        assert cpu.name == "BCM2711"
        assert cpu.arch_version == "8"
        assert cpu.threads == 2
        assert cpu.cores == 4
        assert cpu.status.messages == []

    def test_fetch_arm_cpu_info_model_fallback(self, monkeypatch):
        raw = "processor\t: 0\nCPU architecture: 7\nModel\t: Raspberry Pi 4\n"

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.name == "Raspberry Pi 4"

    def test_fetch_arm_cpu_info_missing_name(self, monkeypatch):
        raw = "processor\t: 0\nCPU architecture: 8\n"

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find model name" in cpu.status.messages

    def test_fetch_arm_cpu_info_missing_arch_version(self, monkeypatch):
        raw = "processor\t: 0\nHardware\t: BCM2711\n"

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find architecture" in cpu.status.messages

    def test_fetch_arm_cpu_info_missing_threads(self, monkeypatch):
        raw = "Hardware\t: BCM2711\nCPU architecture: 8\n"

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find CPU threads" in cpu.status.messages

    def test_fetch_arm_cpu_info_missing_cores(self, monkeypatch):
        raw = "processor\t: 0\nHardware\t: BCM2711\nCPU architecture: 8\n"

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: None)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find CPU cores" in cpu.status.messages

    def test_fetch_arm_cpu_info_all_missing(self, monkeypatch):
        raw = ""

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: None)

        cpu = fetch_arm_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert len(cpu.status.messages) == 4


class TestFetchX86CpuInfo:
    """Tests for fetch_x86_cpu_info function."""

    def test_fetch_x86_cpu_info_success(self):
        raw = (
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz\n"
            "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault pti ssbd ibrs ibpb stibp tpr_shadow flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid mpx rdseed adx smap clflushopt intel_pt xsaveopt xsavec xgetbv1 xsaves dtherm arat pln pts hwp hwp_notify hwp_act_window hwp_epp vnmi md_clear flush_l1d arch_capabilities ibpb_exit_to_user\n"
            "cpu cores\t: 2\n"
            "\n"
            "processor\t: 1\n"
            "vendor_id\t: GenuineIntel\n"
            "model name\t: Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz\n"
            "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf pni pclmulqdq dtes64 monitor ds_cpl vmx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault pti ssbd ibrs ibpb stibp tpr_shadow flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid mpx rdseed adx smap clflushopt intel_pt xsaveopt xsavec xgetbv1 xsaves dtherm arat pln pts hwp hwp_notify hwp_act_window hwp_epp vnmi md_clear flush_l1d arch_capabilities ibpb_exit_to_user\n"
            "cpu cores\t: 2\n"
        )

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.architecture == "x86"
        assert cpu.name == "Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz"
        assert cpu.vendor == "intel"
        assert cpu.bitness == 64
        assert cpu.cores == 2
        assert cpu.threads == 2
        assert "SSE" in cpu.sse_flags
        assert "SSE2" in cpu.sse_flags
        assert "SSE4.1" in cpu.sse_flags
        assert "SSE4.2" in cpu.sse_flags
        assert cpu.status.messages == []

    def test_fetch_x86_cpu_info_amd_vendor(self):
        raw = "model name\t: AMD Ryzen 5 3600 6-Core Processor\nflags\t\t: sse lm\ncpu cores\t: 6\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.vendor == "amd"

    def test_fetch_x86_cpu_info_unknown_vendor(self):
        raw = "model name\t: Generic CPU\nflags\t\t: sse lm\ncpu cores\t: 4\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.vendor == "unknown"

    def test_fetch_x86_cpu_info_32bit(self):
        raw = "model name\t: Intel CPU\nflags\t\t: sse sse2\ncpu cores\t: 2\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.bitness == 32

    def test_fetch_x86_cpu_info_missing_name(self):
        raw = "flags\t\t: sse lm\ncpu cores\t: 4\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find CPU name and vendor" in cpu.status.messages

    def test_fetch_x86_cpu_info_missing_flags(self):
        raw = "model name\t: Intel CPU\ncpu cores\t: 4\n\n"

        cpu = fetch_x86_cpu_info(raw)

        # When flags line is missing, status is PARTIAL
        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find CPU flags" in cpu.status.messages
        assert cpu.bitness == 32  # Default when flags missing

    def test_fetch_x86_cpu_info_missing_cores(self):
        raw = "model name\t: Intel CPU\nflags\t\t: sse lm\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.status.type == StatusType.PARTIAL
        assert "Could not find cpu cores" in cpu.status.messages

    def test_fetch_x86_cpu_info_threads_count(self):
        raw = (
            "model name\t: Intel CPU\n"
            "flags\t\t: sse lm\n"
            "cpu cores\t: 2\n"
            "\n"
            "model name\t: Intel CPU\n"
            "flags\t\t: sse lm\n"
            "cpu cores\t: 2\n"
            "\n"
            "model name\t: Intel CPU\n"
            "flags\t\t: sse lm\n"
            "cpu cores\t: 2\n"
            "\n"
            "model name\t: Intel CPU\n"
            "flags\t\t: sse lm\n"
            "cpu cores\t: 2\n"
        )

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.threads == 4

    def test_fetch_x86_cpu_info_empty_input(self):
        raw = ""

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.status.type == StatusType.FAILED
        assert "Could not parse CPU info" in cpu.status.messages

    def test_fetch_x86_cpu_info_whitespace_only(self):
        raw = "\n\n\n"

        cpu = fetch_x86_cpu_info(raw)

        assert cpu.status.type == StatusType.FAILED
        assert "Could not parse CPU info" in cpu.status.messages


class TestFetchCpuInfo:
    """Tests for fetch_cpu_info function."""

    def test_fetch_cpu_info_x86_success(self, monkeypatch):
        raw = "model name\t: Intel CPU\nflags\t\t: lm sse\ncpu cores\t: 4\n\n"

        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO(raw)

        monkeypatch.setattr(builtins, "open", mock_open)
        monkeypatch.setattr("hwprobe.core.linux.cpu.platform.machine", lambda: "x86_64")

        cpu = fetch_cpu_info()
        assert cpu.architecture == "x86"
        assert cpu.name == "Intel CPU"

    def test_fetch_cpu_info_arm_aarch64(self, monkeypatch):
        raw = "Hardware\t: BCM2711\nCPU architecture: 8\nprocessor\t: 0\n"

        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO(raw)

        monkeypatch.setattr(builtins, "open", mock_open)
        monkeypatch.setattr("hwprobe.core.linux.cpu.platform.machine", lambda: "aarch64")

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_cpu_info()
        assert cpu.architecture == "ARM"
        assert cpu.name == "BCM2711"

    def test_fetch_cpu_info_arm_armv7(self, monkeypatch):
        raw = "Hardware\t: BCM2835\nCPU architecture: 7\nprocessor\t: 0\n"

        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO(raw)

        monkeypatch.setattr(builtins, "open", mock_open)
        monkeypatch.setattr("hwprobe.core.linux.cpu.platform.machine", lambda: "armv7l")

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_cpu_info()
        assert cpu.architecture == "ARM"

    def test_fetch_cpu_info_failure_file_open(self, monkeypatch):
        def mock_open(*args, **kwargs):
            raise FileNotFoundError("No such file")

        monkeypatch.setattr(builtins, "open", mock_open)

        cpu = fetch_cpu_info()
        assert cpu.status.type == StatusType.FAILED
        assert any("Could not open /proc/cpuinfo" in msg for msg in cpu.status.messages)

    def test_fetch_cpu_info_empty_file(self, monkeypatch):
        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO("")

        monkeypatch.setattr(builtins, "open", mock_open)

        cpu = fetch_cpu_info()
        assert cpu.status.type == StatusType.FAILED
        assert any("/proc/cpuinfo has no content" in msg for msg in cpu.status.messages)


class TestLinuxCPURealWorld:
    """Integration tests using real-world CPU info files."""

    def test_fetch_cpu_info_rpi_success(self, monkeypatch):
        with open("tests/assets/raw_cpu_info/rpi.txt", "r") as f:
            raw = f.read()

        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO(raw)

        monkeypatch.setattr(builtins, "open", mock_open)
        monkeypatch.setattr("hwprobe.core.linux.cpu.platform.machine", lambda: "aarch64")

        monkeypatch.setattr("hwprobe.core.linux.cpu._arm_cpu_cores", lambda: 4)

        cpu = fetch_cpu_info()
        assert cpu.architecture == "ARM"
        assert cpu.name == "Raspberry Pi 4 Model B Rev 1.5"
        assert cpu.arch_version == "8"
        assert cpu.threads == 4
        assert cpu.cores == 4

    def test_fetch_cpu_info_7200u_success(self, monkeypatch):
        with open("tests/assets/raw_cpu_info/7200u.txt", "r") as f:
            raw = f.read()

        def mock_open(*args, **kwargs):
            from io import StringIO

            return StringIO(raw)

        monkeypatch.setattr(builtins, "open", mock_open)

        def mock_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout="x86_64")

        monkeypatch.setattr(subprocess, "run", mock_run)

        cpu = fetch_cpu_info()
        assert cpu.architecture == "x86"
        assert cpu.name == "Intel(R) Core(TM) i5-7200U CPU @ 2.50GHz"
        assert cpu.vendor == "intel"
        assert cpu.bitness == 64
        assert cpu.cores == 2
        assert cpu.threads == 4
        assert "SSE4.2" in cpu.sse_flags
