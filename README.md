# HWProbe

A cross-platform Python library that gathers hardware component info — CPU, GPU, memory, storage, and
network — from Linux, macOS, and Windows, returning it in a **consistent, strictly-typed schema** so your
code doesn't need per-platform branches.

- To get started, read the **[Quickstart](https://mahasvan.github.io/HWProbe/quickstart.html).**
- Additionally, you can view the **[Documentation](https://mahasvan.github.io/HWProbe/)**.

## Features

- **Consistent schema everywhere** — every platform returns the same [Pydantic](https://docs.pydantic.dev/latest/concepts/models/) models, so the same code works unmodified on Linux, macOS, and Windows.
- **Structured output** — access data as Python objects, dicts, or JSON-serializable strings.
- **No required external tools** — Linux/macOS/Windows ship optional native C++ accelerators (see [interops](src/hwprobe/interops)) that query the kernel/IOKit/WMI directly instead of shelling out to external tools, with automatic fallback if the native library isn't built.
- **Per-component granularity** — fetch just the CPU, or just storage, instead of the whole hardware profile.

## Requirements

- Python 3.9 or newer.

## Installation

### macOS / Linux

```bash
pip3 install HWProbe
```

### Windows

```bash
pip install HWProbe
```

## Usage

```python
from hwprobe import HardwareManager
import json

hm = HardwareManager()

data = hm.fetch_hardware_info()

# All data returned are Pydantic models and have strict schema
# You can use it as is, or serialize it to JSON if you wish.
# We print the data in JSON here for readability.

json_data = json.loads(data.model_dump_json())
print(json.dumps(json_data, indent=2))
```

You can also fetch a single component instead of everything at once:

```python
from hwprobe import HardwareManager

hm = HardwareManager()
cpu = hm.fetch_cpu_info()
print(cpu.name, cpu.vendor)
```

<details>

<summary>Sample Output</summary>

```json
{
  "cpu": {
    "status": {
      "type": "success",
      "messages": []
    },
    "name": "Apple M3 Pro",
    "architecture": "ARM",
    "bitness": 64,
    "arch_version": "8",
    "vendor": "Apple",
    "sse_flags": [],
    "cores": 12,
    "threads": 12
  },
  "memory": {
    "status": {
      "type": "success",
      "messages": [
        "ARM macOS only exposes partial RAM data."
      ]
    },
    "modules": [
      {
        "manufacturer": "Micron",
        "part_number": null,
        "type": "LPDDR5",
        "capacity": {
          "capacity": 18,
          "unit": "GB"
        },
        "frequency_mhz": null,
        "slot": null,
        "supports_ecc": null,
        "ecc_type": null
      }
    ]
  },
  "storage": {
    "status": {
      "type": "success",
      "messages": []
    },
    "modules": [
      {
        "model": "APPLE SSD AP0512Z",
        "manufacturer": "Apple",
        "identifier": "disk0",
        "location": "Internal",
        "connector": "Apple Fabric",
        "type": "Solid State Drive (SSD)",
        "vendor_id": null,
        "device_id": null,
        "size": {
          "capacity": 477102,
          "unit": "MB"
        }
      },
      {
        "model": "Built In SDXC Reader",
        "manufacturer": "Apple",
        "identifier": null,
        "location": "Internal",
        "connector": "Secure Digital",
        "type": "Unknown",
        "vendor_id": null,
        "device_id": null,
        "size": null
      }
    ]
  },
  "graphics": {
    "status": {
      "type": "success",
      "messages": []
    },
    "modules": [
      {
        "name": "Apple M3 Pro",
        "vendor_id": "0x106b",
        "device_id": null,
        "manufacturer": "Apple Inc.",
        "subsystem_manufacturer": null,
        "subsystem_model": null,
        "acpi_path": null,
        "pci_path": null,
        "pcie_width": null,
        "pcie_gen": null,
        "vram": {
          "capacity": 18432,
          "unit": "MB"
        },
        "apple_gpu_info": {
          "gpu_core_count": 20,
          "performance_shader_count": 8,
          "gpu_gen": 15
        }
      }
    ]
  },
  "network": {
    "status": {
      "type": "success",
      "messages": []
    },
    "modules": [
      {
        "name": "Ethernet Adapter (en4)",
        "device_id": null,
        "vendor_id": null,
        "acpi_path": null,
        "pci_path": null,
        "manufacturer": null,
        "interface": "en4",
        "mac_address": "XX:XX:XX:XX:XX:XX",
        "type": "Ethernet",
        "ip_address": null
      },
      {
        "name": "Wi-Fi",
        "device_id": "0x4434",
        "vendor_id": "0x14e4",
        "acpi_path": null,
        "pci_path": null,
        "manufacturer": "Apple",
        "interface": "en0",
        "mac_address": "XX:XX:XX:XX:XX:XX",
        "type": "AirPort",
        "ip_address": "10.200.185.18"
      }
    ]
  }
}
```

</details>

## Hardware Discovery Progress Tracker

| Component   | Linux | macOS  | Windows |
|-------------|:-----:|:------:|:-------:|
| CPU         |   ✅        |   ✅    |    ✅    |
| GPU         |   ✅        |   ✅    |    ✅    |
| Memory      |   ✅* (3)   |   ✅    |    ✅    |
| Network     |   ✅        |   ✅    |    ✅    |
| Storage     |   ✅        |   ✅    |    ✅    | 
| Display     |   ✅        | ❌* (1) | ✅* (2)  |
| Audio       |   ❌        |   ❌    | ✅* (2)  |
| Motherboard |   ❌        |   ❌    |    ✅    |
| Vendor      |   ❌        |   ❌    |    ➖    |
| Input       |   ❌        |   ❌    |    ❌    |

1. In progress
2. Need to rewrite C++ bindings (In progress)
3. HWProbe doesn't directly interact with `/sys/firmware/dmi/entries/17-*`, 
the user is encouraged to satisfy the data acquisition contract via the `DMIProvider` interface.

### Miscellaneous Tasks

| Task                                                                  | Status |
|-----------------------------------------------------------------------|:------:|
| Pending components                                                    |   ❌    |
| Autodetection of storage units                                        |   ❌    |
| PCI Lookup — [PCI IDs Repository](https://github.com/pciutils/pciids) |   ✅    |

## Building Native Components (optional)

Linux, macOS, and Windows each have an optional native C++ accelerator under `src/hwprobe/interops/<platform>/`
that HWProbe uses automatically when present, falling back to pure-Python/subprocess-based detection otherwise.
See each platform's README for build instructions and requirements:

- [Linux](src/hwprobe/interops/linux/README.md)
- [macOS](src/hwprobe/interops/mac/README.md)
- [Windows](src/hwprobe/interops/win/README.md)

## Credits

There are so many people that helped with developing this library, directly or indirectly.

<details>
<summary>Thank you to these people for bringing HWProbe to the shape it currently is in.</summary>

- [kernel-dev](https://github.com/kernel-dev) for OCSysInfo
- People who helped with testing the myriad of hardware combinations:
    - [AjaxR0](https://github.com/AjaxR0)
    - [Andrupka](https://github.com/Andrupka)
    - [chrisdodgers](https://github.com/chrisdodgers)
    - [Dids](https://github.com/dids)
    - [PJFrye](https://github.com/PJFrye)
    - So many more people, you know who you are, thank you so much!

</details>