#include "../include/gpu_info.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <stdio.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <xf86drm.h>
#include <drm/amdgpu_drm.h>
#include <drm/i915_drm.h>
#include <drm/nouveau_drm.h>

// ============================================================================
// Vulkan types — dlopen'd at runtime, no SDK headers required
// ============================================================================

typedef void *VkInstance;
typedef void *VkPhysicalDevice;

enum {
    VK_STYPE_APP_INFO       = 0,
    VK_STYPE_INST_CREATE    = 1,
    VK_STYPE_PROPS2         = 1000059001,
    VK_STYPE_PCI_BUS_EXT    = 1000212000,
    VK_STYPE_MEM_PROPS2     = 1000059006,
    VK_STYPE_MEM_BUDGET_EXT = 1000237000,
    VK_HEAP_DEVICE_LOCAL    = 0x1,
};

struct VkAppInfo {
    uint32_t sType; const void *pNext;
    const char *appName; uint32_t appVer;
    const char *engName; uint32_t engVer;
    uint32_t apiVer;
};

struct VkInstCreateInfo {
    uint32_t sType; const void *pNext; uint32_t flags;
    const VkAppInfo *pAppInfo;
    uint32_t layerCnt; const char *const *layers;
    uint32_t extCnt; const char *const *exts;
};

struct VkPhysDevProps {
    uint32_t api, driver, vendorID, deviceID, devType;
    char name[256];
    uint8_t uuid[16];
    uint8_t _limits[504];
    uint8_t _sparse[20];
};

struct VkPhysDevProps2 {
    uint32_t sType; void *pNext;
    VkPhysDevProps props;
};

struct VkPCIBusInfo {
    uint32_t sType; void *pNext;
    uint32_t dom, bus, dev, func;
};

struct VkMemHeap  { uint64_t size; uint32_t flags; };
struct VkMemType  { uint32_t flags; uint32_t heapIdx; };

struct VkMemProps {
    uint32_t typeCnt; VkMemType types[32];
    uint32_t heapCnt; VkMemHeap heaps[16];
};

struct VkMemProps2 {
    uint32_t sType; void *pNext;
    VkMemProps memProps;
};

struct VkMemBudget {
    uint32_t sType; void *pNext;
    uint64_t budget[16];
    uint64_t usage[16];
};

typedef int32_t (*PFN_CreateInst)(const VkInstCreateInfo *, const void *, VkInstance *);
typedef void (*PFN_DestroyInst)(VkInstance, const void *);
typedef int32_t (*PFN_EnumDevs)(VkInstance, uint32_t *, VkPhysicalDevice *);
typedef void (*PFN_GetProps2)(VkPhysicalDevice, VkPhysDevProps2 *);
typedef void (*PFN_GetMem2)(VkPhysicalDevice, VkMemProps2 *);

enum {
    MAX_GPU_CARDS = 16,
    BYTES_PER_MB = 1024 * 1024,
};

static uint64_t to_mb(uint64_t bytes) {
    return bytes / BYTES_PER_MB;
}

// ============================================================================
// Sysfs helpers
//
// The device attribute files (vendor/device/class/driver/...) all live in
// the same sysfs directory. Opening that directory once and reading each
// attribute via *at() syscalls avoids re-walking the full kernfs path
// (/sys/class/drm/cardN/device/...) for every single attribute.
// ============================================================================

