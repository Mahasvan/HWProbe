from unittest.mock import patch

from hwprobe.core.mac.cpu import fetch_cpu_info
from hwprobe.models.status_models import StatusType

# ── sample sysctl outputs ────────────────────────────────────────────────────

SYSCTL_APPLE_M3 = (
    "machdep.cpu.cores_per_package: 8\n"
    "machdep.cpu.core_count: 8\n"
    "machdep.cpu.logical_per_package: 8\n"
    "machdep.cpu.thread_count: 8\n"
    "machdep.cpu.brand_string: Apple M3\n"
)

SYSCTL_INTEL = (
    "machdep.cpu.cores_per_package: 6\n"
    "machdep.cpu.core_count: 6\n"
    "machdep.cpu.logical_per_package: 12\n"
    "machdep.cpu.thread_count: 12\n"
    "machdep.cpu.brand_string: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz\n"
    "machdep.cpu.vendor: GenuineIntel\n"
    "machdep.cpu.features: FPU VME DE PSE TSC MSR PAE MCE CX8 APIC SEP MTRR PGE "
    "MCA CMOV PAT PSE36 CLFSH DS ACPI MMX FXSR SSE SSE2 SS HTT TM PBE SSE3 "
    "PCLMULQDQ DTES64 MON DSCPL VMX EST TM2 SSSE3 FMA CX16 TPR PDCM SSE4.1 SSE4.2 "
    "x2APIC MOVBE POPCNT AES PCID XSAVE OSXSAVE SEGLIM64 TSCTMOUT AVX1.0 RDRAND F16C\n"
)

SYSCTL_AMD = (
    "machdep.cpu.cores_per_package: 8\n"
    "machdep.cpu.core_count: 8\n"
    "machdep.cpu.logical_per_package: 16\n"
    "machdep.cpu.thread_count: 16\n"
    "machdep.cpu.brand_string: AMD Ryzen 7 5800X\n"
    "machdep.cpu.vendor: AuthenticAMD\n"
    "machdep.cpu.features: FPU VME SSE SSE2 SSE3 SSE4.1 SSE4.2\n"
)

SYSCTL_BITNESS_64 = "hw.cpu64bit_capable: 1\n"
SYSCTL_BITNESS_32 = "hw.cpu64bit_capable: 0\n"

SYSCTL_SME_PRESENT = "hw.optional.arm.FEAT_SME: 1\n"
SYSCTL_SME_ABSENT = "hw.optional.arm.FEAT_SME: 0\n"
SYSCTL_SME2_PRESENT = "hw.optional.arm.FEAT_SME2: 1\n"
SYSCTL_SME2_ABSENT = "hw.optional.arm.FEAT_SME2: 0\n"


# ── helpers ──────────────────────────────────────────────────────────────────


def _mock_check_output(
    sysctl_cpu, arch="arm64", bitness=SYSCTL_BITNESS_64, sme=SYSCTL_SME_ABSENT, sme2=SYSCTL_SME2_ABSENT
):
    """Build a side_effect for subprocess.check_output that returns
    the right value depending on the command argument."""

    def side_effect(cmd):
        if cmd == ["sysctl", "machdep.cpu"]:
            return sysctl_cpu.encode()
        if cmd == ["uname", "-m"]:
            return arch.encode()
        if cmd == ["sysctl", "hw.cpu64bit_capable"]:
            return bitness.encode()
        if cmd == ["sysctl", "hw.optional.arm.FEAT_SME"]:
            return sme.encode()
        if cmd == ["sysctl", "hw.optional.arm.FEAT_SME2"]:
            return sme2.encode()
        raise FileNotFoundError(f"Unexpected command: {cmd}")

    return side_effect


# ── Apple Silicon happy path ─────────────────────────────────────────────────


class TestAppleSiliconCPU:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_apple_m3_basic_info(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3)
        info = fetch_cpu_info()

        assert info.name == "Apple M3"
        assert info.architecture == "ARM"
        assert info.bitness == 64
        assert info.vendor == "Apple"
        assert info.cores == 8
        assert info.threads == 8

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_apple_silicon_arm_v9_detected(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, sme=SYSCTL_SME_PRESENT)
        info = fetch_cpu_info()
        assert info.arch_version == "9"

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_apple_silicon_arm_v8_detected(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, sme=SYSCTL_SME_ABSENT, sme2=SYSCTL_SME2_ABSENT)
        info = fetch_cpu_info()
        assert info.arch_version == "8"

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_apple_silicon_sme2_alone_triggers_v9(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, sme=SYSCTL_SME_ABSENT, sme2=SYSCTL_SME2_PRESENT)
        info = fetch_cpu_info()
        assert info.arch_version == "9"

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_apple_silicon_no_sse_flags(self, mock_co):
        """Apple Silicon machines don't have machdep.cpu.features; sse_flags should be empty."""
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3)
        info = fetch_cpu_info()
        assert info.sse_flags == []


# ── Intel happy path ─────────────────────────────────────────────────────────


class TestIntelCPU:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_intel_basic_info(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_INTEL, arch="x86_64")
        info = fetch_cpu_info()

        assert info.name == "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"
        assert info.architecture == "x86"
        assert info.bitness == 64
        assert info.vendor == "Intel"
        assert info.cores == 6
        assert info.threads == 12

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_intel_sse_flags_extracted(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_INTEL, arch="x86_64")
        info = fetch_cpu_info()

        assert "SSE" in info.sse_flags
        assert "SSE2" in info.sse_flags
        assert "SSE3" in info.sse_flags
        assert "SSE4.1" in info.sse_flags
        assert "SSE4.2" in info.sse_flags
        assert "SSSE3" in info.sse_flags

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_intel_i386_arch(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_INTEL, arch="i386")
        info = fetch_cpu_info()
        assert info.architecture == "x86"

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_intel_no_arm_version(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_INTEL, arch="x86_64")
        info = fetch_cpu_info()
        assert info.arch_version is None

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_intel_32bit(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_INTEL, arch="i386", bitness=SYSCTL_BITNESS_32)
        info = fetch_cpu_info()
        assert info.bitness == 32


