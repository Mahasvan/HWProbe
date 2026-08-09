.. _supported:

--------------------
Supported Components
--------------------

As of this version, HWProbe supports retrieving info from the following components
via the aggregate :func:`fetch_hardware_info` call, on Linux, macOS, and Windows:

- CPU
- GPU
- Memory
- Network
- Storage

The following components are implemented but must be fetched individually (they are not
yet part of the aggregate ``fetch_hardware_info()`` call on every platform):

- Display (``fetch_display_info()``) — Linux, macOS, Windows
- Audio (``fetch_audio_info()``) — Windows only
- Motherboard/Baseboard (``fetch_baseboard_info()``) — Windows only

.. note::

   On Linux, :func:`fetch_memory_info` requires a ``DMIProvider`` to supply raw SMBIOS
   Type 17 data (the library never reads ``/sys/firmware/dmi`` itself). See
   :ref:`linux-memory-concept` for details.

To get started, visit :ref:`quickstart`.

Attributes gathered for each component are listed in the component's schema,
in the :ref:`models` section.