import os
import platform

__version__ = "0.0.1b2"
__author__ = "Mahasvan"
__license__ = "BSD-3-Clause"



def _detect_platform() -> str:
    """Allow overriding platform selection for tests via env.

    Set HWPROBE_PLATFORM to one of linux|darwin|windows to force a backend.
    Defaults to the host platform.
    """
    override = os.environ.get("HWPROBE_PLATFORM", "").lower()
    if override in {"linux", "darwin", "windows", "win32", "nt"}:
        return override
    return platform.system().lower()


_platform = _detect_platform()

if _platform in {"windows", "win32", "nt"}:
    from hwprobe.core.windows import WindowsHardwareManager as HardwareManager

    if hasattr(os, "add_dll_directory"):
        dll_path = os.path.join(os.path.dirname(__file__), "interops", "win", "bindings")
        os.add_dll_directory(dll_path)
elif _platform == "darwin":
    from hwprobe.core.mac import MacHardwareManager as HardwareManager
else:
    # Default to Linux for unknown/override cases (including tests on macOS)
    from hwprobe.core.linux import LinuxHardwareManager as HardwareManager

__all__ = ["HardwareManager"]
