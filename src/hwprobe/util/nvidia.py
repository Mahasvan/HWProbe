import subprocess


def fetch_gpu_details_nvidia(device: str) -> tuple[str, int, int, int]:
    """
    :param device: format: <domain>:<bus>:<slot>.<function>
    :return: GPU name, PCI Width, PCI Gen, Total VRAM in MB
    """
    # Combine all queries into a single comma-separated string
    # Fields: Name, PCIe Width, PCIe Gen, Memory Total
    # Use the ".max" variants (card capability) rather than ".current" (instantaneous
    # link state), since PCIe ASPM downclocks idle GPUs and ".current" would report
    # whatever speed/width the link happens to be negotiating at query time.
    query_fields = "name,pcie.link.width.max,pcie.link.gen.max,memory.total"

    command = ["nvidia-smi", f"--id={device}", f"--query-gpu={query_fields}", "--format=csv,noheader,nounits"]

    # Run the command
    result = subprocess.run(command, capture_output=True, text=True)

    # Check for execution errors
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi failed: {result.stderr}")

    # Parse output (Expected: "Name, Width, Gen, Memory")
    output = result.stdout.strip()
    parts = output.split(",")

    # Validate we got exactly 4 fields back
    if len(parts) != 4:
        raise ValueError(f"Unexpected output format from nvidia-smi: {output}")

    # Parse and Type Convert
    gpu_name = parts[0].strip()
    try:
        pci_width = int(parts[1].strip())  # e.g., 16
        pci_gen = int(parts[2].strip())  # e.g., 3, 4, or 5
        vram_total = int(parts[3].strip())  # e.g., 16384 (MiB)
    except ValueError as e:
        raise ValueError(f"Unexpected output format from nvidia-smi: {output}") from e

    return gpu_name, pci_width, pci_gen, vram_total
