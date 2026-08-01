#ifndef HW_HELPER_HPP
#define HW_HELPER_HPP

#include <cstdint>

// Chasis type mapping based on SMBIOS Chassis Type field
static const char *CHASSIS_TYPE_MAPPING[0x100u] =
    {
        "Reserved",              /* 00h */
        "Other",                 /* 01h */
        "Unknown",               /* 02h */
        "Desktop",               /* 03h */
        "Low Profile Desktop",   /* 04h */
        "Pizza Box",             /* 05h */
        "Mini Tower",            /* 06h */
        "Tower",                 /* 07h */
        "Portable",              /* 08h */
        "Laptop",                /* 09h */
        "Notebook",              /* 0Ah */
        "Hand Held",             /* 0Bh */
        "Docking Station",       /* 0Ch */
        "All-in-One",            /* 0Dh */
        "Sub Notebook",          /* 0Eh */
        "Space-Saving",          /* 0Fh */
        "Lunch Box",             /* 10h */
        "Main Server Chassis",   /* 11h */
        "Expansion Chassis",     /* 12h */
        "SubChassis",            /* 13h */
        "Bus Expansion Chassis", /* 14h */
        "Peripheral Chassis",    /* 15h */
        "RAID Chassis",          /* 16h */
        "Rack Mount Chassis",    /* 17h */
        "Sealed-Case PC",        /* 18h */
        "Multi-System Chassis",  /* 19h */
        "Compact PCI",           /* 1Ah */
        "AdvancedTCA",           /* 1Bh */
        "Blade",                 /* 1Ch */
        "Blade Enclosure",       /* 1Dh */
        "Tablet",                /* 1Eh */
        "Convertible",           /* 1Fh */
        "Detachable",            /* 20h */
        "IoT Gateway",           /* 21h */
        "Embedded PC",           /* 22h */
        "Mini PC",               /* 23h */
        "Stick PC",              /* 24h */
                                 /* 25h - FFh => UNKNOWN */
};

// Socket type mapping based on SMBIOS Processor Upgrade field
static const char *PROCESSOR_UPGRADE_MAPPING[0x100u] = {
    "Reserved",               /* 00h */
    "Other",                  /* 01h */
    "Unknown",                /* 02h */
    "Daughter Board",         /* 03h */
    "ZIF Socket",             /* 04h */
    "Replaceable Piggy Back", /* 05h */
    "None",                   /* 06h */
    "LIF Socket",             /* 07h */
    "Slot 1",                 /* 08h */
    "Slot 2",                 /* 09h */
    "370-pin Socket",         /* 0Ah */
    "Slot A",                 /* 0Bh */
    "Slot M",                 /* 0Ch */
    "Socket 423",             /* 0Dh */
    "Socket A (Socket 462)",  /* 0Eh */
    "Socket 478",             /* 0Fh */
    "Socket 754",             /* 10h */
    "Socket 940",             /* 11h */
    "Socket 939",             /* 12h */
    "Socket mPGA604",         /* 13h */
    "Socket LGA771",          /* 14h */
    "Socket LGA775",          /* 15h */
    "Socket S1",              /* 16h */
    "Socket AM2",             /* 17h */
    "Socket F (1207)",        /* 18h */
    "Socket LGA1366",         /* 19h */
    "Socket G34",             /* 1Ah */
    "Socket AM3",             /* 1Bh */
    "Socket C32",             /* 1Ch */
    "Socket LGA1156",         /* 1Dh */
    "Socket LGA1567",         /* 1Eh */
    "Socket PGA988A",         /* 1Fh */
    "Socket BGA1288",         /* 20h */
    "Socket rPGA988B",        /* 21h */
    "Socket BGA1023",         /* 22h */
    "Socket BGA1224",         /* 23h */
    "Socket LGA1155",         /* 24h */
    "Socket LGA1356",         /* 25h */
    "Socket LGA2011",         /* 26h */
    "Socket FS1",             /* 27h */
    "Socket FS2",             /* 28h */
    "Socket FM1",             /* 29h */
    "Socket FM2",             /* 2Ah */
    "Socket LGA2011-3",       /* 2Bh */
    "Socket LGA1356-3",       /* 2Ch */
    "Socket LGA1150",         /* 2Dh */
    "Socket BGA1168",         /* 2Eh */
    "Socket BGA1234",         /* 2Fh */
    "Socket BGA1364",         /* 30h */
    "Socket AM4",             /* 31h */
    "Socket LGA1151",         /* 32h */
    "Socket BGA1356",         /* 33h */
    "Socket BGA1440",         /* 34h */
    "Socket BGA1515",         /* 35h */
    "Socket LGA3647-1",       /* 36h */
    "Socket SP3",             /* 37h */
    "Socket SP3r2",           /* 38h */
    "Socket LGA2066",         /* 39h */
    "Socket BGA1392",         /* 3Ah */
    "Socket BGA1510",         /* 3Bh */
    "Socket BGA1528",         /* 3Ch */
    "Socket LGA4189",         /* 3Dh */
    "Socket LGA1200",         /* 3Eh */
    "Socket LGA4677",         /* 3Fh */
    "Socket LGA1700",         /* 40h */
    "Socket BGA1744",         /* 41h */
    "Socket BGA1781",         /* 42h */
    "Socket BGA1211",         /* 43h */
    "Socket BGA2422",         /* 44h */
    "Socket LGA1211",         /* 45h */
    "Socket LGA2422",         /* 46h */
    "Socket LGA5773",         /* 47h */
    "Socket BGA5773",         /* 48h */
    "Socket AM5",             /* 49h */
    "Socket SP5",             /* 4Ah */
    "Socket SP6",             /* 4Bh */
    "Socket BGA883",          /* 4Ch */
    "Socket BGA1190",         /* 4Dh */
    "Socket BGA4129",         /* 4Eh */
    "Socket LGA4710",         /* 4Fh */
    "Socket LGA7529",         /* 50h */
    "Socket BGA1964",         /* 51h */
    "Socket BGA1792",         /* 52h */
    "Socket BGA2049",         /* 53h */
    "Socket BGA2551",         /* 54h */
    "Socket LGA1851",         /* 55h */
    "Socket BGA2114",         /* 56h */
    "Socket BGA2833",         /* 57h */
    /* 58h - FFh => UNKNOWN */
};

