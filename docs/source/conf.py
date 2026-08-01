import sys
from pathlib import Path

sys.path.insert(0, str(Path("..", "src").resolve()))

# Mock platform-specific dependencies so autodoc works off-host
autodoc_mock_imports = []

if sys.platform != "win32":
    autodoc_mock_imports += [
        "winreg",
        "hwprobe.interops.win",
        "hwprobe.core.windows.audio",
        "hwprobe.core.windows.baseboard",
        "hwprobe.core.windows.common",
        "hwprobe.core.windows.cpu",
        "hwprobe.core.windows.display",
        "hwprobe.core.windows.graphics",
        "hwprobe.core.windows.memory",
        "hwprobe.core.windows.network",
        "hwprobe.core.windows.storage",
        "hwprobe.core.windows.win_enum",
    ]

if sys.platform != "darwin":
    autodoc_mock_imports += ["objc", "CoreFoundation", "Foundation", "PyObjCTools"]

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information


import hwprobe

project = "HWProbe"
copyright = "2025, Mahasvan Mohan"
author = "Mahasvan Mohan"
release = hwprobe.__version__

autodoc_class_signature = "separated"
add_module_names = False
# python_use_unqualified_type_names = True

autodoc_pydantic_model_show_json = False
autodoc_pydantic_settings_show_json = False
autoclass_content = "class"

autodoc_default_options = {
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__, __init___",
}

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinxcontrib.autodoc_pydantic",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]
