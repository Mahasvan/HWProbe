import ctypes

from hwprobe.interops.win.legacy.structs import GUID

# Win32 General Constants
ENUM_CURRENT_SETTINGS = -1
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
DICS_FLAG_GLOBAL = 0x00000001
DIREG_DEV = 0x00000001
KEY_READ = 0x20019
REG_BINARY = 3

# Orientation values
DMDO_DEFAULT = 0  # Landscape
DMDO_90 = 1  # Portrait
DMDO_180 = 2  # Landscape (flipped)
DMDO_270 = 3  # Portrait (flipped)

GUID_DEVCLASS_MONITOR = GUID(
    0x4D36E96E,
    0xE325,
    0x11CE,
    (ctypes.c_ubyte * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18),
)

GUID_DEVINTERFACE_MONITOR = GUID(
    0xE6F07B5F,
    0xEE97,
    0x4A90,
    (ctypes.c_ubyte * 8)(0xB0, 0x76, 0x33, 0xF5, 0x7B, 0xF4, 0xEA, 0xA7),
)

# GPU Helper Status Codes
STATUS_OK = 0
STATUS_NOK = 1
STATUS_INVALID_ARG = 2
STATUS_FAILURE = 3

# ECC Types for Memory Modules
ECC_RESERVED = 0
ECC_OTHER = 1
ECC_UNKNOWN = 2
ECC_NONE = 3
ECC_PARITY = 4
ECC_SINGLE_BIT = 5
ECC_MULTI_BIT = 6
ECC_CRC = 7
