from typing import Optional

from pydantic import Field

from hwprobe.models.component_model import ComponentInfo


class CPUInfo(ComponentInfo):
    #: This is the CPU's name
    name: Optional[str] = None

    #: x86, ARM, etc.
    architecture: Optional[str] = None

    #: Denotes whether the CPU is 32 or 64 bit.
    #: Independent of whether the OS is 32 or 64 bit.
    bitness: Optional[int] = None

    #: ARM Version. Will be ``null`` on x86 CPUs.
    arch_version: Optional[str] = None

    #: Manufacturer of the CPU. ``Intel``, for example.
    vendor: Optional[str] = None

    #: SSE flags supported by the CPU.
    sse_flags: list[str] = Field(default_factory=list)

    #: The number of physical cores present on the CPU
    cores: Optional[int] = None
    #: The number of logical threads supported by the CPU
    threads: Optional[int] = None
