#include "../include/gpu_info.h"

#include <stdio.h>
#include <stdalign.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <xf86drm.h>
#include <drm/amdgpu_drm.h>
#include <drm/i915_drm.h>
#include <drm/nouveau_drm.h>

//
// Vulkan types — dlopen'd at runtime, no SDK headers required
//

typedef void *VkInstance;
typedef void *VkPhysicalDevice;

enum
{
    VK_STYPE_APP_INFO = 0,
    VK_STYPE_INST_CREATE = 1,
    VK_STYPE_PROPS2 = 1000059001,
    VK_STYPE_PCI_BUS_EXT = 1000212000,
    VK_STYPE_MEM_PROPS2 = 1000059006,
    VK_STYPE_MEM_BUDGET_EXT = 1000237000,
    VK_HEAP_DEVICE_LOCAL = 0x1,
};

struct VkAppInfo
{
    uint32_t sType;
    const void *pNext;
    const char *appName;
    uint32_t appVer;
    const char *engName;
    uint32_t engVer;
    uint32_t apiVer;
};

struct VkInstCreateInfo
{
    uint32_t sType;
    const void *pNext;
    uint32_t flags;
    const VkAppInfo *pAppInfo;
    uint32_t layerCnt;
    const char *const *layers;
    uint32_t extCnt;
    const char *const *exts;
};

struct VkPhysDevProps
{
    uint32_t api, driver, vendorID, deviceID, devType;
    char name[256];
    uint8_t uuid[16];
    alignas(uint64_t) uint8_t _limits[504];
    uint8_t _sparse[20];
};

struct VkPhysDevProps2
{
    uint32_t sType;
    void *pNext;
    VkPhysDevProps props;
};

struct VkPCIBusInfo
{
    uint32_t sType;
    void *pNext;
    uint32_t dom, bus, dev, func;
};

struct VkMemHeap
{
    uint64_t size;
    uint32_t flags;
};
struct VkMemType
{
    uint32_t flags;
    uint32_t heapIdx;
};

struct VkMemProps
{
    uint32_t typeCnt;
    VkMemType types[32];
    uint32_t heapCnt;
    VkMemHeap heaps[16];
};

struct VkMemProps2
{
    uint32_t sType;
    void *pNext;
    VkMemProps memProps;
};

struct VkMemBudget
{
    uint32_t sType;
    void *pNext;
    uint64_t budget[16];
    uint64_t usage[16];
};

struct VkGPU
{
    char name[256];
    char slot[32];
    uint64_t vram_mb;
    uint64_t used_mb;
    uint32_t vendor_id;
    uint32_t device_id;
};

typedef int32_t (*PFN_CreateInst)(const VkInstCreateInfo *, const void *, VkInstance *);
typedef void (*PFN_DestroyInst)(VkInstance, const void *);
typedef int32_t (*PFN_EnumDevs)(VkInstance, uint32_t *, VkPhysicalDevice *);
typedef void (*PFN_GetProps2)(VkPhysicalDevice, VkPhysDevProps2 *);
typedef void (*PFN_GetMem2)(VkPhysicalDevice, VkMemProps2 *);

enum
{
    MAX_GPU_CARDS = 16,
    BYTES_PER_MB = 1024 * 1024,
};

static uint64_t to_mb(uint64_t bytes)
{
    return bytes / BYTES_PER_MB;
}

static PCIAddress parse_bdf_to_pci_addr(const char *bdf)
{
    PCIAddress pciAddr = {0};
    if (!bdf)
        return pciAddr;

    sscanf(bdf, "%hx:%hhx:%hhx.%hhd", &pciAddr.domain, &pciAddr.bus, &pciAddr.device, &pciAddr.function);
    return pciAddr;
}

//
// DRM ioctl VRAM queries
//

static void vram_amdgpu(int fd, GPUProperties *g)
{
    drm_amdgpu_info req = {0};
    drm_amdgpu_info_vram_gtt vram = {0};

    req.return_pointer = reinterpret_cast<uint64_t>(&vram);
    req.return_size = sizeof(vram);
    req.query = AMDGPU_INFO_VRAM_GTT;

    if (ioctl(fd, DRM_IOCTL_AMDGPU_INFO, &req) == 0)
        g->vram_total_mb = to_mb(vram.vram_size);

    drm_amdgpu_info ureq = {0};
    struct
    {
        uint64_t vram, vis, gtt;
    } usage = {0};

    ureq.return_pointer = reinterpret_cast<uint64_t>(&usage);
    ureq.return_size = sizeof(usage);
    ureq.query = AMDGPU_INFO_VRAM_USAGE;

    if (ioctl(fd, DRM_IOCTL_AMDGPU_INFO, &ureq) == 0)
        g->vram_used_mb = to_mb(usage.vram);
}

