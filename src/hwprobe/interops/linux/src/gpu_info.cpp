#include "../include/gpu_info.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <stdalign.h>
#include <unistd.h>
#include <vector>
#include <xf86drm.h>

#include <drm/amdgpu_drm.h>
#include <drm/i915_drm.h>
#include <drm/nouveau_drm.h>
#include <drm/radeon_drm.h>
#include <drm/xe_drm.h>
#include <sys/ioctl.h>
#include <vulkan/vulkan.h>

typedef struct VkGPU {
  uint32_t vendor_id;
  uint32_t device_id;
  uint64_t vram_mb;
  uint64_t used_mb;
  char     slot[64];
  char     name[256];
} VkGPU;

inline GPUInfoQueryStatus operator|(GPUInfoQueryStatus a, GPUInfoQueryStatus b) {
    return static_cast<GPUInfoQueryStatus>(static_cast<uint32_t>(a) | static_cast<uint32_t>(b));
}

inline GPUInfoQueryStatus operator|=(GPUInfoQueryStatus a, GPUInfoQueryStatus b) {
    a = a | b;
    return a;
}

static uint64_t to_mb(uint64_t bytes) { return bytes / BYTES_PER_MB; }

static PCIAddress parse_bdf_to_pci_addr(const char *bdf)
{
  PCIAddress pciAddr = {0};
  if (!bdf || strlen(bdf) == 0) {
    return pciAddr;
  }

  char *endptr = nullptr;

  uint16_t domain = strtoll(bdf, &endptr, 16u);
  if (*endptr != ':') {
    return pciAddr;
  }

  uint8_t bus = strtoll(endptr + 1, &endptr, 16u);
  if (*endptr != ':') {
    return pciAddr;
  }

  uint8_t device = strtoll(endptr + 1, &endptr, 16u);
  if (*endptr != '.') {
    return pciAddr;
  }

  uint8_t function = strtoll(endptr + 1, &endptr, 16u);

  pciAddr.domain   = domain;
  pciAddr.bus      = bus;
  pciAddr.device   = device;
  pciAddr.function = function;

  return pciAddr;
}

//
// DRM ioctl VRAM queries
//

static void vram_amdgpu(int fd, GPUProperties *g)
{
  if (g == nullptr) {
    return;
  }

  drm_amdgpu_info        req = {0};
  drm_amdgpu_memory_info mem;

  req.return_pointer = reinterpret_cast<uint64_t>(&mem);
  req.return_size    = sizeof(mem);
  req.query          = AMDGPU_INFO_MEMORY;

  if (ioctl(fd, DRM_IOCTL_AMDGPU_INFO, &req) == 0) {
    g->vram_total_mb = to_mb(mem.vram.total_heap_size);
    g->vram_used_mb  = to_mb(mem.vram.heap_usage);
  }
}

static void vram_radeon(int fd, GPUProperties *g)
{
  if (g == nullptr) {
    return;
  }

  drm_radeon_gem_info gem_info = {0};

  if (ioctl(fd, DRM_IOCTL_RADEON_GEM_INFO, &gem_info) == 0) {
    g->vram_total_mb = to_mb(gem_info.vram_size);
  }

  drm_radeon_info info = {0};
  info.request         = RADEON_INFO_VRAM_USAGE;
  info.value           = (uint64_t)(uintptr_t)(&g->vram_used_mb);
  if (ioctl(fd, DRM_IOCTL_RADEON_INFO, &info) < 0) {
    g->vram_used_mb = 0;
  }
}

static void vram_i915(int fd, GPUProperties *g)
{
  if (g == nullptr) {
    return;
  }

  drm_i915_query_item item = {0};
  item.query_id            = DRM_I915_QUERY_MEMORY_REGIONS;

  drm_i915_query q = {0};
  q.num_items      = 1;
  q.items_ptr      = reinterpret_cast<uint64_t>(&item);

  if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) != 0 || item.length <= 0) {
    return;
  }

  uint8_t *buf = static_cast<uint8_t *>(calloc(1, item.length));
  if (!buf) {
    return;
  }

  item.data_ptr = reinterpret_cast<uint64_t>(buf);

  if (ioctl(fd, DRM_IOCTL_I915_QUERY, &q) == 0) {
    drm_i915_query_memory_regions *r =
        reinterpret_cast<drm_i915_query_memory_regions *>(buf);
    for (uint32_t i = 0; i < r->num_regions; i++) {
      if (r->regions[i].region.memory_class == I915_MEMORY_CLASS_DEVICE) {
        g->vram_total_mb = to_mb(r->regions[i].probed_size);
        break;
      }
    }
  }

  free(buf);
}

