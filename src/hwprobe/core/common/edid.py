from typing import Optional

from hwprobe.models.display_models import DisplayModuleInfo, ResolutionInfo

BIT_DEPTH_ENUM = {1: 6, 2: 8, 3: 10, 4: 12, 5: 14, 6: 16}

INTERFACE_ENUM = {
    0: "Undefined",
    1: "DVI",
    2: "HDMI",  # Standard HDMI-A
    3: "HDMI (B)",
    4: "MDDI",
    5: "DisplayPort",
}

DESCRIPTOR_TAG_ENUM = {
    0xFF: "Serial Number",
    0xFE: "Alphanumeric Data String",
    0xFC: "Display Product Name",
}

CTA_EXTENSION_TAG = 0x02
DISPLAYID_EXTENSION_TAG = 0x70
DISPLAYID_TYPE_I_TIMING_TAG = 0x03

# (width, height, refresh_rate)
ResolutionCandidate = tuple[int, int, float]
_NO_RESOLUTION: ResolutionCandidate = (0, 0, 0)


def _get_bits(data: bytes, start_bit: int, end_bit: int) -> int:
    # Get the bit values in an offset, given a bytes object.

    if start_bit < 0 or end_bit <= start_bit:
        raise ValueError("Invalid bit range")

    total_bits = len(data) * 8
    if end_bit > total_bits:
        raise ValueError("Bit range exceeds data length")

    # Convert bytes to integer
    value = int.from_bytes(data, byteorder="big")

    # Number of bits to extract
    length = end_bit - start_bit

    # Shift right to drop lower bits, then mask
    shift = total_bits - end_bit
    return (value >> shift) & ((1 << length) - 1)


def _detailed_timing(descriptor: bytes) -> Optional[ResolutionCandidate]:
    # Parse an 18-byte EDID Detailed Timing Descriptor into (width, height, refresh_rate).
    # Returns None if this slot isn't a timing descriptor (e.g. all-zero padding/tag block).
    if len(descriptor) < 18 or descriptor[:2] == b"\x00\x00":
        return None

    pixel_clock_hz = (descriptor[0] | (descriptor[1] << 8)) * 10_000

    horiz = ((descriptor[4] & 0xF0) << 4) | descriptor[2]
    vert = ((descriptor[7] & 0xF0) << 4) | descriptor[5]

    h_blank = ((descriptor[4] & 0x0F) << 8) | descriptor[3]
    v_blank = ((descriptor[7] & 0x0F) << 8) | descriptor[6]

    total_h = horiz + h_blank
    total_v = vert + v_blank
    if total_h == 0 or total_v == 0:
        return None

    refresh_rate = pixel_clock_hz / (total_h * total_v)
    return horiz, vert, round(refresh_rate, 2)


def _type_i_timing(entry: bytes) -> Optional[ResolutionCandidate]:
    # Parse a 20-byte DisplayID Type I Timing entry into (width, height, refresh_rate).
    # Layout verified byte-for-byte against a real DisplayID extension block: pixel clock
    # is a 24-bit LE value in units of 10 kHz (stored as actual-1), and active/blank pixel
    # counts are 16-bit LE (also stored as actual-1) - unlike the base/CTA DTD format.
    if len(entry) < 20:
        return None

    pixel_clock_hz = ((entry[0] | (entry[1] << 8) | (entry[2] << 16)) + 1) * 10_000

    h_active = (entry[4] | (entry[5] << 8)) + 1
    h_blank = (entry[6] | (entry[7] << 8)) + 1
    v_active = (entry[12] | (entry[13] << 8)) + 1
    v_blank = (entry[14] | (entry[15] << 8)) + 1

    total_h = h_active + h_blank
    total_v = v_active + v_blank
    if total_h == 0 or total_v == 0:
        return None

    refresh_rate = pixel_clock_hz / (total_h * total_v)
    return h_active, v_active, round(refresh_rate, 2)


def _better_resolution(
    current: ResolutionCandidate, candidate: Optional[ResolutionCandidate]
) -> ResolutionCandidate:
    """Keep whichever of current/candidate has the larger area, breaking ties on refresh rate."""
    if candidate is None:
        return current
    return max(current, candidate, key=lambda r: (r[0] * r[1], r[2]))


def _parse_manufacturer_code(manuf_bytes: bytes) -> str:
    """Decode the 3-letter PNP manufacturer ID packed into bytes 0x08-0x0A (5 bits/letter, offset from 'A'-1)."""
    manuf_bits = int.from_bytes(manuf_bytes, byteorder="big")
    return "".join(chr(((manuf_bits >> shift) & 0x1F) + 64) for shift in (10, 5, 0))


