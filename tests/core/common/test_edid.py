from typing import Optional

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


def _build_cta_detailed_timing_descriptor(
    width=1920,
    height=1080,
    h_blank=280,
    v_blank=45,
    pixel_clock_10khz=14850,
):
    """Create a valid 18-byte CTA/EDID detailed timing descriptor."""
    descriptor = bytearray(18)
    descriptor[0] = pixel_clock_10khz & 0xFF
    descriptor[1] = (pixel_clock_10khz >> 8) & 0xFF
    descriptor[2] = width & 0xFF
    descriptor[3] = h_blank & 0xFF
    descriptor[4] = ((width >> 8) & 0x0F) << 4 | ((h_blank >> 8) & 0x0F)
    descriptor[5] = height & 0xFF
    descriptor[6] = v_blank & 0xFF
    descriptor[7] = ((height >> 8) & 0x0F) << 4 | ((v_blank >> 8) & 0x0F)
    return bytes(descriptor)


def _build_cta_extension(dtd: bytes) -> bytes:
    """Build a CTA-861 extension block with the DTD starting at byte offset 4."""
    ext = bytearray(128)
    ext[0] = 0x02
    ext[1] = 0x03
    ext[2] = 0x04
    ext[4 : 4 + len(dtd)] = dtd
    return bytes(ext)


def _build_displayid_type_i_timing_entry(
    width=1920,
    height=1080,
    h_blank=280,
    v_blank=45,
    pixel_clock_10khz=14850,
):
    """Build a 20-byte DisplayID Type-I timing entry using the actual-1 encoding."""
    entry = bytearray(20)
    entry[0:3] = (pixel_clock_10khz - 1).to_bytes(3, byteorder="little")
    entry[4:6] = (width - 1).to_bytes(2, byteorder="little")
    entry[6:8] = (h_blank - 1).to_bytes(2, byteorder="little")
    entry[8:10] = b"\x00\x00"
    entry[10:12] = b"\x00\x00"
    entry[12:14] = (height - 1).to_bytes(2, byteorder="little")
    entry[14:16] = (v_blank - 1).to_bytes(2, byteorder="little")
    entry[16:20] = b"\x00\x00\x00\x00"
    return bytes(entry)


def _build_displayid_extension(payload: bytes, *, section_size: Optional[int] = None, truncated: bool = False) -> bytes:
    """Build a DisplayID extension block with a Type-I timing payload.

    If truncated is True, the payload length is longer than the advertised section size
    to ensure the parser must stop before overrunning the extension boundary.
    """
    ext = bytearray(128)
    ext[0] = 0x70
    ext[1] = 0x01
    ext[2] = section_size if section_size is not None else 5 + len(payload)
    ext[3] = 0x00
    ext[4] = 0x00

    if truncated:
        ext[5] = 0x03
        ext[6] = 0x01
        ext[7] = 0x20
    else:
        ext[5] = 0x03
        ext[6] = 0x01
        ext[7] = len(payload)
        ext[8 : 8 + len(payload)] = payload

    return bytes(ext)


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


class TestEdidExtensionFixtures:
    def test_parse_edid_reads_cta_dtd_from_extension(self):
        dtd = _build_cta_detailed_timing_descriptor()
        cta_ext = _build_cta_extension(dtd)

        edid = bytearray(128 * 2)
        edid[0x7E] = 1
        edid[128 : 128 + 128] = cta_ext

        result = parse_edid(bytes(edid))

        assert result.resolution.width == 1920
        assert result.resolution.height == 1080
        assert result.resolution.refresh_rate == 60.0

    def test_parse_edid_reads_displayid_type_i_timing(self):
        entry = _build_displayid_type_i_timing_entry()
        displayid_ext = _build_displayid_extension(entry)

        edid = bytearray(128 * 2)
        edid[0x7E] = 1
        edid[128 : 128 + 128] = displayid_ext

        result = parse_edid(bytes(edid))

        assert result.resolution.width == 1920
        assert result.resolution.height == 1080
        assert result.resolution.refresh_rate == 60.0

    def test_parse_edid_handles_truncated_displayid_payload(self):
        entry = _build_displayid_type_i_timing_entry()
        displayid_ext = _build_displayid_extension(entry, section_size=25, truncated=True)

        edid = bytearray(128 * 2)
        edid[0x7E] = 1
        edid[128 : 128 + 128] = displayid_ext

        result = parse_edid(bytes(edid))

        assert result.resolution.width is None
        assert result.resolution.height is None
        assert result.resolution.refresh_rate is None
