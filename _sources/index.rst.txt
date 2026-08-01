.. HWProbe documentation master file

---------
HWProbe
---------

HWProbe is a Python library that gathers info about system components, such as the
CPU, memory, storage, and graphics, across Linux, macOS, and Windows.

========
Features
========

- Consistent structure on all platforms, using `Pydantic models <https://docs.pydantic.dev/latest/concepts/models/>`_.
- Usage stays the same everywhere, with no need for code changes across platforms.
- Supports data retrieval as Class objects, Python dictionaries, or JSON-parsable strings.
- For a list of supported hardware components, refer to :ref:`supported`.

=======
Install
=======

**Prerequisites:** Python 3.9 or newer.

.. code-block:: bash

   pip install HWProbe

=============
Quick Example
=============

.. code-block:: python

   from hwprobe import HardwareManager

   manager = HardwareManager()
   hardware = manager.fetch_hardware_info()
   print(hardware.model_dump_json(indent=2))

--------

========
Contents
========

.. toctree::
   :maxdepth: 2

   quickstart
   querying_info
   supported
   models
