

from hwprobe.core.common.edid import parse_edid


def _build_edid(
    version=1,
    revision=4,
    input_byte=0x80,
    year_offset=25,
    manuf=(0x10, 0xAC),
    name=None,
    serial=None,
    timing=None,
):
    """Build a minimal 128-byte EDID block for testing.

    Args:
        version: EDID version (byte 0x12).
        revision: EDID revision (byte 0x13).
        input_byte: Video input parameters (byte 0x14).
        year_offset: Year of manufacture minus 1990 (byte 0x11).
        manuf: Two-byte manufacturer ID (bytes 0x08-0x09).
        name: Display name string for descriptor block (max 13 chars).
        serial: Serial number string for descriptor block (max 13 chars).
        timing: Tuple of (pixel_clock_10khz, h_active, h_blank, v_active, v_blank)
                for a detailed timing descriptor.
    """
    edid = bytearray(128)

    # Header
    edid[0x00:0x08] = b"\x00\xff\xff\xff\xff\xff\xff\x00"

    # Manufacturer ID
    edid[0x08] = manuf[0]
    edid[0x09] = manuf[1]

    # Product code + serial (leave as zeros)
    # edid[0x0A:0x10] already zero

    # Year
    edid[0x11] = year_offset

    # EDID version / revision
    edid[0x12] = version
    edid[0x13] = revision

    # Video input parameters
    edid[0x14] = input_byte

    # Fill the four 18-byte descriptor blocks (0x36 - 0x7D)
    desc_offset = 0x36
    descriptors_used = 0

    if timing is not None:
        pixel_clock, h_active, h_blank, v_active, v_blank = timing
        block = bytearray(18)
        block[0] = pixel_clock & 0xFF
        block[1] = (pixel_clock >> 8) & 0xFF
        block[2] = h_active & 0xFF
        block[3] = h_blank & 0xFF
        block[4] = ((h_active >> 8) & 0x0F) << 4 | ((h_blank >> 8) & 0x0F)
        block[5] = v_active & 0xFF
        block[6] = v_blank & 0xFF
        block[7] = ((v_active >> 8) & 0x0F) << 4 | ((v_blank >> 8) & 0x0F)
        edid[desc_offset : desc_offset + 18] = block
        desc_offset += 18
        descriptors_used += 1

    if name is not None:
        block = bytearray(18)
        block[0:4] = b"\x00\x00\x00\xfc"
        block[4] = 0x00
        name_bytes = name.encode("ascii")[:13]
        block[5 : 5 + len(name_bytes)] = name_bytes
        # EDID spec: terminate with 0x0A, pad remainder with 0x20
        for i in range(5 + len(name_bytes), 18):
            block[i] = 0x0A if i == 5 + len(name_bytes) else 0x20
        edid[desc_offset : desc_offset + 18] = block
        desc_offset += 18
        descriptors_used += 1

    if serial is not None:
        block = bytearray(18)
        block[0:4] = b"\x00\x00\x00\xff"
        block[4] = 0x00
        serial_bytes = serial.encode("ascii")[:13]
        block[5 : 5 + len(serial_bytes)] = serial_bytes
        for i in range(5 + len(serial_bytes), 18):
            block[i] = 0x0A if i == 5 + len(serial_bytes) else 0x20
        edid[desc_offset : desc_offset + 18] = block
        desc_offset += 18
        descriptors_used += 1

    return bytes(edid)


# Manufacturer "DEL" encoded: D=4, E=5, L=12 → (4<<10)|(5<<5)|12 = 0x10AC
_MANUF_DEL = (0x10, 0xAC)


