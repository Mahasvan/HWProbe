import ctypes

# todo: refactor to new bindings
from hwprobe.interops.win.legacy.constants import STATUS_OK
from hwprobe.interops.win.legacy.signatures import GetAudioHardwareInfo
from hwprobe.models.audio_models import (
    AudioControllerInfo,
    AudioDeviceInfo,
    AudioInfo,
)
from hwprobe.models.status_models import Status, StatusType


def fetch_audio_info_fast() -> AudioInfo:
    audio_info = AudioInfo(status=Status(type=StatusType.SUCCESS))

    # 512 bytes per property, ~15 properties, ~10 devices
    buf_size = 512 * 15 * 10
    raw_data = ctypes.create_string_buffer(buf_size)

    res = GetAudioHardwareInfo(raw_data, buf_size)

    # the method couldn't execute successfully
    if res != STATUS_OK:
        audio_info.status.type = StatusType.FAILED
        audio_info.status.messages.append(f"Audio HW info query failed with status code: {res}")
        return audio_info

    decoded = raw_data.value.decode("utf-8", errors="ignore").strip()

    # data is empty
    if not decoded:
        audio_info.status.type = StatusType.FAILED
        audio_info.status.messages.append("Audio HW info query returned no data")
        return audio_info

    current_hardware = None

    for line in decoded.split("\n"):
        if not line or "|" not in line:
            continue

        parsed = dict(x.split("=", 1) for x in line.split("|") if "=" in x)
        device_type = parsed.get("Type")

        """
        Device types can be "Hardware" (audio controller) or "Endpoint" (audio device)
        We group endpoints under their parent hardware controller.
        """
        if device_type == "Hardware":
            if current_hardware:
                audio_info.modules.append(current_hardware)

            current_hardware = AudioControllerInfo()
            current_hardware.name = parsed.get("Name", "Unknown")
            current_hardware.manufacturer = parsed.get("Manufacturer", "Unknown")
            current_hardware.pnp_device_id = parsed.get("PNPDeviceID", "")

        elif device_type == "Endpoint" and current_hardware:
            endpoint = AudioDeviceInfo()
            endpoint.name = parsed.get("Name", "Unknown")
            endpoint.data_flow = parsed.get("DataFlow", "Unknown")
            endpoint.parent_pnp_device_id = parsed.get("ParentPNPDeviceID", "")
            current_hardware.endpoints.append(endpoint)

    # don't forget last device
    if current_hardware:
        audio_info.modules.append(current_hardware)

    return audio_info
