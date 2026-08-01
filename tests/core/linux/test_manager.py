"""Tests for LinuxHardwareManager — verifies delegation and info aggregation.

Only covers supported components: CPU, GPU, Memory, Network, Storage.
"""

import pytest

from hwprobe.core.linux.manager import LinuxHardwareManager
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.gpu_models import GraphicsInfo
from hwprobe.models.info_models import LinuxHardwareInfo
from hwprobe.models.memory_models import MemoryInfo
from hwprobe.models.network_models import NetworkInfo
from hwprobe.models.storage_models import StorageInfo


@pytest.fixture
def mgr():
    return LinuxHardwareManager()


class TestLinuxHardwareManagerInit:
    def test_init_creates_linux_hardware_info(self, mgr):
        assert isinstance(mgr.info, LinuxHardwareInfo)

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


# ── fetch_* methods that delegate AND store on self.info ─────────────────────

# (module_path, method_name, info_attr, fake_return)
_STORING_FETCHES = [
    ("hwprobe.core.linux.manager.fetch_cpu_info", "fetch_cpu_info", "cpu", CPUInfo(name="AMD Ryzen 9 7950X", vendor="AuthenticAMD")),
    ("hwprobe.core.linux.manager.fetch_memory_info", "fetch_memory_info", "memory", MemoryInfo()),
    ("hwprobe.core.linux.manager.fetch_storage_info", "fetch_storage_info", "storage", StorageInfo()),
    ("hwprobe.core.linux.manager.fetch_graphics_info", "fetch_graphics_info", "graphics", GraphicsInfo()),
]


@pytest.mark.parametrize(
    "module_path,method_name,info_attr,fake_return",
    _STORING_FETCHES,
    ids=[f[1] for f in _STORING_FETCHES],
)
def test_fetch_method_delegates_to_module_function(mgr, module_path, method_name, info_attr, fake_return):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(module_path, lambda: fake_return)
        result = getattr(mgr, method_name)()
    assert result is fake_return


@pytest.mark.parametrize(
    "module_path,method_name,info_attr,fake_return",
    _STORING_FETCHES,
    ids=[f[1] for f in _STORING_FETCHES],
)
def test_fetch_method_stores_result_on_info(mgr, module_path, method_name, info_attr, fake_return):
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(module_path, lambda: fake_return)
        getattr(mgr, method_name)()
    assert getattr(mgr.info, info_attr) is fake_return


# ── fetch_network_info — delegates but does NOT store on self.info ───────────


def test_fetch_network_info_delegates_to_module_function(mgr):
    fake_net = NetworkInfo()
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("hwprobe.core.linux.manager.fetch_network_info", lambda: fake_net)
        result = mgr.fetch_network_info()
    assert result is fake_net


# ── fetch_hardware_info — aggregates all sub-fetches ─────────────────────────


@pytest.fixture
def mgr_with_all_mocked(mgr):
    """Manager with all fetch_* module functions patched."""
    mp = pytest.MonkeyPatch()
    mp.setattr("hwprobe.core.linux.manager.fetch_cpu_info", lambda: CPUInfo(name="AMD Ryzen 9 7950X", vendor="AuthenticAMD"))
    mp.setattr("hwprobe.core.linux.manager.fetch_graphics_info", lambda: GraphicsInfo())
    mp.setattr("hwprobe.core.linux.manager.fetch_memory_info", lambda: MemoryInfo())
    mp.setattr("hwprobe.core.linux.manager.fetch_storage_info", lambda: StorageInfo())
    mp.setattr("hwprobe.core.linux.manager.fetch_network_info", lambda: NetworkInfo())
    yield mgr
    mp.undo()


def test_fetch_hardware_info_returns_self_info(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert result is mgr_with_all_mocked.info


def test_fetch_hardware_info_returns_linux_hardware_info(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert isinstance(result, LinuxHardwareInfo)


def test_fetch_hardware_info_populates_cpu(mgr_with_all_mocked):
    result = mgr_with_all_mocked.fetch_hardware_info()
    assert result.cpu.name == "AMD Ryzen 9 7950X"
    assert result.cpu.vendor == "AuthenticAMD"
