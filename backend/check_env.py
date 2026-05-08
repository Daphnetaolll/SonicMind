from __future__ import annotations

import importlib
import sys


def _version(module_name: str) -> str:
    # This checker imports heavy semantic packages only when the script is run intentionally.
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return "not installed"
    return str(getattr(module, "__version__", "ok"))


print("Python:", sys.version)
for dependency in ("transformers", "faiss", "sentence_transformers", "torch"):
    print(f"{dependency}: {_version(dependency)}")
print("ENV CHECK COMPLETE")
