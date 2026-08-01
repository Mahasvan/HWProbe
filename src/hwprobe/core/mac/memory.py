import plistlib
import subprocess

from hwprobe.models.memory_models import MemoryInfo, MemoryModuleInfo, MemoryModuleSlot
from hwprobe.models.size_models import Gigabyte, Megabyte, StorageSize
from hwprobe.models.status_models import StatusType


def get_ram_size_from_reg(reg) -> list[StorageSize]:
    """
    Observed values of reg:
    "02 00 00 00 00 00 00 00 02 00 00 00 00 00 00 00" -> Two sticks of 4GB each
    "00 00 00 80 00 00 00 80 00 00 00 80 00 00 00 80" -> Two sticks of 2GB each

    For simplicity, we can drop all '\x00's, and only retain the non-zero values.
    Then, multiply every remaining hex-byte by 4096, to get an array of RAM Capacities.

    (n * 0x010000 / 0x10) is used to multiply n by 4096.
    - 0x010000 is 65536.
    - 0x10 is 16.
    - The multiplier is 65536 / 16 = 4096.

    This works for the first example (and most others encountered during testing),
    but not for the second example, which is from a 2006 C2D iMac

    DeviceTree Specification:
    https://devicetree-specification.readthedocs.io/en/latest/chapter2-devicetree-basics.html#reg

    :param reg: value of the "reg" key in IOreg.
    :return: Array of StorageSize (MegaByte) objects.
    """

    sizes = [round(n * 0x010000 / 0x10) for n in reg.replace(b"\x00", b"")]
    return [Megabyte(capacity=x) for x in sizes]


def get_arm_ram_info() -> MemoryInfo:
    # ARM macOS doesn't expose all properties that x86 macs do.
    memory_info = MemoryInfo()
    memory_info.status.messages.append("ARM macOS only exposes partial RAM data.")

    try:
        value = subprocess.check_output(["system_profiler", "SPMemoryDataType", "-xml"])
        pl = plistlib.loads(value, fmt=plistlib.FMT_XML)
    except Exception as e:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("Failed to parse SPMemoryDataType: " + str(e))
        return memory_info

    try:
        for entry in pl:
            sticks = entry["_items"]
            for stick in sticks:
                module = MemoryModuleInfo()
                try:
                    # This is a dictionary
                    for k, v in stick.items():
                        if k == "SPMemoryDataType" and v.strip():
                            module.capacity = Gigabyte(capacity=int(v.strip().removesuffix(" GB")))

                        if "manufacturer" in k:
                            module.manufacturer = v
                        if "type" in k:
                            module.type = v

                    memory_info.modules.append(module)
                except Exception as e:
                    memory_info.status.type = StatusType.PARTIAL
                    memory_info.status.messages.append("Failed to parse SPMemoryDataType: " + str(e))

    except Exception as e:
        # We preserve messages if it was PartialStatus prior to this exception
        memory_info.status.type = StatusType.PARTIAL
        memory_info.status.messages.append("Failed to parse SPMemoryDataType: " + str(e))
    return memory_info


def get_ram_size_from_system_profiler() -> list[StorageSize]:
    sizes = []
    value = subprocess.check_output(["system_profiler", "SPMemoryDataType", "-xml"])
    pl = plistlib.loads(value, fmt=plistlib.FMT_XML)
    for entry in pl:
        items = entry.get("_items")
        for item in items:
            sticks = item.get("_items")
            for stick in sticks:
                size = stick.get("dimm_size")
                if size:
                    sizes.append(int(size.removesuffix(" GB")))
    return [Gigabyte(capacity=x) for x in sizes]


