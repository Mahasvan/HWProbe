import plistlib
import re
import subprocess
from typing import Optional

from hwprobe.models.network_models import NetworkInfo, NICInfo


def _fetch_controllers() -> list[str]:
    output = subprocess.run(["ipconfig", "getiflist"], capture_output=True)
    stripped = output.stdout.decode("utf-8").strip()
    return stripped.split(" ") if stripped else []


def _fetch_ethernet_details() -> dict[str, NICInfo]:
    output = subprocess.run(["system_profiler", "SPEthernetDataType", "-xml"], capture_output=True)
    plist = plistlib.loads(output.stdout)
    res = {}
    for item in plist:
        for ethernet_controller in item.get("_items", []):
            bsd_device_name = ethernet_controller.get("spethernet_BSD_Device_Name")

            info = NICInfo()
            info.vendor_id = ethernet_controller.get("spethernet_vendor-id")
            info.manufacturer = ethernet_controller.get("spethernet_vendor_name")
            info.device_id = ethernet_controller.get("spethernet_product-id")

            res[bsd_device_name] = info

    return res


def _find_child(children: list, key: str, value: str) -> Optional[dict]:
    """Find the first child dict where dict[key] == value."""
    return next((x for x in children if x and x.get(key) == value), None)


def _traverse_ioreg(root: dict, steps: list[tuple], result_key: str = "IORegistryEntryName") -> Optional[str]:
    """
    Generic IORegistry depth-first traversal.

    Each step is a (match_key, match_value) pair used to select the next child
    via _find_child.  After all steps, ``result_key`` is read from the final node.

    Example – AppleBCMWLANCore path:
        steps = [
            ("IORegistryEntryName", "AppleBCMWLANSkywalkInterface"),
            ("IOObjectClass",       "IOSkywalkLegacyEthernet"),
            ("IOObjectClass",       "IOSkywalkLegacyEthernetInterface"),
        ]
    """
    node = root
    for match_key, match_value in steps:
        node = _find_child(node.get("IORegistryEntryChildren", []), match_key, match_value)
        if node is None:
            return None
    return node.get(result_key)


# Traversal path for AppleBCMWLANCore (Intel Macs / most Apple Silicon)
_STEPS_BCM_WLAN = [
    ("IORegistryEntryName", "AppleBCMWLANSkywalkInterface"),
    ("IOObjectClass", "IOSkywalkLegacyEthernet"),
    ("IOObjectClass", "IOSkywalkLegacyEthernetInterface"),
]

# Traversal path for AppleWLANDriver (Wi-Fi 7, M5 series)
# Note: the second level is matched by IORegistryEntryName, not IOObjectClass.
_STEPS_WLAN_DRIVER = [
    ("IORegistryEntryName", "AppleWLANInterfaceSTA"),
    ("IORegistryEntryName", "IOSkywalkLegacyEthernet"),
    ("IOObjectClass", "IOSkywalkLegacyEthernetInterface"),
]


def _get_bsd_interface_apple_silicon(item: dict, driver: str = "AppleBCMWLANCore") -> Optional[str]:
    """
    Resolve the BSD interface name for Apple Silicon Wi-Fi controllers.

    Tries the AppleBCMWLANCore path first, then falls back to the
    AppleWLANDriver (Wi-Fi 7 / Skywalk STA) path.
    """
    mapping = {
        "AppleBCMWLANCore": _STEPS_BCM_WLAN,
        "AppleWLANDriver": _STEPS_WLAN_DRIVER,
        # Add to this if more drivers are supported
    }

    if driver in mapping:
        return _traverse_ioreg(item, mapping[driver])

    return _traverse_ioreg(item, _STEPS_BCM_WLAN) or _traverse_ioreg(item, _STEPS_WLAN_DRIVER)