def _parse_video_input(
    input_type: int, edid_version: tuple[int, int]
) -> tuple[Optional[int], Optional[str]]:
    """
    Decode the video input definition byte (offset 0x14) into (bit_depth, interface).

    Either value may come back None if it isn't determinable - this matches the original
    behavior where pre-1.4 digital displays don't report bit depth/interface here at all.
    """
    if input_type >> 7 != 1:
        return None, "Analog"

    if edid_version < (1, 4):
        return None, None

    bit_depth = BIT_DEPTH_ENUM.get(_get_bits(input_type.to_bytes(1, byteorder="little"), 1, 4), 0)
    interface = INTERFACE_ENUM.get(input_type & 7, "Unknown")
    return bit_depth, interface


def _process_display_descriptors(
    edid_data: bytes,
) -> tuple[Optional[str], Optional[str], ResolutionCandidate]:
    """
    Walk the four 18-byte descriptor blocks in the base EDID (offset 0x36-0x6C).

    Each block is either a Detailed Timing Descriptor, or a display descriptor
    (serial number / product name / other, tagged by DESCRIPTOR_TAG_ENUM).
    Returns (serial_number, name, best_resolution_found).
    """
    serial_number = None
    name = None
    resolution = _NO_RESOLUTION

    for block_start in range(0x36, 0x6D, 18):
        block = edid_data[block_start : block_start + 18]

        if block[:2] != b"\x00\x00":
            resolution = _better_resolution(resolution, _detailed_timing(block))
            continue

        tag = block[3]
        if tag == 0xFF:
            # todo: test if this works
            serial_number = block[5:].decode("ascii").strip()
        elif tag == 0xFC:
            name = block[5:].decode("ascii").strip()

    return serial_number, name, resolution


def _process_cta_extension(ext_block: bytes, resolution: ResolutionCandidate) -> ResolutionCandidate:
    """Scan a CTA-861 extension block for additional Detailed Timing Descriptors."""
    dtd_offset = ext_block[2]
    if dtd_offset < 4:
        # 0 means this extension carries no Detailed Timing Descriptors
        return resolution

    for descriptor_start in range(dtd_offset, 127, 18):
        timing = _detailed_timing(ext_block[descriptor_start : descriptor_start + 18])
        resolution = _better_resolution(resolution, timing)

    return resolution


def _process_displayid_extension(ext_block: bytes, resolution: ResolutionCandidate) -> ResolutionCandidate:
    """Scan a DisplayID extension block for Type I Timing data blocks.

    Structure: [tag, version, section_size, product_type, ext_count], followed by a
    sequence of data blocks: [tag, revision, payload_len, *payload].
    """
    section_end = min(5 + ext_block[2], 127)
    offset = 5

    while offset + 3 <= section_end:
        block_tag = ext_block[offset]
        payload_len = ext_block[offset + 2]
        payload_start = offset + 3

        if payload_start + payload_len > section_end:
            break

        if block_tag == DISPLAYID_TYPE_I_TIMING_TAG:
            for entry_start in range(payload_start, payload_start + payload_len, 20):
                timing = _type_i_timing(ext_block[entry_start : entry_start + 20])
                resolution = _better_resolution(resolution, timing)

        offset = payload_start + payload_len

    return resolution


def parse_edid(edid_data: bytes) -> DisplayModuleInfo:
    # todo: Parse EDID v1.2 and v1.3. This will work for v1.4, but need to verify on the older versions.
    if len(edid_data) < 128:
        raise ValueError(f"EDID data too short: expected at least 128 bytes, got {len(edid_data)}")

    module = DisplayModuleInfo()
    module.resolution = ResolutionInfo()

    edid_version = (edid_data[0x12], edid_data[0x13])
    module.year = edid_data[0x11] + 1990
    module.manufacturer_code = _parse_manufacturer_code(edid_data[0x08:0x0A])

    bit_depth, interface = _parse_video_input(edid_data[0x14], edid_version)
    if bit_depth is not None:
        module.resolution.bit_depth = bit_depth
    if interface is not None:
        module.interface = interface

    serial_number, name, resolution = _process_display_descriptors(edid_data)
    if serial_number is not None:
        module.serial_number = serial_number
    if name is not None:
        module.name = name

    # High-refresh-rate timings (e.g. 4K@120Hz+) are frequently declared only in a
    # CTA-861 or DisplayID extension block rather than the base 128 bytes, so scan those too.
    num_extensions = edid_data[0x7E] if len(edid_data) > 0x7E else 0
    for i in range(num_extensions):
        ext_start = 128 + i * 128
        ext_block = edid_data[ext_start : ext_start + 128]
        if len(ext_block) < 128:
            continue

        if ext_block[0] == CTA_EXTENSION_TAG:
            resolution = _process_cta_extension(ext_block, resolution)
        elif ext_block[0] == DISPLAYID_EXTENSION_TAG:
            resolution = _process_displayid_extension(ext_block, resolution)

    if resolution != _NO_RESOLUTION:
        module.resolution.width = resolution[0]
        module.resolution.height = resolution[1]
        module.resolution.refresh_rate = resolution[2]

    return module