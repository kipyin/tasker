"""Tasker — context-integrity task tracking from email and files."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tasker")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__all__ = ["__version__"]