# ── AMD ──────────────────────────────────────────────────────────────────────


class TestAMDCPU:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_amd_vendor_detected(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_AMD, arch="x86_64")
        info = fetch_cpu_info()
        assert info.vendor == "AMD"
        assert info.cores == 8
        assert info.threads == 16


# ── Error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_sysctl_failure_returns_failed(self, mock_co):
        mock_co.side_effect = FileNotFoundError("sysctl not found")
        info = fetch_cpu_info()
        assert info.status.type == StatusType.FAILED

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_uname_failure_returns_failed(self, mock_co):
        def side_effect(cmd):
            if cmd == ["sysctl", "machdep.cpu"]:
                return SYSCTL_APPLE_M3.encode()
            raise FileNotFoundError("uname not found")

        mock_co.side_effect = side_effect
        info = fetch_cpu_info()
        assert info.status.type == StatusType.FAILED

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_bitness_check_failure_is_partial(self, mock_co):
        def side_effect(cmd):
            if cmd == ["sysctl", "machdep.cpu"]:
                return SYSCTL_APPLE_M3.encode()
            if cmd == ["uname", "-m"]:
                return b"arm64"
            if cmd == ["sysctl", "hw.cpu64bit_capable"]:
                raise FileNotFoundError("no such sysctl")
            if cmd[0] == "sysctl" and "FEAT_SME" in cmd[1]:
                return SYSCTL_SME_ABSENT.encode()
            if cmd[0] == "sysctl" and "FEAT_SME2" in cmd[1]:
                return SYSCTL_SME2_ABSENT.encode()
            raise FileNotFoundError(f"Unexpected: {cmd}")

        mock_co.side_effect = side_effect
        info = fetch_cpu_info()
        # ARM sets bitness=64 before the sysctl check, so it's still 64
        assert info.bitness == 64
        assert info.status.type == StatusType.PARTIAL

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_unknown_arch_is_partial(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, arch="riscv64")
        info = fetch_cpu_info()
        assert info.status.type == StatusType.PARTIAL
        assert any("Unknown" in m for m in info.status.messages)

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_empty_uname_output_is_partial(self, mock_co):
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, arch="")
        info = fetch_cpu_info()
        assert info.status.type == StatusType.PARTIAL


# ── BUG: sysctl output with trailing empty line crashes split ────────────────


class TestSysctlParsingEdgeCases:
    """Malformed sysctl lines (without ': ') should be skipped, not crash."""

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_sysctl_line_without_separator_is_skipped(self, mock_co):
        """A line without ': ' in sysctl output is silently skipped.
        Valid lines are still parsed successfully."""
        bad_sysctl = (
            "machdep.cpu.brand_string: Apple M3\n"
            "machdep.cpu.core_count: 8\n"
            "machdep.cpu.thread_count: 8\n"
            "MALFORMED LINE WITHOUT SEPARATOR\n"
        )
        mock_co.side_effect = _mock_check_output(bad_sysctl)
        info = fetch_cpu_info()
        assert info.name == "Apple M3"
        assert info.cores == 8
        assert info.threads == 8


# ── BUG: KeyError when both vendor and brand_string are absent ───────────────


class TestMissingBrandString:
    """When both vendor and brand_string are absent, vendor should remain None
    without crashing."""

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_missing_vendor_and_brand_string_no_crash(self, mock_co):
        minimal_sysctl = "machdep.cpu.core_count: 4\nmachdep.cpu.thread_count: 4\n"
        mock_co.side_effect = _mock_check_output(minimal_sysctl, arch="x86_64")
        info = fetch_cpu_info()
        assert info.vendor is None
        assert info.status.type == StatusType.PARTIAL


# ── BUG: Inconsistent arch casing in ARM version detection ───────────────────


class TestArchCasingConsistency:
    """ARM version detection should work regardless of uname casing."""

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_uppercase_arm_still_detects_version(self, mock_co):
        """ARM64 (uppercase) sets architecture=ARM and also detects ARM version."""
        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3, arch="ARM64")
        info = fetch_cpu_info()
        assert info.architecture == "ARM"
        assert info.arch_version in ("8", "9")


# ── Missing cores/threads ───────────────────────────────────────────────────


class TestMissingCoresThreads:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_missing_core_count_is_partial(self, mock_co):
        sysctl = "machdep.cpu.brand_string: Apple M3\nmachdep.cpu.thread_count: 8\n"
        mock_co.side_effect = _mock_check_output(sysctl)
        info = fetch_cpu_info()
        assert info.cores is None
        assert info.threads == 8
        assert info.status.type == StatusType.PARTIAL

    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_missing_thread_count_is_partial(self, mock_co):
        sysctl = "machdep.cpu.brand_string: Apple M3\nmachdep.cpu.core_count: 8\n"
        mock_co.side_effect = _mock_check_output(sysctl)
        info = fetch_cpu_info()
        assert info.cores == 8
        assert info.threads is None
        assert info.status.type == StatusType.PARTIAL


# ── Return type ──────────────────────────────────────────────────────────────


class TestReturnType:
    @patch("hwprobe.core.mac.cpu.subprocess.check_output")
    def test_return_type_is_cpu_info(self, mock_co):
        from hwprobe.models.cpu_models import CPUInfo

        mock_co.side_effect = _mock_check_output(SYSCTL_APPLE_M3)
        info = fetch_cpu_info()
        assert isinstance(info, CPUInfo)
