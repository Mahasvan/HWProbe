#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "gpu_info.h"

int main(int argc, char *argv[]) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <bdf> <vendor_id>\n  e.g. %s 0000:01:00.0 0x1002\n",
                argv[0], argv[0]);
        return 1;
    }

    uint32_t vendor_id = (uint32_t)strtoul(argv[2], NULL, 16);
    GPUProperties g;
    if (get_gpu_info(argv[1], vendor_id, &g) < 0) {
        fprintf(stderr, "Failed to query GPU info for %s\n", argv[1]);
        return 1;
    }

    printf("GPU at %s:\n", argv[1]);
    printf("  Name:        %s\n", g.name[0] ? g.name : "(unknown)");
    printf("  VRAM Total:  %lu MB\n", (unsigned long)g.vram_total_mb);
    printf("  VRAM Used:   %lu MB\n", (unsigned long)g.vram_used_mb);
    return 0;
}
