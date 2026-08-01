"""
Tests for hwprobe.core.mac.graphics.fetch_graphics_info

Strategy
--------
fetch_graphics_info imports the binding lazily (inside the try block), so
every test patches the binding at the point it is looked up:
    hwprobe.core.mac.graphics  <– the module under test

We build minimal fake GPUProperties / AppleGPUProperties objects that mirror
the real dataclasses from the binding, without importing the dylib at all.
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

from hwprobe.core.mac.graphics import fetch_graphics_info
from hwprobe.models.status_models import StatusType

# ── lightweight stand-ins for the binding's dataclasses ─────────────────────


@dataclass
class FakeAppleGPUProperties:
    core_count: int
    gpu_perf_shaders: int
    gpu_gen: int
    unified_memory_mb: int


@dataclass
class FakeGPUProperties:
    name: str
    vendor_id: int
    device_id: int
    is_apple_silicon: bool
    apple_gpu: Optional[FakeAppleGPUProperties]
    acpi_path: Optional[str] = None
    pci_path: Optional[str] = None
    vram_mb: int = 0


# ── helpers ──────────────────────────────────────────────────────────────────


def _apple_gpu(
    name="Apple M3 Pro",
    vendor_id=0x106B,
    device_id=0x0000,
    core_count=20,
    gpu_perf_shaders=8,
    gpu_gen=15,
    unified_memory_mb=18432,
) -> FakeGPUProperties:
    """Return a fully-populated Apple Silicon GPU stub."""
    return FakeGPUProperties(
        name=name,
        vendor_id=vendor_id,
        device_id=device_id,
        is_apple_silicon=True,
        apple_gpu=FakeAppleGPUProperties(
            core_count=core_count,
            gpu_perf_shaders=gpu_perf_shaders,
            gpu_gen=gpu_gen,
            unified_memory_mb=unified_memory_mb,
        ),
    )


def _discrete_gpu(
    name="NVIDIA GeForce RTX 3090",
    vendor_id=0x10DE,
    device_id=0x2204,
    vram_mb=24576,
) -> FakeGPUProperties:
    """Return a fully-populated discrete (non-Apple-Silicon) GPU stub."""
    return FakeGPUProperties(
        name=name,
        vendor_id=vendor_id,
        device_id=device_id,
        is_apple_silicon=False,
        apple_gpu=None,
        vram_mb=vram_mb,
    )


def _patch_binding(gpu_list):
    """
    Return a context-manager that patches the lazy import inside
    fetch_graphics_info so that get_gpu_info() returns *gpu_list*.
    """
    mock_module = MagicMock()
    mock_module.get_gpu_info.return_value = gpu_list
    mock_module.GPUProperties = FakeGPUProperties

    return patch.dict(
        "sys.modules",
        {"hwprobe.interops.mac.bindings.gpu_info": mock_module},
    )


# ── dylib / binding load failures ────────────────────────────────────────────


class TestBindingLoadFailures:
    """fetch_graphics_info must gracefully handle errors that arise when the
    C binding cannot be imported or when IOKit enumeration fails."""

    def test_dylib_not_found_returns_failed_status(self):
        """FileNotFoundError raised at module import time → FAILED with a rebuild hint.

        The binding raises FileNotFoundError at *module level* (not inside a
        function), so the exception surfaces when Python executes the
        ``from hwprobe.interops.mac.bindings.gpu_info import ...`` line
        inside fetch_graphics_info.

        We simulate this by installing a temporary meta-path finder that
        raises FileNotFoundError whenever that specific module is imported,
        then evicting it from sys.modules so the lazy import is forced to run.
        """
        import importlib.machinery
        import sys

        _TARGET = "hwprobe.interops.mac.bindings.gpu_info"

        class _DylibMissingFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname == _TARGET:
                    raise FileNotFoundError(
                        "libdevice_info.dylib not found at …/bindings/libdevice_info.dylib.\n"
                        "Build the project first:  cmake --build cmake-build-debug"
                    )

        finder = _DylibMissingFinder()
        sys.meta_path.insert(0, finder)
        sys.modules.pop(_TARGET, None)
        try:
            info = fetch_graphics_info()
        finally:
            sys.meta_path.remove(finder)
            sys.modules.pop(_TARGET, None)

        assert info.status.type == StatusType.FAILED
        assert any("libdevice_info.dylib" in m or "rebuild" in m.lower() for m in info.status.messages)
        assert info.modules == []

    def test_iokit_enumeration_failure_returns_failed_status(self):
        """RuntimeError (get_gpu_info returns -1) → FAILED."""
        mock_module = MagicMock()
        mock_module.get_gpu_info.side_effect = RuntimeError("get_gpu_info() failed (C library returned -1)")

        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)

        with patch.dict("sys.modules", {"hwprobe.interops.mac.bindings.gpu_info": mock_module}):
            info = fetch_graphics_info()

        assert info.status.type == StatusType.FAILED
        assert any("IOKit" in m or "-1" in m for m in info.status.messages)
        assert info.modules == []

    def test_unexpected_exception_returns_failed_status(self):
        """Any other exception during binding load → FAILED."""
        mock_module = MagicMock()
        mock_module.get_gpu_info.side_effect = OSError("Unexpected OS error")

        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)

        with patch.dict("sys.modules", {"hwprobe.interops.mac.bindings.gpu_info": mock_module}):
            info = fetch_graphics_info()

        assert info.status.type == StatusType.FAILED
        assert len(info.status.messages) == 1
        assert info.modules == []


# ── Apple Silicon GPU (happy path) ───────────────────────────────────────────


class TestAppleSiliconGPU:
    """Tests covering normal Apple Silicon GPU enumeration."""

    def _run(self, gpu_list):
        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)
        with _patch_binding(gpu_list):
            return fetch_graphics_info()

    def test_single_apple_silicon_gpu_success(self):
        info = self._run([_apple_gpu()])

        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 1

        gpu = info.modules[0]
        assert gpu.name == "Apple M3 Pro"
        assert gpu.vendor_id == "0x106b"
        assert gpu.manufacturer == "Apple Inc."
        # device_id 0x0000 on Apple Silicon is expected – must stay None in the model
        assert gpu.device_id is None

    def test_apple_silicon_vram_populated(self):
        info = self._run([_apple_gpu(unified_memory_mb=18432)])
        gpu = info.modules[0]
        assert gpu.vram is not None
        assert gpu.vram.capacity == 18432
        assert gpu.vram.unit == "MB"

    def test_apple_silicon_extended_info_populated(self):
        info = self._run([_apple_gpu(core_count=20, gpu_perf_shaders=8, gpu_gen=15)])
        gpu = info.modules[0]
        assert gpu.apple_gpu_info is not None
        assert gpu.apple_gpu_info.gpu_core_count == 20
        assert gpu.apple_gpu_info.performance_shader_count == 8
        assert gpu.apple_gpu_info.gpu_gen == 15

    def test_apple_silicon_no_device_id_is_not_partial(self):
        """0x0000 device_id on Apple Silicon must NOT set a partial status."""
        info = self._run([_apple_gpu(device_id=0x0000)])
        assert info.status.type == StatusType.SUCCESS

    def test_apple_silicon_nonzero_device_id_is_set(self):
        """If somehow an Apple Silicon GPU does report a device_id, it is stored."""
        info = self._run([_apple_gpu(device_id=0xABCD)])
        assert info.modules[0].device_id == hex(0xABCD)

    def test_apple_m1_gpu(self):
        info = self._run(
            [_apple_gpu(name="Apple M1", core_count=7, gpu_perf_shaders=0, gpu_gen=13, unified_memory_mb=8192)]
        )
        gpu = info.modules[0]
        assert gpu.name == "Apple M1"
        assert gpu.vram.capacity == 8192
        assert gpu.apple_gpu_info.gpu_core_count == 7
        assert gpu.apple_gpu_info.gpu_gen == 13

    def test_apple_m2_max_gpu(self):
        info = self._run(
            [_apple_gpu(name="Apple M2 Max", core_count=38, gpu_perf_shaders=16, gpu_gen=14, unified_memory_mb=32768)]
        )
        gpu = info.modules[0]
        assert gpu.name == "Apple M2 Max"
        assert gpu.vram.capacity == 32768
        assert gpu.apple_gpu_info.gpu_core_count == 38

    def test_apple_silicon_missing_extended_info_is_partial(self):
        """apple_gpu=None on an Apple Silicon GPU → PARTIAL."""
        stub = FakeGPUProperties(
            name="Apple M3",
            vendor_id=0x106B,
            device_id=0x0000,
            is_apple_silicon=True,
            apple_gpu=None,  # unexpectedly absent
        )
        info = self._run([stub])

        assert info.status.type == StatusType.PARTIAL
        assert any("extended properties" in m for m in info.status.messages)
        # The module is still appended
        assert len(info.modules) == 1

    def test_no_gpus_returns_empty_success(self):
        """An empty GPU list is valid – success with no modules."""
        info = self._run([])
        assert info.status.type == StatusType.SUCCESS
        assert info.modules == []


# ── Discrete / non-Apple-Silicon GPU ─────────────────────────────────────────


class TestDiscreteGPU:
    """Tests for Intel, AMD, and NVIDIA GPUs on x86 Macs."""

    def _run(self, gpu_list):
        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)
        with _patch_binding(gpu_list):
            return fetch_graphics_info()

    def test_nvidia_gpu_success(self):
        info = self._run(
            [_discrete_gpu(name="NVIDIA GeForce RTX 3090", vendor_id=0x10DE, device_id=0x2204, vram_mb=24576)]
        )
        assert info.status.type == StatusType.SUCCESS
        gpu = info.modules[0]
        assert gpu.name == "NVIDIA GeForce RTX 3090"
        assert gpu.vendor_id == "0x10de"
        assert gpu.device_id == hex(0x2204)
        assert gpu.manufacturer == "Nvidia"
        assert gpu.vram.capacity == 24576
        assert gpu.apple_gpu_info is None

    def test_amd_gpu_success(self):
        info = self._run([_discrete_gpu(name="AMD Radeon Pro 5600M", vendor_id=0x1002, device_id=0x7341)])
        gpu = info.modules[0]
        assert gpu.manufacturer == "AMD"
        assert gpu.vendor_id == "0x1002"
        assert gpu.device_id == hex(0x7341)

    def test_intel_igpu_success(self):
        info = self._run([_discrete_gpu(name="Intel UHD Graphics 630", vendor_id=0x8086, device_id=0x3E9B)])
        gpu = info.modules[0]
        assert gpu.manufacturer == "Intel"
        assert gpu.vendor_id == "0x8086"

    def test_unknown_vendor_labelled_unknown(self):
        info = self._run([_discrete_gpu(name="Mystery GPU", vendor_id=0xDEAD, device_id=0xBEEF)])
        assert info.modules[0].manufacturer == "Unknown"

    def test_discrete_missing_device_id_is_partial(self):
        """device_id == 0 on a non-Apple-Silicon GPU → PARTIAL."""
        stub = FakeGPUProperties(
            name="Intel HD 4000",
            vendor_id=0x8086,
            device_id=0x0000,  # truly missing
            is_apple_silicon=False,
            apple_gpu=None,
        )
        info = self._run([stub])

        assert info.status.type == StatusType.PARTIAL
        assert any("device ID" in m for m in info.status.messages)

    def test_discrete_missing_vendor_id_is_partial(self):
        """vendor_id == 0 → PARTIAL."""
        stub = FakeGPUProperties(
            name="Mystery GPU",
            vendor_id=0x0000,
            device_id=0x1234,
            is_apple_silicon=False,
            apple_gpu=None,
        )
        info = self._run([stub])

        assert info.status.type == StatusType.PARTIAL
        assert any("vendor ID" in m for m in info.status.messages)

    def test_discrete_gpu_vram_populated(self):
        """Discrete GPUs with reported VRAM should have vram set."""
        info = self._run([_discrete_gpu(vram_mb=8192)])
        gpu = info.modules[0]
        assert gpu.vram is not None
        assert gpu.vram.capacity == 8192
        assert gpu.vram.unit == "MB"
        assert gpu.apple_gpu_info is None

    def test_discrete_gpu_missing_vram_is_partial(self):
        """vram_mb == 0 on a non-Apple-Silicon GPU -> PARTIAL."""
        info = self._run([_discrete_gpu(vram_mb=0)])
        gpu = info.modules[0]
        assert info.status.type == StatusType.PARTIAL
        assert any("VRAM" in m for m in info.status.messages)
        assert gpu.vram is None
        assert gpu.apple_gpu_info is None


# ── Multiple GPUs ─────────────────────────────────────────────────────────────


class TestMultipleGPUs:
    """Tests for machines with more than one GPU."""

    def _run(self, gpu_list):
        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)
        with _patch_binding(gpu_list):
            return fetch_graphics_info()

    def test_two_discrete_gpus(self):
        """Dual-GPU Intel Mac Pro style."""
        info = self._run(
            [
                _discrete_gpu("AMD Radeon Pro W6800X", 0x1002, 0x73A3),
                _discrete_gpu("AMD Radeon Pro W6800X Duo", 0x1002, 0x73A5),
            ]
        )
        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 2
        assert info.modules[0].name == "AMD Radeon Pro W6800X"
        assert info.modules[1].name == "AMD Radeon Pro W6800X Duo"

    def test_igpu_plus_dgpu(self):
        """Intel iGPU + discrete NVIDIA dGPU (MacBook Pro 16-inch 2019 style)."""
        igpu = _discrete_gpu("Intel UHD Graphics 630", 0x8086, 0x3E9B)
        dgpu = _discrete_gpu("AMD Radeon Pro 5500M", 0x1002, 0x7340)
        info = self._run([igpu, dgpu])

        assert info.status.type == StatusType.SUCCESS
        assert len(info.modules) == 2
        assert info.modules[0].manufacturer == "Intel"
        assert info.modules[1].manufacturer == "AMD"

    def test_partial_status_propagates_across_gpus(self):
        """One good GPU + one GPU with missing vendor_id → overall PARTIAL."""
        good = _apple_gpu()
        bad = FakeGPUProperties(
            name="Ghost GPU",
            vendor_id=0x0000,
            device_id=0x0000,
            is_apple_silicon=False,
            apple_gpu=None,
        )
        info = self._run([good, bad])

        assert info.status.type == StatusType.PARTIAL
        # Both GPUs are still present
        assert len(info.modules) == 2

    def test_all_modules_appended_even_with_partial_data(self):
        """Every GPU in the list appears in modules regardless of partial status."""
        stubs = [
            _apple_gpu("Apple M3 Pro"),
            _discrete_gpu("AMD Radeon Pro 5600M", 0x1002, 0x7341),
            _discrete_gpu("Intel UHD 630", 0x8086, 0x3E9B),
        ]
        info = self._run(stubs)
        assert len(info.modules) == 3


# ── Edge cases & name handling ────────────────────────────────────────────────


class TestEdgeCases:
    """Misc edge-case and boundary tests."""

    def _run(self, gpu_list):
        import sys

        sys.modules.pop("hwprobe.interops.mac.bindings.gpu_info", None)
        with _patch_binding(gpu_list):
            return fetch_graphics_info()

    def test_empty_name_string_treated_as_missing(self):
        """An empty name string must trigger a partial status."""
        stub = FakeGPUProperties(
            name="",
            vendor_id=0x106B,
            device_id=0x0000,
            is_apple_silicon=True,
            apple_gpu=FakeAppleGPUProperties(20, 8, 15, 18432),
        )
        info = self._run([stub])
        assert info.status.type == StatusType.PARTIAL
        assert any("name" in m.lower() for m in info.status.messages)

    def test_whitespace_only_name_treated_as_missing(self):
        """
        BUG: 'gpu.name if gpu.name else None' keeps whitespace-only strings
        because "   " is truthy. The fix strips before the truthiness check.
        """
        stub = FakeGPUProperties(
            name="   ",
            vendor_id=0x106B,
            device_id=0x0000,
            is_apple_silicon=True,
            apple_gpu=FakeAppleGPUProperties(20, 8, 15, 18432),
        )
        info = self._run([stub])
        assert info.status.type == StatusType.PARTIAL
        assert any("name" in m.lower() for m in info.status.messages)
        assert info.modules[0].name is None

    def test_zero_unified_memory_is_partial(self):
        """
        BUG: unified_memory_mb=0 used to silently produce Megabyte(capacity=0).
        The fix treats 0 as a missing value and raises a partial instead.
        """
        stub = FakeGPUProperties(
            name="Apple M3",
            vendor_id=0x106B,
            device_id=0x0000,
            is_apple_silicon=True,
            apple_gpu=FakeAppleGPUProperties(
                core_count=20,
                gpu_perf_shaders=8,
                gpu_gen=15,
                unified_memory_mb=0,  # bad value from binding
            ),
        )
        info = self._run([stub])
        assert info.status.type == StatusType.PARTIAL
        assert any("0 MB" in m for m in info.status.messages)
        assert info.modules[0].vram is None

    def test_zero_unified_memory_still_populates_extended_info(self):
        """Even when vram=0 (partial), the other Apple Silicon fields are still set."""
        stub = FakeGPUProperties(
            name="Apple M3",
            vendor_id=0x106B,
            device_id=0x0000,
            is_apple_silicon=True,
            apple_gpu=FakeAppleGPUProperties(20, 8, 15, 0),
        )
        info = self._run([stub])
        gpu = info.modules[0]
        assert gpu.apple_gpu_info is not None
        assert gpu.apple_gpu_info.gpu_core_count == 20

    def test_vendor_id_hex_string_is_lowercase(self):
        """hex() in Python always returns lowercase; confirm it is stored that way."""
        info = self._run([_discrete_gpu(vendor_id=0x10DE, device_id=0x2204)])
        assert info.modules[0].vendor_id == "0x10de"

    def test_device_id_hex_string_is_lowercase(self):
        info = self._run([_discrete_gpu(vendor_id=0x1002, device_id=0xABCD)])
        assert info.modules[0].device_id == "0xabcd"

    def test_large_unified_memory(self):
        """192 GB unified memory (Mac Pro style hypothetical)."""
        info = self._run([_apple_gpu(unified_memory_mb=192 * 1024)])
        assert info.modules[0].vram.capacity == 192 * 1024

    def test_return_type_is_graphics_info(self):
        from hwprobe.models.gpu_models import GraphicsInfo

        info = self._run([_apple_gpu()])
        assert isinstance(info, GraphicsInfo)