class TestEdidVersionParsing:
    def test_v14_digital_has_bit_depth_and_interface(self):
        # 0b1_010_0101 = digital, 8-bit depth (010), DisplayPort (5)
        edid = _build_edid(version=1, revision=4, input_byte=0b10100101)
        result = parse_edid(edid)

        assert result.resolution is not None
        assert result.resolution.bit_depth == 8
        assert result.interface == "DisplayPort"

    def test_v14_digital_6bit_dvi(self):
        # 0b1_001_0001 = digital, 6-bit depth (001), DVI (1)
        edid = _build_edid(version=1, revision=4, input_byte=0b10010001)
        result = parse_edid(edid)

        assert result.resolution.bit_depth == 6
        assert result.interface == "DVI"

    def test_v14_digital_10bit_hdmi(self):
        # 0b1_011_0010 = digital, 10-bit depth (011), HDMI (2)
        edid = _build_edid(version=1, revision=4, input_byte=0b10110010)
        result = parse_edid(edid)

        assert result.resolution.bit_depth == 10
        assert result.interface == "HDMI"

    def test_v14_digital_undefined_depth(self):
        # 0b1_000_0101 = digital, undefined depth (000), DisplayPort (5)
        edid = _build_edid(version=1, revision=4, input_byte=0b10000101)
        result = parse_edid(edid)

        assert result.resolution.bit_depth == 0
        assert result.interface == "DisplayPort"

    def test_v13_digital_no_bit_depth_or_interface(self):
        # v1.3 digital: bit depth and interface fields should not be extracted
        edid = _build_edid(version=1, revision=3, input_byte=0b10100101)
        result = parse_edid(edid)

        assert result.resolution is not None
        assert result.resolution.bit_depth is None
        assert result.interface is None

    def test_v12_digital_no_bit_depth_or_interface(self):
        # v1.2 digital: same as v1.3
        edid = _build_edid(version=1, revision=2, input_byte=0b10000001)
        result = parse_edid(edid)

        assert result.resolution is not None
        assert result.resolution.bit_depth is None
        assert result.interface is None


class TestAnalogDisplay:
    def test_analog_interface_set(self):
        # bit 7 = 0 → analog
        edid = _build_edid(version=1, revision=3, input_byte=0b00000000)
        result = parse_edid(edid)

        assert result.interface == "Analog"

    def test_analog_resolution_initialized(self):
        edid = _build_edid(version=1, revision=3, input_byte=0b00000000)
        result = parse_edid(edid)

        assert result.resolution is not None

    def test_analog_no_bit_depth(self):
        edid = _build_edid(version=1, revision=3, input_byte=0b00000000)
        result = parse_edid(edid)

        assert result.resolution.bit_depth is None

    def test_analog_v14_still_analog(self):
        # Even on v1.4, bit 7 = 0 means analog
        edid = _build_edid(version=1, revision=4, input_byte=0b01100000)
        result = parse_edid(edid)

        assert result.interface == "Analog"
        assert result.resolution.bit_depth is None

    def test_analog_with_timing_gets_resolution(self):
        # 1366x768@60Hz: pixel clock = 7622 (in 10kHz units),
        # h_active=1366, h_blank=434, v_active=768, v_blank=22
        edid = _build_edid(
            version=1,
            revision=3,
            input_byte=0b00000000,
            timing=(7622, 1366, 434, 768, 22),
        )
        result = parse_edid(edid)

        assert result.resolution.width == 1366
        assert result.resolution.height == 768
        assert result.resolution.refresh_rate is not None
        assert result.resolution.refresh_rate > 0


class TestCommonFieldsAcrossVersions:
    def test_year_parsed(self):
        edid = _build_edid(year_offset=25)
        result = parse_edid(edid)
        assert result.year == 2015

    def test_manufacturer_code_parsed(self):
        edid = _build_edid(manuf=_MANUF_DEL)
        result = parse_edid(edid)
        assert result.manufacturer_code == "DEL"

    def test_display_name_parsed(self):
        edid = _build_edid(name="Test Monitor")
        result = parse_edid(edid)
        assert result.name == "Test Monitor"

    def test_serial_number_parsed(self):
        edid = _build_edid(serial="SN12345")
        result = parse_edid(edid)
        assert result.serial_number == "SN12345"

    def test_name_and_serial_both_parsed(self):
        edid = _build_edid(name="My Display", serial="ABC123")
        result = parse_edid(edid)
        assert result.name == "My Display"
        assert result.serial_number == "ABC123"
