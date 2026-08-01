from hwprobe.models.display_models import DisplayModuleInfo, ResolutionInfo

BIT_DEPTH_ENUM = {
    1: 6,
    2: 8,
    3: 10,
    4: 12,
    5: 14,
    6: 16
}

INTERFACE_ENUM = {
    0: "Undefined",
    1: "DVI",
    2: "HDMI",  # Standard HDMI-A
    3: "HDMI (B)",
    4: "MDDI",
    5: "DisplayPort"
}

DESCRIPTOR_TAG_ENUM = {
    0xFF: "Serial Number",
    0xFE: "Alphanumeric Data String",
    0xFC: "Display Product Name",
}


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


def parse_edid(edid_data: bytes) -> DisplayModuleInfo:
    # todo: Parse EDID v1.2 and v1.3. This will work for v1.4, but need to verify on the older versions.
    module = DisplayModuleInfo()

    edid_version = (edid_data[0x12], edid_data[0x13])

    module.year = edid_data[0x11] + 1990

    manuf_bits = int.from_bytes(edid_data[0x08:0x0A], byteorder="big")
    char1 = chr(((manuf_bits >> 10) & 0x1F) + 64)
    char2 = chr(((manuf_bits >> 5) & 0x1F) + 64)
    char3 = chr((manuf_bits & 0x1F) + 64)
    manuf_string = char1 + char2 + char3

    module.manufacturer_code = manuf_string

    product_code = edid_data[0x0A:0x0C].hex().upper()

    id_serial_number = "0x" + edid_data[0x0C:0x10].hex().upper()

    input_type = edid_data[0x14]
    module.resolution = ResolutionInfo()

    if input_type >> 7 == 1:  # MSB is 1 => Digital output
        if edid_version >= (1, 4):
            module.resolution.bit_depth = BIT_DEPTH_ENUM.get(
                _get_bits(input_type.to_bytes(1, byteorder="little"), 1, 4),
                0)
            module.interface = INTERFACE_ENUM.get(input_type & 7, "Unknown")
    else:
        module.interface = "Analog"

    resolution = (0, 0, 0)  # Width, Height, Refresh Rate
    # We will use this tuple to find the max resolution and refresh rate, and update it in `module.resolution`.

    for block_start in range(0x36, 0x6d, 18):
        block = edid_data[block_start:block_start + 18]
        if block[:2] == b"\x00\x00":
            tag = block[3]
            if tag in DESCRIPTOR_TAG_ENUM:
                # Refer to DESCRIPTOR_TAG_ENUM for valid block type codes
                if tag == 0xFF:
                    # todo: test if this works
                    module.serial_number = block[5:].decode("ascii").strip()
                elif tag == 0xFC:
                    module.name = block[5:].decode("ascii").strip()

        else:
            if not module.resolution: continue

            pixel_clock_hz = (block[0] | (block[1] << 8)) * 10_000

            horiz = ((block[4] & 0xF0) << 4) | block[2]
            vert = ((block[7] & 0xF0) << 4) | block[5]

            h_blank = ((block[4] & 0x0F) << 8) | block[3]
            v_blank = ((block[7] & 0x0F) << 8) | block[6]
            refresh_rate = pixel_clock_hz / ((horiz + h_blank) * (vert + v_blank))

            resolution = max(
                resolution,
                (horiz, vert, round(refresh_rate, 2)),
                key=lambda x: (x[0] * x[1], x[2])
            )

    if resolution != (0, 0, 0):
        if not module.resolution:
            module.resolution = ResolutionInfo()
        module.resolution.width = resolution[0]
        module.resolution.height = resolution[1]
        module.resolution.refresh_rate = resolution[2]

    # print("\nRaw EDID:")
    # for byte in edid_data:
    #     print(f"{byte:02X}", end=" ")

    return module

# todo: parse extension blocks