static void vram_i915(int fd, GPUProperties *g)
{
    drm_i915_query_item item = {0};
    item.query_id = DRM_I915_QUERY_MEMORY_REGIONS;

    drm_i915_query q = {0};
    q.num_items = 1;
    q.items_ptr = reinterpret_cast<uint64_t>(&item);

    if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) != 0 || item.length <= 0)
        return;

    uint8_t *buf = static_cast<uint8_t *>(calloc(1, item.length));
    if (!buf)
        return;

    item.data_ptr = reinterpret_cast<uint64_t>(buf);

    if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) == 0)
    {
        drm_i915_query_memory_regions *r = reinterpret_cast<drm_i915_query_memory_regions *>(buf);
        for (uint32_t i = 0; i < r->num_regions; i++)
        {
            if (r->regions[i].region.memory_class == I915_MEMORY_CLASS_DEVICE)
            {
                g->vram_total_mb = to_mb(r->regions[i].probed_size);
                break;
            }
        }
    }

    free(buf);
}

static void vram_nouveau(int fd, GPUProperties *g)
{
    drm_nouveau_getparam p = {0};
    p.param = NOUVEAU_GETPARAM_FB_SIZE;

    if (ioctl(fd, DRM_IOCTL_NOUVEAU_GETPARAM, &p) == 0 && p.value > 0)
        g->vram_total_mb = to_mb(p.value);
}

static int vulkan_query(VkGPU *out, const PCIAddress *pciAddr)
{
    if (pciAddr == NULL)
        return -1;

    void *lib = dlopen("libvulkan.so.1", RTLD_LAZY);
    if (!lib)
        return -1;

    // Load the Vulkan entry points we need.
    // If any are missing, the ICD is too old to support the features we need.
    PFN_CreateInst createInstance = reinterpret_cast<PFN_CreateInst>(dlsym(lib, "vkCreateInstance"));
    PFN_DestroyInst destroyInstance = reinterpret_cast<PFN_DestroyInst>(dlsym(lib, "vkDestroyInstance"));
    PFN_EnumDevs enumPhysDev = reinterpret_cast<PFN_EnumDevs>(dlsym(lib, "vkEnumeratePhysicalDevices"));
    PFN_GetProps2 getPhysDevProps = reinterpret_cast<PFN_GetProps2>(dlsym(lib, "vkGetPhysicalDeviceProperties2"));
    PFN_GetMem2 getPhysDevMemProps = reinterpret_cast<PFN_GetMem2>(dlsym(lib, "vkGetPhysicalDeviceMemoryProperties2"));

    if (!createInstance || !destroyInstance || !enumPhysDev || !getPhysDevProps || !getPhysDevMemProps)
    {
        dlclose(lib);
        return -1;
    }

    VkAppInfo vkAppInfo = {VK_STYPE_APP_INFO, NULL, "HWProbe", 1, NULL, 0, (1u << 22) | (1u << 12)};
    VkInstCreateInfo vkInstCreate = {VK_STYPE_INST_CREATE, NULL, 0, &vkAppInfo, 0, NULL, 0, NULL};

    VkInstance inst = NULL;
    if (createInstance(&vkInstCreate, NULL, &inst) != 0 || !inst)
    {
        dlclose(lib);
        return -1;
    }

    // Unfortunately, Vulkan doesn't provide a way to directly correlate
    // a PCI BDF to a VkPhysicalDevice. We have to enumerate all devices and
    // check their PCI bus info until we find a match (or exhaust the device list).
    //
    // The only "useful" identifiers Vulkan provides are internal [L|U]UID representations,
    // which doesn't help us with our situation: they are used to identify devices across
    // multiple Graphics API stacks.
    //
    // What we can do is return early if a VkPhysicalDevice matches the PCI BDF we are looking for.
    //
    // Sources:
    //  - https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html
    //  - https://docs.vulkan.org/refpages/latest/refpages/source/vkGetWinrtDisplayNV.html
    uint32_t numberOfDevices = 0;
    if (enumPhysDev(inst, &numberOfDevices, NULL) != 0)
    {
        destroyInstance(inst, NULL);
        dlclose(lib);
        return -1;
    }

    if (numberOfDevices == 0)
    {
        destroyInstance(inst, NULL);
        dlclose(lib);
        return 0;
    }

    if (numberOfDevices > MAX_GPU_CARDS)
        numberOfDevices = MAX_GPU_CARDS;

    VkPhysicalDevice devs[MAX_GPU_CARDS];
    if (enumPhysDev(inst, &numberOfDevices, devs) != 0)
    {
        destroyInstance(inst, NULL);
        dlclose(lib);
        return -1;
    }

    int cnt = 0;

    for (uint32_t i = 0; i < numberOfDevices && cnt < MAX_GPU_CARDS; i++)
    {
        VkPCIBusInfo pci = {VK_STYPE_PCI_BUS_EXT, NULL, 0, 0, 0, 0};
        VkPhysDevProps2 p = {0};
        p.sType = VK_STYPE_PROPS2;
        p.pNext = &pci;
        getPhysDevProps(devs[i], &p);

        VkMemBudget bgt = {0};
        bgt.sType = VK_STYPE_MEM_BUDGET_EXT;
        bgt.pNext = NULL;

        VkMemProps2 m = {0};
        m.sType = VK_STYPE_MEM_PROPS2;
        m.pNext = &bgt;
        getPhysDevMemProps(devs[i], &m);

        uint64_t total = 0, used = 0;
        for (uint32_t h = 0; h < m.memProps.heapCnt; h++)
        {
            if (m.memProps.heaps[h].flags & VK_HEAP_DEVICE_LOCAL)
            {
                total += m.memProps.heaps[h].size;
                // total - budget ≈ system-wide VRAM usage
                if (bgt.budget[h] > 0 && bgt.budget[h] < m.memProps.heaps[h].size)
                    used += m.memProps.heaps[h].size - bgt.budget[h];
            }
        }

        VkGPU *g = &out[cnt++];

        g->vendor_id = p.props.vendorID;
        g->device_id = p.props.deviceID;
        g->vram_mb = to_mb(total);
        g->used_mb = to_mb(used);

        snprintf(g->slot, sizeof(g->slot), "%04x:%02x:%02x.%x", pci.dom, pci.bus, pci.dev, pci.func);
        snprintf(g->name, sizeof(g->name), "%s", p.props.name);

        if (
            pciAddr->domain == pci.dom &&
            pciAddr->bus == pci.bus &&
            pciAddr->device == pci.dev &&
            pciAddr->function == pci.func)
        {
            // Found the device we were looking for; stop enumerating.
            break;
        }
    }

    destroyInstance(inst, NULL);
    dlclose(lib);
    return cnt;
}

