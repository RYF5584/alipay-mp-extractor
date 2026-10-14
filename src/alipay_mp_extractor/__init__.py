"""alipay_mp_extractor - Alipay(Android) mini-program package extractor & decompiler.

Public API::

    from alipay_mp_extractor import AlipayMPExtractor

    mp = AlipayMPExtractor()                 # USB device (first one) via local adb server
    mp.sync()                       # pull packages from device
    mp.list()                       # -> list[MiniApp]
    mp.search("<name>")             # -> list[MiniApp]
    mp.query("<appId>")             # -> MiniApp
    mp.export("<name>")             # -> Path (unpacked + decompiled)
"""

from __future__ import annotations

from .client import AlipayMPExtractor
from .errors import (
    AdbServerUnavailableError,
    AlipayMPError,
    AmbiguousKeyError,
    AppNotFoundError,
    DeviceNotFoundError,
    NoDeviceError,
    PackageParseError,
    PullError,
    RootRequiredError,
)
from .i18n import set_lang
from .models import FrameworkPackage, MiniApp, PluginInfo

try:
    from importlib.metadata import version as _metadata_version

    __version__ = _metadata_version("alipay-mp-extractor")
except Exception:  # package not installed (e.g. running from a checkout)
    __version__ = "1.2.1"

__all__ = [
    "AlipayMPExtractor",
    "MiniApp",
    "PluginInfo",
    "FrameworkPackage",
    "AlipayMPError",
    "AdbServerUnavailableError",
    "DeviceNotFoundError",
    "NoDeviceError",
    "RootRequiredError",
    "PullError",
    "PackageParseError",
    "AppNotFoundError",
    "AmbiguousKeyError",
    "set_lang",
    "__version__",
]
