"""Top-level package for pyEIL."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyEIL")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Eva Maxfield Brown"
__email__ = "evamaxfieldbrown@gmail.com"

from .main import Extractor


__all__ = ["Extractor", __author__, __email__, __version__]