#pragma pack(push, 1)
struct SMBIOSHeader
{
    uint8_t Type;
    uint8_t Length;
    uint16_t Handle;
};

struct SMBIOSBaseboard
{
    SMBIOSHeader H;
    uint8_t Manufacturer;
    uint8_t Product;
    uint8_t Version;
    uint8_t Serial;
};

struct SMBIOSChassis
{
    SMBIOSHeader H;
    uint8_t Manufacturer;
    uint8_t ChassisType;
};

struct SMBIOSProcessor
{
    SMBIOSHeader H;                    // 0x00-0x03
    uint8_t SocketDesignation;         // 0x04
    uint8_t ProcessorType;             // 0x05
    uint8_t ProcessorFamily;           // 0x06
    uint8_t Manufacturer;              // 0x07
    uint32_t ProcessorID;              // 0x08-0x0B
    uint8_t Version;                   // 0x0C-0x0D
    uint8_t Voltage;                   // 0x0E
    uint16_t ExternalClock;            // 0x0F-0x10
    uint16_t MaxSpeed;                 // 0x11-0x12
    uint16_t CurrentSpeed;             // 0x13-0x14
    uint8_t Status;                    // 0x15
    uint8_t ProcessorUpgrade;          // 0x16
    uint16_t L1CacheHandle;            // 0x17-0x18
    uint16_t L2CacheHandle;            // 0x19-0x1A
    uint16_t L3CacheHandle;            // 0x1B-0x1C
    uint8_t SerialNumber;              // 0x1D
    uint8_t AssetTag;                  // 0x1E
    uint8_t PartNumber;                // 0x1F
    uint8_t CoreCount;                 // 0x20
    uint8_t CoreEnabled;               // 0x21
    uint8_t ThreadCount;               // 0x22
    uint16_t ProcessorCharacteristics; // 0x23-0x24
    uint16_t ProcessorFamily2;         // 0x25-0x26
    uint16_t CoreCount2;               // 0x27-0x28
    uint16_t CoreEnabled2;             // 0x29-0x2A
    uint16_t ThreadCount2;             // 0x2B-0x2C
    uint16_t ThreadEnabled;            // 0x30-0x31
    uint8_t SocketType;                // 0x32 - Additional socket type string (SMBIOS 3.6+)
};
#pragma pack(pop)

struct SMBIOSHwInfo
{
    char motherboardManufacturer[256];
    char motherboardModel[256];
    char chassisType[256];
    char cpuSocket[256];
};

typedef enum gpuHelper_Result_ENUM
{
    STATUS_OK = 0u,
    STATUS_NOK,
    STATUS_INVALID_ARG,
    STATUS_FAILURE
} HardwareHelper_RESULT;

#endif /* hw_helper.hpp */