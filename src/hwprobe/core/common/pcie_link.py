from typing import Optional

from hwprobe.models.gpu_models import PCIeLinkInfo, PCIeLinkValue


def build_pcie_link(
    *,
    max_gen: int,
    current_gen: int,
    max_width: int,
    current_width: int
) -> Optional[PCIeLinkInfo]:
    gen = None
    width = None
    
    if max_gen > 0 and current_gen > 0:
        gen = PCIeLinkValue(max=max_gen, current=current_gen)
        
    if max_width > 0 and current_width > 0:
        width = PCIeLinkValue(max=max_width, current=current_width)
        
    if gen is None and width is None:
        return None
    
    return PCIeLinkInfo(gen=gen, width=width)