def fetch_memory_info() -> MemoryInfo:
    memory_info = MemoryInfo()
    """
    Memory Module Information, can only work on Intel and AMD machines.
    Does not work on Apple Silicon, because the modules are part of the SoC, and the info we need is not exposed.
    """
    arch = subprocess.check_output(["uname", "-m"]).decode()
    """
    Output:
    x86_64 for late-model Intel Macs
    i386 for earlier Intel Macs
    arm64 for Apple Silicon
    """
    if "arm" in arch.lower():
        return get_arm_ram_info()

    """
    We get the output of ioreg as a Plist, and parse it using Python's Plist library.
    `-alw0` forces a Plist output
    `-p` is used to traverse registry over the IODeviceTree plane (IOService is default)
    """
    try:
        output = subprocess.check_output(["ioreg", "-alw0", "-p", "IODeviceTree"])
        pl = plistlib.loads(output, fmt=plistlib.FMT_XML)

        children = pl["IORegistryEntryChildren"]
    except Exception as e:
        memory_info.status.type = StatusType.FAILED
        memory_info.status.messages.append("Failed to parse ioreg command output: " + str(e))
        return memory_info

    dimm_manufacturer = []
    dimm_part_numbers = []
    dimm_serial_number = []
    dimm_speeds = []
    dimm_sizes = []
    dimm_types = []
    ecc_enabled = False
    # todo: Add ECC Detection to other OSes, and the Schema
    dimm_slots = []

    try:
        for child in children:
            array = child["IORegistryEntryChildren"]
            for entry in array:
                if entry["IORegistryEntryName"] != "memory":
                    continue

                # This is the dictionary entry we want to parse
                for k, v in entry.items():
                    """
                    Actual Key names:
                    - dimm-manufacturer
                    - dimm-part-number
                    - dimm-serial-number
                    - dimm-speeds
                    - dimm-types
                    - ecc-enabled
                    - reg
                    - slot-names
                    
                    We don't use exact matching in case there are some discrepancies across machines.
                    Since we have to accumulate all properties in their own arrays anyway,
                    and make the MemoryModuleInfo afterwards, there is no downsides to iterating through all keys.
                    """

                    # We use exact matching here because otherwise, it may match for IORegistryXYZ
                    if k.lower() == "reg":
                        dimm_sizes = get_ram_size_from_reg(v)

                    if "manufacturer" in k.lower():
                        dimm_manufacturer.extend([x.decode() for x in v.split(b"\x00") if x.decode().strip()])

                    if "part-number" in k.lower():
                        dimm_part_numbers.extend([x.decode() for x in v.split(b"\x00") if x.decode().strip()])

                    if "serial-number" in k.lower():
                        dimm_serial_number.extend([x.decode() for x in v.split(b"\x00") if x.decode().strip()])

                    if "speed" in k.lower():
                        dimm_speeds.extend([x.decode() for x in v.split(b"\x00") if x.decode().strip()])

                    if "type" in k.lower():
                        dimm_types.extend([x.decode() for x in v.split(b"\x00") if x.decode().strip()])

                    if "ecc-enabled" in k.lower():
                        ecc_enabled = ecc_enabled or v

                    if "slot-name" in k.lower():
                        dimm_slots = [x.decode().split("/") for x in v.split(b"\x00") if x.decode().strip()]

        # Now we attempt to get more accurate RAM Module Capacities
        """
        The "reg" key does not strictly encode the RAM size, but in a lot of machines, this does work.
        From testing however, the behaviour assumed in get_ram_size_from_reg() is not consistent. 
        So, we will use the output of `system_profiler SPMemoryDataType` to get the RAM sizes.
        
        Note that system_profiler may not be available in recovery environments.
        Therefore, we initially load the values of the "reg" key.
        Afterwards, replace the values by the output from system profiler.
        If system profiler fails to work, we add a message that the RAM size may not be accurate, 
        and retain the values from "reg". 
        """
        try:
            sysprofiler_dimm_sizes = get_ram_size_from_system_profiler()
            dimm_sizes = sysprofiler_dimm_sizes
        except Exception as e:
            # We don't have to make it a PartialStatus, because we already have semi-accurate data from the "reg" field.
            memory_info.status.messages.append(
                "Failed to get RAM size from system profiler. RAM Capacity may not be accurate: " + str(e)
            )

    except Exception as e:
        memory_info.status.type = StatusType.PARTIAL
        memory_info.status.messages.append("Error parsing ioreg plist: " + str(e))

    n_modules = max(
        [
            len(dimm_manufacturer),
            len(dimm_part_numbers),
            len(dimm_serial_number),
            len(dimm_speeds),
            len(dimm_types),
            len(dimm_slots),
        ]
    )

    for i in range(n_modules):
        module = MemoryModuleInfo()
        try:
            if i < len(dimm_manufacturer):
                module.manufacturer = dimm_manufacturer[i]
            if i < len(dimm_part_numbers):
                module.part_number = dimm_part_numbers[i]
            if i < len(dimm_types):
                module.type = dimm_types[i]
            if i < len(dimm_sizes):
                module.capacity = dimm_sizes[i]
            if i < len(dimm_slots):
                module.slot = MemoryModuleSlot(channel=dimm_slots[i][0], bank=dimm_slots[i][1])
            if i < len(dimm_speeds):
                module.frequency_mhz = int(dimm_speeds[i].removesuffix("MHz"))
            module.supports_ecc = ecc_enabled
            memory_info.modules.append(module)

        except Exception as e:
            memory_info.status.type = StatusType.PARTIAL
            memory_info.status.messages.append("Failed to parse DIMM info: " + str(e))

    return memory_info
