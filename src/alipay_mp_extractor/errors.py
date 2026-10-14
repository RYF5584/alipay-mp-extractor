"""Typed errors with i18n messages; CLI turns these into friendly output."""

from __future__ import annotations

from typing import Optional

from .i18n import t


class AlipayMPError(Exception):
    """Base error. ``key`` is an i18n message key, ``kw`` its parameters."""

    key = "err.generic"

    def __init__(self, key: Optional[str] = None, **kw) -> None:
        self.key = key or self.key
        self.kw = kw
        super().__init__(t(self.key, **kw))


class AdbServerUnavailableError(AlipayMPError):
    key = "err.adb_server"


class DeviceNotFoundError(AlipayMPError):
    key = "err.device_not_found"


class NoDeviceError(AlipayMPError):
    key = "err.no_device"


class RootRequiredError(AlipayMPError):
    key = "err.root_required"


class PullError(AlipayMPError):
    key = "err.pull"


class TarCorruptError(AlipayMPError):
    key = "err.tar_corrupt"


class PackageParseError(AlipayMPError):
    key = "err.pkg_parse"


class DatabaseParseError(AlipayMPError):
    key = "err.db_parse"


class AppNotFoundError(AlipayMPError):
    key = "err.app_not_found"


class AmbiguousKeyError(AlipayMPError):
    key = "err.ambiguous"
