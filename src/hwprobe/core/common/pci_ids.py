"""
PCI-IDS parser and lookup utility.

Parses the standard pci.ids file (as shipped by the `hwdata` package on most
Linux distributions) into a structured dictionary, and provides a lookup
function to resolve vendor/device/subsystem IDs to human-readable names.

The pci.ids file format:
    - Vendor:    ^<4-hex vendor_id>  <vendor_name>
    - Device:    ^\t<4-hex device_id>  <device_name>
    - Subsystem: ^\t\t<4-hex subvendor_id> <4-hex subdevice_id>  <subsystem_name>
    - Comments start with '#', blank lines are ignored.
    - Device classes follow after a 'C <class_id>' line (not parsed here).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

# Common locations where distros install pci.ids
_PCI_IDS_SEARCH_PATHS = [
    "/usr/share/hwdata/pci.ids",
    "/usr/share/misc/pci.ids",
    "/usr/local/share/hwdata/pci.ids",
    "/usr/share/pci.ids",
]

_VENDOR_RE = re.compile(r"^([0-9a-fA-F]{4})\s{2}(.+)$")
_DEVICE_RE = re.compile(r"^\t([0-9a-fA-F]{4})\s{2}(.+)$")
_SUBSYSTEM_RE = re.compile(r"^\t\t([0-9a-fA-F]{4})\s([0-9a-fA-F]{4})\s{2}(.+)$")

# Module-level cache so we only parse once per process
_pci_ids_cache: Optional[Dict] = None


@dataclass
class PCILookupResult:
    """Result of a PCI-IDS lookup."""

    vendor_id: str
    device_id: str
    vendor_name: Optional[str] = None
    device_name: Optional[str] = None
    subsystem_name: Optional[str] = None


def find_pci_ids_file() -> Optional[str]:
    """Locate the system's pci.ids file."""
    for path in _PCI_IDS_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return None


def parse_pci_ids(path: Optional[str] = None) -> Dict:
    """
    Parse a pci.ids file into a nested dictionary structure.

    Returns a dict shaped like:
    {
        "<vendor_id>": {
            "name": "<vendor_name>",
            "devices": {
                "<device_id>": {
                    "name": "<device_name>",
                    "subsystems": {
                        "<subvendor_id>:<subdevice_id>": "<subsystem_name>",
                        ...
                    }
                },
                ...
            }
        },
        ...
    }

    Vendor and device IDs are stored in lowercase hex (no '0x' prefix).
    """
    if path is None:
        path = find_pci_ids_file()
    if path is None:
        raise FileNotFoundError(
            "Could not locate pci.ids. Searched: " + ", ".join(_PCI_IDS_SEARCH_PATHS)
        )

    result: Dict = {}
    current_vendor: Optional[str] = None
    current_device: Optional[str] = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            # Stop at device classes section — we only care about vendors/devices
            if line.startswith("C "):
                break

            # Skip comments and blank lines
            if line.startswith("#") or line.strip() == "":
                continue

            # Try subsystem first (most indented)
            m = _SUBSYSTEM_RE.match(line)
            if m and current_vendor and current_device:
                subvendor = m.group(1).lower()
                subdevice = m.group(2).lower()
                subsystem_name = m.group(3).strip()
                key = f"{subvendor}:{subdevice}"
                result[current_vendor]["devices"][current_device]["subsystems"][key] = subsystem_name
                continue

            # Try device
            m = _DEVICE_RE.match(line)
            if m and current_vendor:
                current_device = m.group(1).lower()
                device_name = m.group(2).strip()
                result[current_vendor]["devices"][current_device] = {
                    "name": device_name,
                    "subsystems": {},
                }
                continue

            # Try vendor
            m = _VENDOR_RE.match(line)
            if m:
                current_vendor = m.group(1).lower()
                vendor_name = m.group(2).strip()
                current_device = None
                result[current_vendor] = {
                    "name": vendor_name,
                    "devices": {},
                }
                continue

    return result


