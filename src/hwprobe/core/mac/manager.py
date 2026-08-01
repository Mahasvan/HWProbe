from hwprobe.core.mac.cpu import fetch_cpu_info
from hwprobe.core.mac.display import fetch_display_info
from hwprobe.core.mac.graphics import fetch_graphics_info
from hwprobe.core.mac.memory import fetch_memory_info
from hwprobe.core.mac.network import fetch_network_info
from hwprobe.core.mac.storage import fetch_storage_info
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.gpu_models import GraphicsInfo
from hwprobe.models.info_models import HardwareInfo, HardwareManagerInterface, MacHardwareInfo
from hwprobe.models.memory_models import MemoryInfo
from hwprobe.models.network_models import NetworkInfo
from hwprobe.models.storage_models import StorageInfo


class MacHardwareManager(HardwareManagerInterface):
    """
    Uses `sysctl` and IOreg to extract info.
    """

    def __init__(self):
        self.info = MacHardwareInfo(
            cpu=CPUInfo(),
            graphics=GraphicsInfo(),
            memory=MemoryInfo(),
            storage=StorageInfo(),
            network=NetworkInfo(),
        )

    def fetch_cpu_info(self) -> CPUInfo:
        self.info.cpu = fetch_cpu_info()
        return self.info.cpu

    def fetch_memory_info(self) -> MemoryInfo:
        self.info.memory = fetch_memory_info()
        return self.info.memory

    def fetch_storage_info(self) -> StorageInfo:
        self.info.storage = fetch_storage_info()
        return self.info.storage

    def fetch_graphics_info(self) -> GraphicsInfo:
        self.info.graphics = fetch_graphics_info()
        return self.info.graphics

    def fetch_display_info(self):
        self.info.display = fetch_display_info()
        return self.info.display

    def fetch_network_info(self) -> NetworkInfo:
        self.info.network = fetch_network_info()
        return self.info.network

    def fetch_hardware_info(self) -> HardwareInfo:
        self.fetch_cpu_info()
        self.fetch_graphics_info()
        self.fetch_memory_info()
        self.fetch_storage_info()
        self.fetch_network_info()
        return self.info