static void vram_xe(int fd, GPUProperties *g)
{
    if (g == nullptr || fd < 0) {
        return;
    }

    struct drm_xe_device_query query = {};
    query.query = DRM_XE_DEVICE_QUERY_MEM_REGIONS;

    if (ioctl(fd, DRM_IOCTL_XE_DEVICE_QUERY, &query) != 0 || query.size == 0) {
        g->vram_total_mb = 0;
        g->vram_used_mb = 0;
        return;
    }

    std::vector<uint8_t> buffer(query.size);
    query.data = reinterpret_cast<uintptr_t>(buffer.data());

    if (ioctl(fd, DRM_IOCTL_XE_DEVICE_QUERY, &query) != 0) {
        g->vram_total_mb = 0;
        g->vram_used_mb = 0;
        return;
    }

    const auto *regions = reinterpret_cast<const struct drm_xe_query_mem_regions *>(buffer.data());

    uint64_t total_vram = 0;
    uint64_t used_vram = 0;

    for (uint32_t i = 0; i < regions->num_mem_regions; ++i) {
        const auto &mem = regions->mem_regions[i];

        // Filter out system memory (SYSMEM) to only aggregate discrete VRAM
        if (mem.mem_class == DRM_XE_MEM_REGION_CLASS_VRAM) {
            total_vram += mem.total_size;
            used_vram += mem.used;
        }
    }

    g->vram_total_mb = to_mb(total_vram);
    g->vram_used_mb = to_mb(used_vram);
}

static void vram_nouveau(int fd, GPUProperties *g)
{
  if (g == nullptr) {
    return;
  }

  drm_nouveau_getparam p = {0};
  p.param                = NOUVEAU_GETPARAM_FB_SIZE;

  if (ioctl(fd, DRM_IOCTL_NOUVEAU_GETPARAM, &p) == 0 && p.value > 0) {
    g->vram_total_mb = to_mb(p.value);
  }
}

static int vulkan_query(VkGPU *out, const PCIAddress *pciAddr)
{
  if (pciAddr == NULL) {
    return -1;
  }

  // Request the get_physical_device_properties2 extension to read PCI bus
  // info.
  const char *instExts[] = {
      VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME};

  VkApplicationInfo appInfo  = {};
  appInfo.sType              = VK_STRUCTURE_TYPE_APPLICATION_INFO;
  appInfo.pApplicationName   = "HWProbe";
  appInfo.applicationVersion = VK_MAKE_VERSION(1, 0, 0);
#ifdef VK_API_VERSION_1_2
  appInfo.apiVersion = VK_API_VERSION_1_2;
#else
  appInfo.apiVersion = VK_MAKE_VERSION(1, 2, 0);
#endif

  VkInstanceCreateInfo instCreate    = {};
  instCreate.sType                   = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
  instCreate.pApplicationInfo        = &appInfo;
  instCreate.enabledExtensionCount   = 1;
  instCreate.ppEnabledExtensionNames = instExts;

  VkInstance inst = VK_NULL_HANDLE;
  VkResult   r    = vkCreateInstance(&instCreate, NULL, &inst);
  if (r != VK_SUCCESS || inst == VK_NULL_HANDLE) {
    return -1;
  }

  uint32_t numberOfDevices = 0;
  r = vkEnumeratePhysicalDevices(inst, &numberOfDevices, NULL);
  if (r != VK_SUCCESS) {
    vkDestroyInstance(inst, NULL);
    return -1;
  }

  if (numberOfDevices == 0) {
    vkDestroyInstance(inst, NULL);
    return 0;
  }

  if (numberOfDevices > MAX_GPU_CARDS) {
    numberOfDevices = MAX_GPU_CARDS;
  }

  VkPhysicalDevice devs[MAX_GPU_CARDS];
  r = vkEnumeratePhysicalDevices(inst, &numberOfDevices, devs);
  if (r != VK_SUCCESS) {
    vkDestroyInstance(inst, NULL);
    return -1;
  }

  uint32_t cnt = 0;

  for (uint32_t i = 0; i < numberOfDevices && cnt < MAX_GPU_CARDS; i++) {
    VkGPU *g = &out[cnt++];

    VkPhysicalDevicePCIBusInfoPropertiesEXT pci = {};
    pci.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT;

    VkPhysicalDeviceProperties2 props2 = {};
    props2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
    props2.pNext = &pci;
    vkGetPhysicalDeviceProperties2(devs[i], &props2);

    snprintf(
        g->slot, sizeof(g->slot), "%04x:%02x:%02x.%x", pci.pciDomain,
        pci.pciBus, pci.pciDevice, pci.pciFunction);

    if (pciAddr->domain != pci.pciDomain || pciAddr->bus != pci.pciBus ||
        pciAddr->device != pci.pciDevice ||
        pciAddr->function != pci.pciFunction) {
      // Skip devices that don't match the PCI address.
      continue;
    }

    VkPhysicalDeviceMemoryBudgetPropertiesEXT budget = {};
    budget.sType =
        VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_BUDGET_PROPERTIES_EXT;

    VkPhysicalDeviceMemoryProperties2 memProps2 = {};
    memProps2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_PROPERTIES_2;
    memProps2.pNext = &budget;
    vkGetPhysicalDeviceMemoryProperties2(devs[i], &memProps2);

    uint64_t total = 0, used = 0;
    uint32_t heapCnt = memProps2.memoryProperties.memoryHeapCount;
    for (uint32_t h = 0; h < heapCnt; h++) {
      if (memProps2.memoryProperties.memoryHeaps[h].flags &
          VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) {
        total += memProps2.memoryProperties.memoryHeaps[h].size;
        // total - budget ≈ system-wide VRAM usage
        if (budget.heapBudget[h] > 0 &&
            budget.heapBudget[h] <
                memProps2.memoryProperties.memoryHeaps[h].size)
          used += memProps2.memoryProperties.memoryHeaps[h].size -
                  budget.heapBudget[h];
      }
    }

    g->vendor_id = props2.properties.vendorID;
    g->device_id = props2.properties.deviceID;
    g->vram_mb   = to_mb(total);
    g->used_mb   = to_mb(used);

    snprintf(g->name, sizeof(g->name), "%s", props2.properties.deviceName);
  }

  vkDestroyInstance(inst, NULL);
  return cnt;
}

