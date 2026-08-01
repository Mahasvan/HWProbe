"""Tests for MacHardwareManager — verifies delegation and info aggregation.

Only covers supported components: CPU, GPU, Memory, Network, Storage.
"""

import pytest

from hwprobe.core.mac.manager import MacHardwareManager
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.gpu_models import GraphicsInfo
from hwprobe.models.info_models import MacHardwareInfo
from hwprobe.models.memory_models import MemoryInfo
from hwprobe.models.network_models import NetworkInfo
from hwprobe.models.storage_models import StorageInfo


@pytest.fixture
def mgr():
    return MacHardwareManager()


class TestMacHardwareManagerInit:
    def test_init_creates_mac_hardware_info(self, mgr):
        assert isinstance(mgr.info, MacHardwareInfo)

    @pytest.mark.parametrize(
        "attr,expected_type",
        [
            ("cpu", CPUInfo),
            ("graphics", GraphicsInfo),
            ("memory", MemoryInfo),
            ("storage", StorageInfo),
            ("network", NetworkInfo),
        ],
    )
    def test_init_populates_component(self, mgr, attr, expected_type):
        assert isinstance(getattr(mgr.info, attr), expected_type)

    @pytest.mark.parametrize(
        "attr",
        ["graphics", "memory", "storage", "network"],
    )
    def test_init_components_have_empty_modules(self, mgr, attr):
        assert getattr(mgr.info, attr).modules == []

    def test_init_cpu_has_no_name(self, mgr):
        assert mgr.info.cpu.name is None


# ── Individual fetch_* methods that delegate and store on self.info ──────────

# (module_path, method_name, info_attr, fake_return)
_DELEGATING_FETCHES = [
    ("hwprobe.core.mac.manager.fetch_cpu_info", "fetch_cpu_info", "cpu", CPUInfo(name="Apple M3")),
    ("hwprobe.core.mac.manager.fetch_memory_info", "fetch_memory_info", "memory", MemoryInfo()),
    ("hwprobe.core.mac.manager.fetch_storage_info", "fetch_storage_info", "storage", StorageInfo()),
    ("hwprobe.core.mac.manager.fetch_graphics_info", "fetch_graphics_info", "graphics", GraphicsInfo()),
    ("hwprobe.core.mac.manager.fetch_network_info", "fetch_network_info", "network", NetworkInfo()),
]


@pytest.mark.parametrize(
    "module_path,method_name,info_attr,fake_return",
    _DELEGATING_FETCHES,
    ids=[f[1] for f in _DELEGATING_FETCHES],
)
def test_fetch_method_delegates_to_module_function(mgr, module_path, method_name, info_attr, fake_return):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(module_path, lambda: fake_return)
        result = getattr(mgr, method_name)()
    assert result is fake_return


@pytest.mark.parametrize(
    "module_path,method_name,info_attr,fake_return",
    _DELEGATING_FETCHES,
    ids=[f[1] for f in _DELEGATING_FETCHES],
)
def test_fetch_method_stores_result_on_info(mgr, module_path, method_name, info_attr, fake_return):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(module_path, lambda: fake_return)
        getattr(mgr, method_name)()
    assert getattr(mgr.info, info_attr) is fake_return


# ── fetch_hardware_info — aggregates all sub-fetches ─────────────────────────


@pytest.fixture
def mgr_with_all_mocked(mgr):
    """Manager with all fetch_* module functions patched."""
    mp = pytest.MonkeyPatch()
    mp.setattr("hwprobe.core.mac.manager.fetch_cpu_info", lambda: CPUInfo(name="Apple M3", vendor="Apple"))
    mp.setattr("hwprobe.core.mac.manager.fetch_graphics_info", lambda: GraphicsInfo())
    mp.setattr("hwprobe.core.mac.manager.fetch_memory_info", lambda: MemoryInfo())
    mp.setattr("hwprobe.core.mac.manager.fetch_storage_info", lambda: StorageInfo())
    mp.setattr("hwprobe.core.mac.manager.fetch_network_info", lambda: NetworkInfo())
    yield mgr
    mp.undo()


def test_fetch_hardware_info_returns_self_info(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert result is mgr_with_all_mocked.info


def test_fetch_hardware_info_returns_mac_hardware_info(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert isinstance(result, MacHardwareInfo)


def test_fetch_hardware_info_populates_cpu(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert result.cpu.name == "Apple M3"
    assert result.cpu.vendor == "Apple"
