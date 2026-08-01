.. _quickstart:

==========
Quickstart
==========

Hardware Manager
----------------

The entry point to HWProbe is the ``HardwareManager`` class.
When instantiated, it automatically selects the correct backend for your OS.

.. code-block:: python

   import hwprobe

   hm = hwprobe.HardwareManager()
   print(type(hm))

.. code-block:: shell

   <class 'hwprobe.core.mac.MacHardwareManager'>

On Linux and Windows, a ``LinuxHardwareManager`` or ``WindowsHardwareManager``
is returned instead. The API is identical regardless of platform.

All ``HardwareManager`` classes implement the following interface:

.. autoclass:: hwprobe.models.info_models.HardwareManagerInterface
    :members:
    :noindex:


Fetch Everything
----------------

Collect all hardware info in one call:

.. code-block:: python

   from hwprobe import HardwareManager

   hm = HardwareManager()
   info = hm.fetch_hardware_info()

   print(info.cpu.name)
   print(info.model_dump_json(indent=2))

Targeted Collection
-------------------

Fetch individual components when you only need one subsystem:

.. code-block:: python

   from hwprobe import HardwareManager

   hm = HardwareManager()

   cpu = hm.fetch_cpu_info()
   memory = hm.fetch_memory_info()
   storage = hm.fetch_storage_info()
   graphics = hm.fetch_graphics_info()
   network = hm.fetch_network_info()


Serialization
-------------

All component models are `Pydantic models <https://docs.pydantic.dev/latest/concepts/models/>`_,
so they support ``.model_dump()`` for dictionaries and ``.model_dump_json()`` for JSON strings.

.. code-block:: python

   from hwprobe import HardwareManager
   from pprint import pprint

   hm = HardwareManager()
   cpu = hm.fetch_cpu_info()

   # As a Python dictionary
   pprint(cpu.model_dump())

   # As a JSON string
   print(cpu.model_dump_json(indent=2))

.. code-block:: shell

   {'arch_version': '8',
    'architecture': 'ARM',
    'bitness': 64,
    'cores': 8,
    'name': 'Apple M3',
    'sse_flags': [],
    'status': {'messages': [], 'string': 'success'},
    'threads': 8,
    'vendor': 'Apple'}

The same works for ``fetch_hardware_info()`` and all other component methods.

------

Next: :ref:`querying-info`
