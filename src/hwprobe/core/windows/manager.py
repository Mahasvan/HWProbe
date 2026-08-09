from hwprobe.core.windows.audio import fetch_audio_info_fast
from hwprobe.core.windows.baseboard import fetch_baseboard_info
from hwprobe.core.windows.cpu import fetch_cpu_info
from hwprobe.core.windows.display import fetch_display_info_internal
from hwprobe.core.windows.graphics import fetch_graphics_info
from hwprobe.core.windows.memory import fetch_memory_info
from hwprobe.core.windows.network import fetch_network_info_fast
from hwprobe.core.windows.storage import fetch_storage_info
from hwprobe.models.cpu_models import CPUInfo
from hwprobe.models.display_models import DisplayInfo
from hwprobe.models.gpu_models import GraphicsInfo
from hwprobe.models.info_models import HardwareInfo, HardwareManagerInterface, WindowsHardwareInfo
from hwprobe.models.memory_models import MemoryInfo
from hwprobe.models.network_models import NetworkInfo
from hwprobe.models.storage_models import StorageInfo


class WindowsHardwareManager(HardwareManagerInterface):
    """
    Uses Registry and WMI to extract info.
    """

    def __init__(self):
        self.info = WindowsHardwareInfo(
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

    def fetch_network_info(self) -> NetworkInfo:
        self.info.network = fetch_network_info_fast()
        return self.info.network

    def fetch_display_info(self) -> DisplayInfo:
        self.info.display = fetch_display_info_internal()
        return self.info.display

    def fetch_audio_info(self):
        self.info.audio = fetch_audio_info_fast()
        return self.info.audio

    def fetch_baseboard_info(self):
        self.info.baseboard = fetch_baseboard_info()
        return self.info.baseboard

    def fetch_hardware_info(self) -> HardwareInfo:
        self.fetch_cpu_info()
        self.fetch_memory_info()
        self.fetch_storage_info()
        self.fetch_graphics_info()
        self.fetch_network_info()
        self.fetch_display_info()
        self.fetch_audio_info()
        self.fetch_baseboard_info()
        return self.info