/**
 * Get GPU information for a specific PCI device.
 *
 * @note    This function also returns the current VRAM usage, even though it currently
 *          has no proper application in HWProbe. It shall stay here for future reference
 *          if we decide to query similar information on other platforms.
 *
 * @param bdf The PCI bus:device.function string (e.g., "0000:01:00.0").
 * @param vendor_id The PCI vendor ID of the GPU (e.g., 0x1002 for AMD, 0x8086 for Intel, 0x10DE for NVIDIA).
 * @param out Pointer to a GPUProperties struct to receive the GPU information.
 * @return 0 on success, -1 on failure.
 */
int get_gpu_info(const char *bdf, uint32_t vendor_id, GPUProperties *out)
{
    if (!bdf || !out)
        return -1;

    // Find the DRM card node under /sys/bus/pci/devices/<bdf>/drm/cardN.
    char drm_dir_path[160];
    snprintf(drm_dir_path, sizeof(drm_dir_path), "/sys/bus/pci/devices/%s/drm", bdf);

    char card_name[256] = {0};
    DIR *drm_dir = opendir(drm_dir_path);

    if (drm_dir)
    {
        struct dirent *entry;

        while ((entry = readdir(drm_dir)) != NULL)
        {
            if (strncmp(entry->d_name, "card", 4) == 0 &&
                entry->d_name[4] >= '0' && entry->d_name[4] <= '9')
            {
                snprintf(card_name, sizeof(card_name), "%s", entry->d_name);
                break;
            }
        }
        closedir(drm_dir);
    }

    GPUProperties g = {};

    if (card_name[0])
    {
        char devpath[64];

        snprintf(devpath, sizeof(devpath), "/dev/dri/%s", card_name);

        int fd = open(devpath, O_RDWR | O_CLOEXEC);
        if (fd < 0)
            fd = open(devpath, O_RDONLY | O_CLOEXEC);

        if (fd >= 0)
        {
            // TODO:    Figure out if there is a vendor-agnostic way to query VRAM usage
            //          without having to fall back to Vulkan.
            //
            //          For now, we use vendor-specific ioctls.
            switch (vendor_id)
            {
            case AMD_VENDOR_ID:
                vram_amdgpu(fd, &g);
                break;
            case INTEL_VENDOR_ID:
                vram_i915(fd, &g);
                break;
            case NVIDIA_VENDOR_ID:
                vram_nouveau(fd, &g);
                break;
            }

            close(fd);
        }
    }

    // Vulkan fallback if DRM didn't give us complete info.
    if (!g.vram_total_mb || !g.name[0])
    {
        PCIAddress pciAddr = parse_bdf_to_pci_addr(bdf);
        VkGPU vk[MAX_GPU_CARDS];
        int vk_n = vulkan_query(vk, &pciAddr);

        if (vk_n > 0)
        {
            for (int v = 0; v < vk_n; v++)
            {
                if (strcmp(bdf, vk[v].slot) != 0)
                    continue;

                if (!g.vram_total_mb)
                    g.vram_total_mb = vk[v].vram_mb;
                if (!g.vram_used_mb)
                    g.vram_used_mb = vk[v].used_mb;
                if (vk[v].name[0])
                    snprintf(g.name, sizeof(g.name), "%s", vk[v].name);

                break;
            }
        }
    }

    *out = g;
    return 0;
}