static uint32_t read_hex_at(int dirfd, const char *name) {
    int fd = openat(dirfd, name, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;

    char buf[32];
    ssize_t n = read(fd, buf, sizeof(buf) - 1);
    close(fd);

    if (n <= 0) return 0;
    buf[n] = '\0';
    return static_cast<uint32_t>(strtoul(buf, NULL, 16));
}

static int read_str_at(int dirfd, const char *name, char *buf, int sz) {
    if (!buf || sz <= 1) return -1;

    int fd = openat(dirfd, name, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;

    ssize_t n = read(fd, buf, sz - 1);
    close(fd);

    if (n <= 0) { buf[0] = '\0'; return -1; }
    buf[n] = '\0';

    while (n > 0 && buf[n - 1] == '\n') buf[--n] = '\0';
    return 0;
}

static void read_symlink_basename(const char *link, char *out, int sz) {
    char target[512];
    ssize_t n = readlink(link, target, sizeof(target) - 1);

    if (n <= 0) { out[0] = '\0'; return; }
    target[n] = '\0';

    const char *s = strrchr(target, '/');
    snprintf(out, sz, "%s", s ? s + 1 : target);
}

static void read_symlink_basename_at(int dirfd, const char *name, char *out, int sz) {
    char target[512];
    ssize_t n = readlinkat(dirfd, name, target, sizeof(target) - 1);

    if (n <= 0) { out[0] = '\0'; return; }
    target[n] = '\0';

    const char *s = strrchr(target, '/');
    snprintf(out, sz, "%s", s ? s + 1 : target);
}

// ============================================================================
// DRM ioctl VRAM queries
// ============================================================================

static void vram_amdgpu(int fd, GPUProperties *g) {
    drm_amdgpu_info req = {0};
    drm_amdgpu_info_vram_gtt vram = {0};

    req.return_pointer = reinterpret_cast<uint64_t>(&vram);
    req.return_size = sizeof(vram);
    req.query = AMDGPU_INFO_VRAM_GTT;

    if (ioctl(fd, DRM_IOCTL_AMDGPU_INFO, &req) == 0)
        g->vram_total_mb = to_mb(vram.vram_size);

    drm_amdgpu_info ureq = {0};
    struct { uint64_t vram, vis, gtt; } usage = {0};

    ureq.return_pointer = reinterpret_cast<uint64_t>(&usage);
    ureq.return_size = sizeof(usage);
    ureq.query = AMDGPU_INFO_VRAM_USAGE;

    if (ioctl(fd, DRM_IOCTL_AMDGPU_INFO, &ureq) == 0)
        g->vram_used_mb = to_mb(usage.vram);
}

static void vram_i915(int fd, GPUProperties *g) {
    drm_i915_query_item item = {0};
    item.query_id = DRM_I915_QUERY_MEMORY_REGIONS;

    drm_i915_query q = {0};
    q.num_items = 1;
    q.items_ptr = reinterpret_cast<uint64_t>(&item);

    if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) != 0 || item.length <= 0)
        return;

    uint8_t *buf = static_cast<uint8_t *>(calloc(1, item.length));
    if (!buf) return;

    item.data_ptr = reinterpret_cast<uint64_t>(buf);

    if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) == 0) {
        drm_i915_query_memory_regions *r = reinterpret_cast<drm_i915_query_memory_regions *>(buf);
        for (uint32_t i = 0; i < r->num_regions; i++) {
            if (r->regions[i].region.memory_class == I915_MEMORY_CLASS_DEVICE) {
                g->vram_total_mb = to_mb(r->regions[i].probed_size);
                break;
            }
        }
    }

    free(buf);
}

static void vram_nouveau(int fd, GPUProperties *g) {
    drm_nouveau_getparam p = {0};
    p.param = NOUVEAU_GETPARAM_FB_SIZE;

    if (ioctl(fd, DRM_IOCTL_NOUVEAU_GETPARAM, &p) == 0 && p.value > 0)
        g->vram_total_mb = to_mb(p.value);
}

// ============================================================================
// PCIe link info (sysfs — no generic DRM ioctl for this)
// ============================================================================
static void pcie_info(int dirfd, GPUProperties *g) {

    char buf[64];

    if (read_str_at(dirfd, "max_link_width", buf, sizeof(buf)) == 0)
        sscanf(buf, "%d", &g->pcie_width);

    if (read_str_at(dirfd, "max_link_speed", buf, sizeof(buf)) == 0) {
        if      (strstr(buf, "64"))  g->pcie_gen = 6;
        else if (strstr(buf, "32"))  g->pcie_gen = 5;
        else if (strstr(buf, "16"))  g->pcie_gen = 4;
        else if (strstr(buf, "8"))   g->pcie_gen = 3;
        else if (strstr(buf, "5"))   g->pcie_gen = 2;
        else if (strstr(buf, "2.5")) g->pcie_gen = 1;
    }
}

// ============================================================================
// Vulkan ICD restriction
//
// By default the Vulkan loader dlopen()s + initializes every installed ICD
// manifest (a dozen-plus with a typical Mesa install) before it can tell us
// which ones actually have hardware. Since we already know each GPU's vendor
// from sysfs, point the loader at only the matching driver(s) so it skips
// the rest — this is the dominant cost of the fallback path.
// ============================================================================

