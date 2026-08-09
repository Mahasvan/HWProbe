#include <stdio.h>
#include "gpu_info.h"

int main(void) {
    GPUProperties gpus[8];
    int count = get_gpu_info(gpus, 8);

    if (count < 0) { fprintf(stderr, "Failed to query GPU info\n"); return 1; }
    printf("Found %d GPU(s):\n\n", count);

    for (int i = 0; i < count; i++) {
        GPUProperties *g = &gpus[i];
        printf("GPU %d:\n", i);
        printf("  Name:        %s\n", g->name[0] ? g->name : "(unknown)");
        printf("  Vendor ID:   0x%04X\n", g->vendor_id);
        printf("  Device ID:   0x%04X\n", g->device_id);
        printf("  PCI Slot:    %s\n", g->pci_slot);
        printf("  Driver:      %s\n", g->driver[0] ? g->driver : "N/A");
        printf("  VRAM Total:  %lu MB\n", (unsigned long)g->vram_total_mb);
        printf("  VRAM Used:   %lu MB\n", (unsigned long)g->vram_used_mb);
        printf("  PCIe Gen:    %d\n", g->pcie_gen);
        printf("  PCIe Width:  x%d\n", g->pcie_width);
        printf("\n");
    }
    return 0;
}
