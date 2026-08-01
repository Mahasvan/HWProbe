# https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocessorfeaturepresent
FEATURE_ID_MAP = {
    "SSE": 6,
    "SSE2": 10,
    "SSE3": 13,
    "SSSE3": 36,
    "SSE4.1": 37,
    "SSE4.2": 38,
}

# https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ne-winioctl-storage_bus_type
BUS_TYPE = {
    0: {"type": "Unknown", "location": "Unknown"},
    1: {"type": "SCSI", "location": "Internal (Guessed)"},
    2: {"type": "ATAPI", "location": "Internal"},
    3: {"type": "ATA", "location": "Internal"},
    4: {"type": "FireWire (IEEE 1394)", "location": "Internal"},
    5: {"type": "SSA", "location": "Internal (Guessed)"},
    6: {"type": "Fibre Channel", "location": "External"},
    7: {"type": "USB", "location": "External"},
    8: {"type": "RAID", "location": "Internal"},
    9: {"type": "iSCSI", "location": "External (Network)"},
    10: {"type": "Serial Attached SCSI (SAS)", "location": "Internal"},
    11: {"type": "Serial ATA (SATA)", "location": "Internal"},
    12: {"type": "Secure Digital (SD)", "location": "External"},
    13: {"type": "Multimedia Card (MMC)", "location": "External"},
    14: {"type": "MAX (System use)", "location": "Reserved"},
    15: {"type": "File-backed Virtual", "location": "Virtual Disk"},
    16: {"type": "Storage Spaces", "location": "Internal"},
    17: {"type": "NVMe", "location": "Internal"},
    18: {"type": "Microsoft Reserved", "location": "Reserved"},
}

# https://learn.microsoft.com/en-us/windows-hardware/drivers/storage/msft-physicaldisk
MEDIA_TYPE = {
    0: "Unspecified",
    3: "Hard Disk Drive (HDD)",
    4: "Solid State Drive (SSD)",
    5: "Storage Class Memory (SCM)",
}

# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemoryarray
ECC_MEMORY_TYPE = {
    0: "Reserved",
    1: "Other",
    2: "Unknown",
    3: "None",
    4: "Parity",
    5: "Single-bit ECC",
    6: "Multi-bit ECC",
    7: "CRC",
}

# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory
MEMORY_TYPE = {
    0: "Unknown",
    1: "Other",
    2: "DRAM",
    3: "Synchronous DRAM",
    4: "Cache DRAM",
    5: "EDO",
    6: "EDRAM",
    7: "VRAM",
    8: "SRAM",
    9: "RAM",
    10: "ROM",
    11: "Flash",
    12: "EEPROM",
    13: "FEPROM",
    14: "EPROM",
    15: "CDRAM",
    16: "3DRAM",
    17: "SDRAM",
    18: "SGRAM",
    19: "RDRAM",
    20: "DDR",
    21: "DDR2",
    22: "DDR2 FB-DIMM",
    24: "DDR3",
    25: "FBD2",
    26: "DDR4",
}

# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-pointingdevice
POINT_DEV_INTERFACE = {
    1: "Other",
    2: "Unknown",
    3: "Serial",
    4: "PS/2",
    5: "Infrared",
    6: "HP-HIL",
    7: "Bus Mouse",
    8: "Apple Desktop Bus",
    160: "Bus Mouse DB-9",
    161: "Bus Mouse micro-DIN",
    162: "USB",
}

DISPLAY_CON_TYPE = {
    -1: "Other",
    0: "VGA (HD15)",
    1: "S-Video (Y/C) (Mini-DIN)",
    2: "Composite Video (CVBS)",
    3: "Component Video (RCA)",
    4: "DVI",
    5: "HDMI",
    6: "LVDS",
    8: "D Video Connector (D-Tanshi)",
    9: "SDI",
    10: "DisplayPort",
    11: "eDP",
    12: "UDI",
    13: "UDI Embedded",
    14: "SDTV Dongle",
    15: "Miracast",
    16: "Indirect Wired",
    17: "Indirect Wireless",
    18: "DisplayPort USB Type-C",
    0x80000000: "INTERNAL",
    0xFFFFFFFF: "FORCE_UINT32",
}

# https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-processor
CPU_ARCHITECTURES = {
    0: "x86",
    1: "MIPS",
    2: "Alpha",
    3: "PowerPC",
    5: "ARM",
    6: "ia64",
    9: "x64",
    12: "ARM64"
}