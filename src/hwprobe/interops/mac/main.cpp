#include <iostream>
#include <iomanip>
#include "include/gpu_info.h"
#include "include/storage_info.h"

int main() {
    // ── GPU info ────────────────────────────────────────────────────────────
    GPUProperties gpus[16];
    const int gpuCount = get_gpu_info(gpus, 16);

    if (gpuCount < 0) {
        std::cerr << "Failed to retrieve GPU info.\n";
    } else {
        std::cout << "Found " << gpuCount << " GPU(s):\n\n";

        for (int i = 0; i < gpuCount; ++i) {
            const GPUProperties &g = gpus[i];
            std::cout << "GPU " << i << ":\n";
            std::cout << "  Name:         " << g.name << "\n";
            std::cout << std::hex << std::setfill('0');
            std::cout << "  Vendor ID:    0x" << std::setw(4) << g.vendor_id << "\n";
            std::cout << "  Device ID:    0x" << std::setw(4) << g.device_id << "\n";
            std::cout << std::dec << std::setfill(' ');
            if (g.is_apple_silicon) {
                std::cout << "  Apple Silicon GPU:\n";
                std::cout << "    GPU Cores:     " << g.apple_gpu.core_count << "\n";
                std::cout << "    Perf Shaders:  " << g.apple_gpu.gpu_perf_shaders << "\n";
                std::cout << "    GPU Gen:       " << g.apple_gpu.gpu_gen << "\n";
                std::cout << "    Unified Mem:   " << g.apple_gpu.unified_memory_mb << " MB\n";
            }
            if (g.acpi_path[0] != '\0')
                std::cout << "  ACPI Path:    " << g.acpi_path << "\n";
            if (g.pci_path[0] != '\0')
                std::cout << "  PCI Path:     " << g.pci_path << "\n";
            if (g.vram_mb > 0)
                std::cout << "  VRAM:         " << g.vram_mb << " MB\n";

            std::cout << "  PCIe Gen M:   " << g.capable_pcie_gen << "\n";
            std::cout << "  PCIe Width M: " << g.capable_pcie_width << "\n";
            std::cout << "  PCIe Gen S:   " << g.negotiated_pcie_gen << "\n";
            std::cout << "  PCIe Width S: " << g.negotiated_pcie_width << "\n";
            std::cout << "\n";
        }
    }

    // ── Storage info ────────────────────────────────────────────────────────
    StorageDeviceProperties disks[32];
    const int diskCount = get_storage_info(disks, 32);

    if (diskCount < 0) {
        std::cerr << "Failed to retrieve storage info.\n";
    } else {
        std::cout << "Found " << diskCount << " storage device(s):\n\n";

        for (int i = 0; i < diskCount; ++i) {
            const StorageDeviceProperties &d = disks[i];
            std::cout << "Disk " << i << ":\n";
            if (d.product_name[0] != '\0')
                std::cout << "  Product:      " << d.product_name << "\n";
            if (d.vendor_name[0] != '\0')
                std::cout << "  Vendor:       " << d.vendor_name << "\n";
            if (d.medium_type[0] != '\0')
                std::cout << "  Medium Type:  " << d.medium_type << "\n";
            if (d.interconnect[0] != '\0')
                std::cout << "  Interconnect: " << d.interconnect << "\n";
            if (d.location[0] != '\0')
                std::cout << "  Location:     " << d.location << "\n";
            if (d.size_bytes > 0)
                std::cout << "  Size:         " << d.size_bytes / (1024 * 1024) << " MB\n";
            std::cout << "\n";
        }
    }

    return (gpuCount < 0 && diskCount < 0) ? 1 : 0;
}
