import re

pciroot_re = re.compile(r"PCIROOT\((\d+)\)")
pciusb_re = re.compile(r"(PCI|USB)\(([0-9A-Fa-f]+)\)")
acpiusb_re = re.compile(r"(ACPI|USB)\(([^)]+)\)")


def format_acpi_path(raw_path: str) -> str:
    if not raw_path:
        return None

    segments = acpiusb_re.findall(raw_path)

    if not segments:
        return raw_path

    return "\\" + ".".join(seg[1] for seg in segments)


def format_pci_path(raw_path: str) -> str:
    if not raw_path:
        return None

    segments = raw_path.split("#")
    formatted_parts = []

    for seg in segments:
        root_match = pciroot_re.match(seg)
        if root_match:
            val = int(root_match.group(1))
            formatted_parts.append(f"PciRoot(0x{val:X})")
            continue

        pci_match = pciusb_re.match(seg)
        if pci_match:
            full_val = int(pci_match.group(2), 16)
            device = full_val >> 8
            function = full_val & 0xFF
            prefix = pci_match.group(1)
            formatted_parts.append(f"{prefix[0].upper() + prefix[1:].lower()}(0x{device:X},0x{function:X})")

    return "/".join(formatted_parts)