static bool icd_matches_vendor(const char *filename, uint32_t vendor_id) {
    switch (vendor_id) {
        case 0x10DE: return strstr(filename, "nvidia") || strstr(filename, "nouveau");
        case 0x1002:  return strstr(filename, "radeon") != NULL;
        case 0x8086:  return strstr(filename, "intel") != NULL;
        default:      return false;
    }
}

static void restrict_vulkan_icds(const GPUProperties *gpus, int count) {
    static const char *icd_dirs[] = {"/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d"};

    char matches[2048] = {0};
    size_t matches_len = 0;

    for (size_t d = 0; d < sizeof(icd_dirs) / sizeof(icd_dirs[0]); d++) {
        DIR *dir = opendir(icd_dirs[d]);
        if (!dir) continue;

        struct dirent *entry;
        while ((entry = readdir(dir)) != NULL) {
            const char *name = entry->d_name;
            size_t len = strlen(name);
            if (len < 6 || strcmp(name + len - 5, ".json") != 0) continue;
            if (strstr(name, "i686")) continue;  // skip 32-bit manifests

            bool wanted = false;
            for (int i = 0; i < count && !wanted; i++)
                wanted = icd_matches_vendor(name, gpus[i].vendor_id);
            if (!wanted) continue;

            char full[768];
            int n = snprintf(full, sizeof(full), "%s/%s", icd_dirs[d], name);
            // snprintf returns the length it would have written even if truncated;
            // reject that case so we never memcpy past the end of `full`.
            if (n <= 0 || static_cast<size_t>(n) >= sizeof(full)) continue;
            if (matches_len + static_cast<size_t>(n) + 2 > sizeof(matches)) continue;

            if (matches_len > 0) matches[matches_len++] = ':';
            memcpy(matches + matches_len, full, static_cast<size_t>(n));
            matches_len += static_cast<size_t>(n);
        }
        closedir(dir);
    }

    if (matches_len > 0) {
        // VK_DRIVER_FILES is the modern name; VK_ICD_FILENAMES is kept for older loaders.
        setenv("VK_DRIVER_FILES", matches, 1);
        setenv("VK_ICD_FILENAMES", matches, 1);
    }
}

// ============================================================================
// Vulkan fallback (dlopen, no link-time dependency)
// ============================================================================

struct VkGPU {
    uint32_t vendor_id, device_id;
    char slot[32];
    char name[256];
    uint64_t vram_mb, used_mb;
};

