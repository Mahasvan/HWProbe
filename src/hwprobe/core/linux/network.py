import json
import os
import subprocess

from hwprobe.core.linux.common import pci_path_linux
from hwprobe.models.network_models import NetworkInfo, NICInfo
from hwprobe.models.status_models import Status


def _enrich_with_sysfs_info(nic: NICInfo, status: Status) -> None:
    """Helper to read hardware details directly from Linux sysfs."""
    interface_name = nic.interface
    if not interface_name: return

    # todo: pci.ids file may be locally stored in Linux distros.
    # When a scraper-parser is made, make use of this, to get device name.

    base_path = f"/sys/class/net/{interface_name}/device"

    # Virtual interfaces won't have a /device path
    if not os.path.exists(base_path):
        raise ValueError(f"Interface is virtual: {interface_name}")

    try:
        with open(f"{base_path}/vendor") as f:
            nic.vendor_id = f.read().strip()
            # todo: Manufacturer
    except FileNotFoundError:
        status.make_partial(f"Vendor ID not found for interface {interface_name}")

    try:
        with open(f"{base_path}/device") as f:
            nic.device_id = f.read().strip()
    except FileNotFoundError:
        status.make_partial(f"Device ID not found for interface {interface_name}")

    try:
        with open(f"{base_path}/firmware_node/path") as f:
            nic.acpi_path = f.read().strip()
    except FileNotFoundError:
        status.make_partial(f"Path not found for interface {interface_name}")

    try:
        # Resolves the symlink to get the BDF address (e.g., 0000:01:00.0)
        base_name = os.path.basename(os.path.realpath(base_path))
        nic.pci_path = pci_path_linux(base_name)
    except OSError:
        pass


def _fetch_ip_data() -> NetworkInfo:
    command = ["ip", "-json", "addr", "show"]
    output = subprocess.check_output(command, stderr=subprocess.STDOUT)
    data = json.loads(output.decode())

    network_info = NetworkInfo()

    for row in data:
        nic = NICInfo()
        ifname = row.get("ifname")

        nic.interface = ifname
        nic.type = row.get("link_type")
        nic.mac_address = row.get("address")

        # Extract IP Addresses (Prefer IPv4, fallback to IPv6)
        ip_addr = None
        for addr in row.get("addr_info", []):
            if addr.get("family") == "inet":
                ip_addr = addr.get("local")
                break

        if not ip_addr:
            for addr in row.get("addr_info", []):
                if addr.get("family") == "inet6":
                    ip_addr = addr.get("local")
                    break

        nic.ip_address = ip_addr

        try:
            _enrich_with_sysfs_info(nic, network_info.status)
            network_info.modules.append(nic)
        except ValueError:
            # Virtual interface
            pass

    return network_info


def fetch_network_info() -> NetworkInfo:
    ip_data = _fetch_ip_data()
    return ip_data
