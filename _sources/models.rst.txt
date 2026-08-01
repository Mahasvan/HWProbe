.. _models:

------
Models
------

HWProbe exposes Pydantic models for each hardware subsystem plus shared helpers for capacity units and discovery status.


================
Component Models
================

The Model for each component, such as CPU and GPU are subclasses of the ``ComponentInfo`` class.

.. autoclass:: hwprobe.models.component_model.ComponentInfo
    :members:
    :exclude-members: model_config


All the following models include the ``status`` property, even though it is not shown
explicitly.


CPU
===

the information retrieved about the CPU is stored as the following class.

.. autopydantic_model:: hwprobe.models.cpu_models.CPUInfo
    :show-inheritance:
    :inherited-members: ComponentInfo
    :exclude-members: __init__
    :model-show-field-summary: False

---------

GPU
===

Since there may be multiple GPUs present, the output for :meth:`fetch_graphics_info() <hwprobe.models.info_models.HardwareManagerInterface.fetch_graphics_info>`
is a ``GraphicsInfo`` object, with the ``modules`` property containing a list of ``GPUInfo`` objects.

------

.. autopydantic_model:: hwprobe.models.gpu_models.GraphicsInfo
    :show-inheritance:
    :inherited-members: ComponentInfo
    :exclude-members: __init__
    :model-show-field-summary: False

--------

.. autopydantic_model:: hwprobe.models.gpu_models.GPUInfo
    :exclude-members: __init__
    :model-show-field-summary: False

---------

.. autopydantic_model:: hwprobe.models.gpu_models.AppleExtendedGPUInfo
    :exclude-members: __init__
    :model-show-field-summary: False

---------

Memory
======

When :meth:`fetch_memory_info() <hwprobe.models.info_models.HardwareManagerInterface.fetch_memory_info>` is queried,
a :class:`MemoryInfo <hwprobe.models.memory_models.MemoryInfo>` object is returned.

Similar to GPUs, the details of all RAM devices are stored as a list of
:class:`MemoryModuleInfo <hwprobe.models.memory_models.MemoryModuleInfo>` objects,
in the ``modules`` property.

The RAM slot is stored in the ``slot`` property, as a
:class:`MemoryModuleSlot <hwprobe.models.memory_models.MemoryModuleSlot>` object.

--------

.. autopydantic_model:: hwprobe.models.memory_models.MemoryInfo
    :exclude-members: __init__
    :model-show-field-summary: False

--------

.. autopydantic_model:: hwprobe.models.memory_models.MemoryModuleInfo
    :exclude-members: __init__
    :model-show-field-summary: False

--------

.. autopydantic_model:: hwprobe.models.memory_models.MemoryModuleSlot
    :exclude-members: __init__
    :model-show-field-summary: False

--------

Storage
=======

When :meth:`fetch_memory_info() <hwprobe.models.info_models.HardwareManagerInterface.fetch_storage_info>`
is queried, a :class:`StorageInfo <hwprobe.models.storage_models.StorageInfo>` object is returned.

Like GPU and RAM devices, Storage devices are stored as a list of
:class:`DiskInfo <hwprobe.models.storage_models.DiskInfo>` objects in the ``modules`` property.

------

.. autopydantic_model:: hwprobe.models.storage_models.StorageInfo
    :exclude-members: __init__
    :model-show-field-summary: False

------

.. autopydantic_model:: hwprobe.models.storage_models.DiskInfo
    :exclude-members: __init__
    :model-show-field-summary: False


=============
Status Models
=============

Every component's :class:`ComponentInfo <hwprobe.models.component_model.ComponentInfo>` subclass has
a :attr:`status <hwprobe.models.component_model.ComponentInfo.status>` property,
which contains information on the errors encountered while retrieving data.

This property will be of the :class:`Status <hwprobe.models.status_models.Status>` class.

---------

.. autopydantic_model:: hwprobe.models.status_models.Status
    :exclude-members: __init__
    :model-show-field-summary: False

---------

The ``type`` property of the status indicates whether there were errors during the discovery process.

This is an Enum, with three possible values.

.. autoclass:: hwprobe.models.status_models.StatusType
    :members:


=============
Size Models
=============

Capacities, such as the size of a RAM module, or the storage capacity of a Storage Disk,
is expressed as one of the subclasses of the
:class:`StorageSize <hwprobe.models.size_models.StorageSize>` class.


.. autopydantic_model:: hwprobe.models.size_models.StorageSize
    :exclude-members: __init__
    :model-show-field-summary: False

----------


Every ``size`` parameter, that is of type ``StorageSize``, will of be one of the following classes.

----------

.. autopydantic_model:: hwprobe.models.size_models.Kilobyte
    :exclude-members: __init__
    :model-show-field-summary: False

----------

.. autopydantic_model:: hwprobe.models.size_models.Megabyte
    :exclude-members: __init__
    :model-show-field-summary: False

----------

.. autopydantic_model:: hwprobe.models.size_models.Gigabyte
    :exclude-members: __init__
    :model-show-field-summary: False