static int vulkan_query(VkGPU *out, int max) {
    void *lib = dlopen("libvulkan.so.1", RTLD_LAZY);
    if (!lib) return -1;

    PFN_CreateInst ci = reinterpret_cast<PFN_CreateInst>(dlsym(lib, "vkCreateInstance"));
    PFN_DestroyInst di = reinterpret_cast<PFN_DestroyInst>(dlsym(lib, "vkDestroyInstance"));
    PFN_EnumDevs ed = reinterpret_cast<PFN_EnumDevs>(dlsym(lib, "vkEnumeratePhysicalDevices"));
    PFN_GetProps2 gp = reinterpret_cast<PFN_GetProps2>(dlsym(lib, "vkGetPhysicalDeviceProperties2"));
    PFN_GetMem2 gm = reinterpret_cast<PFN_GetMem2>(dlsym(lib, "vkGetPhysicalDeviceMemoryProperties2"));

    if (!ci || !di || !ed || !gp || !gm) { dlclose(lib); return -1; }

    VkAppInfo ai = {VK_STYPE_APP_INFO, NULL, "HWProbe", 1, NULL, 0, (1u << 22) | (1u << 12)};
    VkInstCreateInfo ici = {VK_STYPE_INST_CREATE, NULL, 0, &ai, 0, NULL, 0, NULL};

    VkInstance inst = NULL;
    if (ci(&ici, NULL, &inst) != 0 || !inst) { dlclose(lib); return -1; }

    uint32_t n = 0;
    if (ed(inst, &n, NULL) != 0) {
        di(inst, NULL);
        dlclose(lib);
        return -1;
    }

    if (n == 0) { di(inst, NULL); dlclose(lib); return 0; }
    if (n > MAX_GPU_CARDS) n = MAX_GPU_CARDS;

    VkPhysicalDevice devs[MAX_GPU_CARDS];
    if (ed(inst, &n, devs) != 0) {
        di(inst, NULL);
        dlclose(lib);
        return -1;
    }

    int cnt = 0;

    for (uint32_t i = 0; i < n && cnt < max; i++) {
        VkPCIBusInfo pci = {VK_STYPE_PCI_BUS_EXT, NULL, 0, 0, 0, 0};
        VkPhysDevProps2 p = {0};
        p.sType = VK_STYPE_PROPS2;
        p.pNext = &pci;
        gp(devs[i], &p);

        VkMemBudget bgt = {0};
        bgt.sType = VK_STYPE_MEM_BUDGET_EXT;
        bgt.pNext = NULL;

        VkMemProps2 m = {0};
        m.sType = VK_STYPE_MEM_PROPS2;
        m.pNext = &bgt;
        gm(devs[i], &m);

        uint64_t total = 0, used = 0;
        for (uint32_t h = 0; h < m.memProps.heapCnt; h++) {
            if (m.memProps.heaps[h].flags & VK_HEAP_DEVICE_LOCAL) {
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
    }

    di(inst, NULL);
    dlclose(lib);
    return cnt;
}

// ============================================================================
// Public API
// ============================================================================

int get_gpu_info(GPUProperties *out, int max_count) {
    if (!out || max_count <= 0) return -1;

    int gpu_count = 0;
    bool needs_vulkan_fallback = false;

    for (int card = 0; card < MAX_GPU_CARDS && gpu_count < max_count; card++) {
        char devpath[64], sysfs[128];

        snprintf(devpath, sizeof(devpath), "/dev/dri/card%d", card);
        snprintf(sysfs, sizeof(sysfs), "/sys/class/drm/card%d/device", card);

        // Resolves the "device" symlink once; every attribute below is then
        // read relative to this fd instead of re-walking the full sysfs path.
        int dirfd = open(sysfs, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (dirfd < 0) continue;

        if (((read_hex_at(dirfd, "class") >> 16) & 0xFF) != 0x03) { close(dirfd); continue; }

        GPUProperties g = {0};
        g.vendor_id = read_hex_at(dirfd, "vendor");
        g.device_id = read_hex_at(dirfd, "device");

        if (!g.vendor_id) { close(dirfd); continue; }

        read_symlink_basename(sysfs, g.pci_slot, sizeof(g.pci_slot));
        read_symlink_basename_at(dirfd, "driver", g.driver, sizeof(g.driver));

        int fd = open(devpath, O_RDWR | O_CLOEXEC);
        if (fd < 0) fd = open(devpath, O_RDONLY | O_CLOEXEC);

        if (fd >= 0) {
            switch (g.vendor_id) {
                case 0x1002: vram_amdgpu(fd, &g);  break;
                case 0x8086: vram_i915(fd, &g);    break;
                case 0x10DE: vram_nouveau(fd, &g); break;
            }

            drmVersionPtr v = drmGetVersion(fd);
            if (v) {
                if (v->desc_len > 0)
                    snprintf(g.name, sizeof(g.name), "%.*s", v->desc_len, v->desc);
                else if (v->name_len > 0)
                    snprintf(g.name, sizeof(g.name), "%.*s", v->name_len, v->name);
                drmFreeVersion(v);
            }

            close(fd);
        }
        pcie_info(dirfd, &g);

        close(dirfd);

        if (!g.vram_total_mb || !g.name[0])
            needs_vulkan_fallback = true;

        out[gpu_count++] = g;
    }

    // Vulkan fallback is expensive; only run if DRM/sysfs left gaps.
    if (!needs_vulkan_fallback || gpu_count == 0)
        return gpu_count;

    VkGPU vk[MAX_GPU_CARDS];
    restrict_vulkan_icds(out, gpu_count);
    int vk_n = vulkan_query(vk, MAX_GPU_CARDS);

    if (vk_n > 0) {
        for (int i = 0; i < gpu_count; i++) {
            if (out[i].vram_total_mb && out[i].vram_used_mb && out[i].name[0])
                continue;

            for (int v = 0; v < vk_n; v++) {
                if (strcmp(out[i].pci_slot, vk[v].slot) != 0) continue;

                if (!out[i].vram_total_mb) out[i].vram_total_mb = vk[v].vram_mb;
                if (!out[i].vram_used_mb)  out[i].vram_used_mb  = vk[v].used_mb;
                if (vk[v].name[0]) snprintf(out[i].name, sizeof(out[i].name), "%s", vk[v].name);
                break;
            }
        }
    }

    return gpu_count;
}
