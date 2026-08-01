.. _querying-info:

=============
Querying Info
=============

Accessing Retrieved Data
------------------------

There are two equivalent ways to access retrieved data.

**Option 1: Use the return value directly.**

.. code-block:: python

   import hwprobe

   hm = hwprobe.HardwareManager()
   info = hm.fetch_hardware_info()

   print(info.cpu.name)
   print(info.cpu.architecture)
   print(info.cpu.vendor)

.. code-block:: shell

   Apple M3
   ARM
   Apple

**Option 2: Use the** ``info`` **attribute on the manager.**

Calling any ``fetch_*`` method populates the ``info`` attribute, so previously
fetched data remains accessible without re-querying.

.. code-block:: python

   import hwprobe

   hm = hwprobe.HardwareManager()

   hm.fetch_cpu_info()
   print("CPU Name:", hm.info.cpu.name)

   hm.fetch_storage_info()
   print("Found", len(hm.info.storage.disks), "disks")

   # CPU data is still available
   print("CPU Manufacturer:", hm.info.cpu.vendor)

.. code-block:: shell

   CPU Name: Apple M3
   Found 1 disks
   CPU Manufacturer: Apple

Both approaches return the same objects:

.. code-block:: python

   info = hm.fetch_hardware_info()
   print(hm.info == info)         # True
   print(hm.info.cpu == info.cpu) # True


Working with Collections
------------------------

Components like storage and graphics contain lists of devices:

.. code-block:: python

   import hwprobe

   hm = hwprobe.HardwareManager()
   storage = hm.fetch_storage_info()

   print("Found", len(storage.disks), "storage devices")
   for disk in storage.disks:
       print("Name:", disk.model)
       print("Size:", disk.size.capacity, disk.size.unit)

.. code-block:: shell

   Found 1 storage devices
   Name: APPLE SSD AP0512Z
   Size: 477102 MB


.. _errors-during-hardware-discovery:

Error Handling
--------------

Every component has a ``status`` property indicating whether errors occurred
during discovery.

.. code-block:: python

   import hwprobe

   hm = hwprobe.HardwareManager()
   hm.fetch_hardware_info()

   print("CPU:", hm.info.cpu.status.type)
   print("Graphics:", hm.info.graphics.status.type)
   print("Storage:", hm.info.storage.status.type)

.. code-block:: shell

   CPU: StatusType.SUCCESS
   Graphics: StatusType.SUCCESS
   Storage: StatusType.SUCCESS

The ``status`` property has the following structure:

.. autoclass:: hwprobe.models.status_models.Status
    :members:
    :exclude-members: model_config
    :no-index:

The ``type`` attribute is one of three values:

.. autoclass:: hwprobe.models.status_models.StatusType
    :members:
    :no-index:

Here is an example of handling partial and fatal errors:

.. code-block:: python

   import hwprobe
   from hwprobe.models.status_models import StatusType

   hm = hwprobe.HardwareManager()
   cpu = hm.fetch_cpu_info()

   if cpu.status.type == StatusType.FAILED:
       print("Fatal issue(s) occurred:")
       for message in cpu.status.messages:
           print(message)
       exit(1)

   elif cpu.status.type == StatusType.PARTIAL:
       print("Partial error(s) occurred:")
       for message in cpu.status.messages:
           print(message)
       print(cpu.name)

   else:
       print("Success:", cpu.name)

.. code-block:: shell

   Success: Apple M3
