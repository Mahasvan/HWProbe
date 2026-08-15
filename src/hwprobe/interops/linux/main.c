#include <stdint.h>
#include <stddef.h>
#include <stdalign.h>
#include <vulkan/vulkan.h>

typedef struct VkPhysDevProps
{
    uint32_t api, driver, vendorID, deviceID, devType;
    char name[256];
    uint8_t uuid[16];
    alignas(uint64_t) uint8_t _limits[504];
    uint8_t _sparse[20];
} VkPhysDevProps;

_Static_assert(
    sizeof(VkPhysDevProps) == sizeof(VkPhysicalDeviceProperties),
    "VkPhysDevProps size mismatch"
);

_Static_assert(
    alignof(VkPhysDevProps) == alignof(VkPhysicalDeviceProperties),
    "VkPhysDevProps alignment mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, api) ==
    offsetof(VkPhysicalDeviceProperties, apiVersion),
    "api offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, driver) ==
    offsetof(VkPhysicalDeviceProperties, driverVersion),
    "driver offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, vendorID) ==
    offsetof(VkPhysicalDeviceProperties, vendorID),
    "vendorID offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, deviceID) ==
    offsetof(VkPhysicalDeviceProperties, deviceID),
    "deviceID offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, devType) ==
    offsetof(VkPhysicalDeviceProperties, deviceType),
    "deviceType offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, name) ==
    offsetof(VkPhysicalDeviceProperties, deviceName),
    "deviceName offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, uuid) ==
    offsetof(VkPhysicalDeviceProperties, pipelineCacheUUID),
    "UUID offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, _limits) ==
    offsetof(VkPhysicalDeviceProperties, limits),
    "limits offset mismatch"
);

_Static_assert(
    offsetof(VkPhysDevProps, _sparse) ==
    offsetof(VkPhysicalDeviceProperties, sparseProperties),
    "sparseProperties offset mismatch"
);

int main()
{
    return 0;
}