def parse_pci_ids_to_json(path: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """
    Parse pci.ids and return the result as a JSON string.

    If `output_path` is provided, also writes the JSON to that file.
    """
    if _pci_ids_cache is not None:
        data = _pci_ids_cache
    else:
        data = parse_pci_ids(path)
    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str


def _get_db(path: Optional[str] = None) -> Dict:
    """Return the parsed PCI-IDS database, using a module-level cache."""
    global _pci_ids_cache
    if _pci_ids_cache is None:
        _pci_ids_cache = parse_pci_ids(path)
    return _pci_ids_cache


def _normalize_id(raw: str) -> str:
    """Normalize a PCI ID string to lowercase 4-char hex without '0x' prefix."""
    raw = raw.strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    return raw.zfill(4)


def _scan_lookup(
    path: str, vid: str, did: str, svid: Optional[str], sdid: Optional[str]
) -> PCILookupResult:
    """
    Single-pass scan for one vendor/device/subsystem combo, without building
    the full ~40k-line database into memory.

    pci.ids lists vendors in ascending hex order, so we can stop as soon as
    we've moved past the target vendor's block (or past where it would be).
    """
    result = PCILookupResult(vendor_id=vid, device_id=did)
    vid_int = int(vid, 16)

    in_target_vendor = False
    in_target_device = False

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("C "):
                break  # device-class section; nothing left to find

            if line.startswith("#") or line.strip() == "":
                continue  # comments/blank lines appear inside vendor blocks too

            if not line.startswith("\t"):
                if in_target_vendor:
                    break  # past our vendor's block; nothing more to find
                m = _VENDOR_RE.match(line)
                if not m:
                    continue
                line_vid = m.group(1).lower()
                if line_vid == vid:
                    result.vendor_name = m.group(2).strip()
                    in_target_vendor = True
                elif int(line_vid, 16) > vid_int:
                    break  # sorted ascending; vendor doesn't exist
                continue

            if not in_target_vendor:
                continue  # skip devices/subsystems of vendors we don't need

            if line.startswith("\t\t"):
                if not in_target_device or not svid or not sdid:
                    continue
                m = _SUBSYSTEM_RE.match(line)
                if m and m.group(1).lower() == svid and m.group(2).lower() == sdid:
                    result.subsystem_name = m.group(3).strip()
                continue

            if in_target_device:
                break  # past our target device's subsystem lines

            m = _DEVICE_RE.match(line)
            if m and m.group(1).lower() == did:
                result.device_name = m.group(2).strip()
                in_target_device = True
                if not (svid and sdid):
                    break  # nothing more needed from this vendor block

    return result


def lookup(
    vendor_id: str,
    device_id: str,
    subvendor_id: Optional[str] = None,
    subdevice_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> PCILookupResult:
    """
    Look up a PCI vendor+device (and optionally subsystem) by their IDs.

    IDs can be passed with or without '0x' prefix.

    Returns a PCILookupResult with whatever names were found.
    """
    vid = _normalize_id(vendor_id)
    did = _normalize_id(device_id)
    svid = _normalize_id(subvendor_id) if subvendor_id else None
    sdid = _normalize_id(subdevice_id) if subdevice_id else None

    # A cached full parse (e.g. from a prior parse_pci_ids_to_json call) is
    # already in memory — reuse it instead of re-scanning the file.
    if _pci_ids_cache is not None:
        result = PCILookupResult(vendor_id=vid, device_id=did)
        vendor_entry = _pci_ids_cache.get(vid)
        if vendor_entry is None:
            return result
        result.vendor_name = vendor_entry["name"]
        device_entry = vendor_entry["devices"].get(did)
        if device_entry is None:
            return result
        result.device_name = device_entry["name"]
        if svid and sdid:
            result.subsystem_name = device_entry["subsystems"].get(f"{svid}:{sdid}")
        return result

    path = db_path if db_path is not None else find_pci_ids_file()
    if path is None:
        raise FileNotFoundError(
            "Could not locate pci.ids. Searched: " + ", ".join(_PCI_IDS_SEARCH_PATHS)
        )

    return _scan_lookup(path, vid, did, svid, sdid)