/**
 * Get GPU information for a specific PCI device.
 *
 * @note    This function also returns the current VRAM usage, even though it
 * currently has no proper application in HWProbe. It shall stay here for future
 * reference if we decide to query similar information on other platforms.
 *
 * @param bdf The PCI bus:device.function string (e.g., "0000:01:00.0").
 * @param vendor_id The PCI vendor ID of the GPU (e.g., 0x1002 for AMD, 0x8086
 * for Intel, 0x10DE for NVIDIA).
 * @param out Pointer to a GPUProperties struct to receive the GPU information.
 * @return 0 on success, -1 on failure.
 */
GPUInfoQueryStatus get_gpu_info(const char *bdf, uint32_t vendor_id, GPUProperties *out)
{
  if (!bdf || !out) {
    return GPUInfoQueryStatus::FAILURE;
  }

  GPUInfoQueryStatus status = GPUInfoQueryStatus::FAILURE;

  // Find the DRM card node under /sys/bus/pci/devices/<bdf>/drm/cardN.
  char drm_dir_path[160];
  snprintf(
      drm_dir_path, sizeof(drm_dir_path), "/sys/bus/pci/devices/%s/drm", bdf);

  char card_name[256] = {0};
  DIR *drm_dir        = opendir(drm_dir_path);

  if (drm_dir) {
    struct dirent *entry;

    while ((entry = readdir(drm_dir)) != NULL) {
      if (strncmp(entry->d_name, "card", 4) == 0 && entry->d_name[4] >= '0' &&
          entry->d_name[4] <= '9') {
        snprintf(card_name, sizeof(card_name), "%s", entry->d_name);
        break;
      }
    }
    closedir(drm_dir);
  }

  GPUProperties g = {};

  if (card_name[0]) {
    char devpath[64];

    snprintf(devpath, sizeof(devpath), "/dev/dri/%s", card_name);

    int fd = open(devpath, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
      fd = open(devpath, O_RDONLY | O_CLOEXEC);
    }

    if (fd >= 0) {
      drmVersionPtr drm_version = drmGetVersion(fd);

      // TODO: Test all the DRM IOCTL methods; support from users
      if (drm_version) {
        if (strcmp(drm_version->name, "amdgpu") == 0) {
          vram_amdgpu(fd, &g);
        }
        else if (strcmp(drm_version->name, "radeon") == 0) {
          vram_radeon(fd, &g);
        }
        else if (strcmp(drm_version->name, "i915") == 0) {
          vram_i915(fd, &g);
        }
        else if (strcmp(drm_version->name, "xe") == 0) {
          vram_xe(fd, &g);
        }
        else if (strcmp(drm_version->name, "nouveau") == 0) {
          vram_nouveau(fd, &g);
        }
      }
      close(fd);
    }
  }

  // TODO: Remove 'g.name[0]' check when pci-ids parser is implemented!
  // Vulkan fallback if DRM didn't give us complete info.
  if (!g.vram_total_mb || !g.name[0]) {
    PCIAddress pciAddr = parse_bdf_to_pci_addr(bdf);
    VkGPU      vk[MAX_GPU_CARDS];
    int        vk_n = vulkan_query(vk, &pciAddr);

    if (vk_n > 0) {
      for (int v = 0; v < vk_n; v++) {
        if (strcmp(bdf, vk[v].slot) != 0) {
          continue;
        }

        if (!g.vram_total_mb) {
          g.vram_total_mb = vk[v].vram_mb;
          status = GPUInfoQueryStatus::VULKAN_VRAM_FALLBACK;
        }
        if (!g.vram_used_mb) {
          g.vram_used_mb = vk[v].used_mb;
          status = GPUInfoQueryStatus::VULKAN_VRAM_FALLBACK;
        }
        if (vk[v].name[0]) {
          snprintf(g.name, sizeof(g.name), "%s", vk[v].name);
          if (status == GPUInfoQueryStatus::VULKAN_VRAM_FALLBACK) {
            status |= GPUInfoQueryStatus::VULKAN_NAME_FALLBACK;
          } else {
            status = GPUInfoQueryStatus::VULKAN_NAME_FALLBACK;
          }
        }
        break;
      }
    }
  }

  *out = g;
  return status;
}
