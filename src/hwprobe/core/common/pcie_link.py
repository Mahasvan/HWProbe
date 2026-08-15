from typing import Optional

from hwprobe.models.gpu_models import PCIeLinkInfo, PCIeLinkValue


def build_pcie_link(
    *,
    max_gen: int,
    current_gen: int,
    max_width: int,
    current_width: int
) -> Optional[PCIeLinkInfo]:
    gen = PCIeLinkValue()
    width = PCIeLinkValue()
    
    if max_gen:
        gen.max = max_gen
        
    if current_gen:
        gen.current = current_gen
        
    if max_width:
        width.max = max_width
        
    if current_width:
        width.current = current_width
        
    if max_gen == 0 and current_gen == 0 and max_width == 0 and current_width == 0:
        return None
    
    return PCIeLinkInfo(gen=gen, width=width)