def _fetch_airport_details() -> dict[str, NICInfo]:
    """
    Earlier, `system_profiler SPAirPortDataType -xml` was used to get the vendor and device id.
    However, this was too slow, and we can get the same details from `ioreg`, while it being faster.
    """
    output = subprocess.run(["ioreg", "-c", "IO80211Controller", "-r", "-a"], capture_output=True)
    plist = plistlib.loads(output.stdout)

    res = {}

    io_name_pattern = re.compile(r"pci([0-9a-fA-F]{4}),([0-9a-fA-F]{4})")

    for item in plist:
        driver = item.get("IORegistryEntryName")

        if not driver:
            continue

        if driver == "AirPort_BrcmNIC":
            # Intel Macs, usually
            io_name = item.get("IONameMatched", "")
            io_model = item.get("IOModel", "")
            match = io_name_pattern.match(io_name)
            vendor, device = match.groups()

            nic_info = NICInfo()
            nic_info.vendor_id = "0x" + vendor
            nic_info.device_id = "0x" + device
            if io_model:
                nic_info.name = io_model

            for child in item.get("IORegistryEntryChildren", []):
                if not child.get("IOObjectClass", "") == "AirPort_BrcmNIC_Interface":
                    continue
                bcm_identifier = child.get("IORegistryEntryName")
                res[bcm_identifier] = nic_info
                break

        elif driver == "AppleBCMWLANCore":
            # Most Apple Silicon Macs
            module_data = item.get("ModuleDictionary", {})
            nic_info = NICInfo()
            nic_info.vendor_id = hex(module_data.get("ManufacturerID", 0))
            nic_info.device_id = hex(module_data.get("ProductID", 0))

            if module_data.get("subsystem-vendor-id") == 4203:  # 0x106b, Apple
                nic_info.manufacturer = "Apple"

            bsd_identifier = _get_bsd_interface_apple_silicon(item, driver=driver)
            if bsd_identifier:
                res[bsd_identifier] = nic_info

        elif driver == "AppleWLANDriver":
            # Wi-Fi 7 driver for the M5 series

            device_info = item.get("AirshipDeviceCriteria")

            chipset = device_info.get("Chipset")
            vendor = device_info.get("Vendor")

            bsd_identifier = _get_bsd_interface_apple_silicon(item, driver=driver)
            nic_info = NICInfo()

            if vendor:
                nic_info.manufacturer = f"Apple ({vendor})"
            else:
                nic_info.manufacturer = "Apple"

            if chipset:
                nic_info.name = f"Wi-Fi ({chipset} chipset)"

            res[bsd_identifier] = nic_info

        elif driver == "AirPort_Brcm4331":
            # Older Intel Macs with Broadcom BCM4331 chipset
            io_name = item.get("IONameMatched", "")
            io_model = item.get("IOModel", "")
            match = io_name_pattern.match(io_name)

            if match:
                vendor, device = match.groups()
                nic_info = NICInfo()
                nic_info.vendor_id = "0x" + vendor
                nic_info.device_id = "0x" + device
                if io_model:
                    nic_info.name = io_model

                # Find the BSD interface name from the child "en1" entry
                for child in item.get("IORegistryEntryChildren", []):
                    if child.get("IOObjectClass", "").startswith("en"):
                        bsd_identifier = child.get("IORegistryEntryName")
                        res[bsd_identifier] = nic_info
                        break

        else:
            # todo: Implement for drivers such as AirPortAtheros40, AirPortBrcm4331, AirPortBrcm4360
            print("Unknown driver: ", driver)
            print("Please contact developer with this information to help improve support for your machine.")
            continue

    return res


def _fetch_system_profiler_details(valid_bsd_interfaces: list[str]) -> NetworkInfo:
    output = subprocess.run(["system_profiler", "SPNetworkDataType", "-xml"], capture_output=True)
    plist = plistlib.loads(output.stdout)
    network_info = NetworkInfo()

    ethernet_info: Optional[dict[str, NICInfo]] = None
    airport_info: Optional[dict[str, NICInfo]] = None

    for item in plist:
        for network_controller in item.get("_items", []):
            module = NICInfo()

            bsd_interface_name = network_controller.get("interface")
            if bsd_interface_name not in valid_bsd_interfaces:
                continue

            module.interface = bsd_interface_name
            module.name = network_controller.get("_name", "")
            module.mac_address = network_controller.get("Ethernet", {}).get("MAC Address")
            if not module.mac_address:
                # Sometimes, unplugged devices also show up in system_profiler.
                # todo: Still, some unplugged devices show up, which have duplicated MAC addresses.
                # Can we prune them? They show up in System Information too though, so not a dealbreaker.
                continue
            module.type = network_controller.get("type")
            # todo: Make this an ENUM and share with other OSes
            ip_addresses = network_controller.get("IPv4", {}).get("Addresses")
            if ip_addresses:
                module.ip_address = ip_addresses[0]

            if module.type == "Ethernet":
                if ethernet_info is None:
                    ethernet_info = _fetch_ethernet_details()
                if bsd_interface_name in ethernet_info:
                    module.vendor_id = ethernet_info[bsd_interface_name].vendor_id
                    module.manufacturer = ethernet_info[bsd_interface_name].manufacturer
                    module.device_id = ethernet_info[bsd_interface_name].device_id

            elif module.type == "AirPort":
                if airport_info is None:
                    airport_info = _fetch_airport_details()
                if bsd_interface_name in airport_info:
                    if manufacturer := airport_info[bsd_interface_name].manufacturer:
                        module.manufacturer = manufacturer
                    if name := airport_info[bsd_interface_name].name:
                        module.name = name
                    if vendor_id := airport_info[bsd_interface_name].vendor_id:
                        module.vendor_id = vendor_id
                    if device_id := airport_info[bsd_interface_name].device_id:
                        module.device_id = device_id

            network_info.modules.append(module)

    return network_info


def fetch_network_info() -> NetworkInfo:
    controllers = _fetch_controllers()
    return _fetch_system_profiler_details(controllers)
