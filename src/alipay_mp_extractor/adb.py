"""ADB transport: adbutils primary, system ``adb`` binary as fallback.

Supports USB devices (pinned by serial), network devices (``adb connect``)
and a remote adb server. Device reads stream ``su -c tar`` output as bytes,
so only root is required.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from typing import List, Optional, Tuple

from .errors import (
    AdbServerUnavailableError,
    DeviceNotFoundError,
    NoDeviceError,
    RootRequiredError,
)

DEFAULT_ADB_HOST = "127.0.0.1"
DEFAULT_ADB_PORT = 5037
DEFAULT_TIMEOUT = 300

SYSTEM_ADB_CANDIDATES = ("adb", "/usr/bin/adb", "/opt/homebrew/bin/adb", "/usr/local/bin/adb")


def _adb_binary() -> Optional[str]:
    for cand in SYSTEM_ADB_CANDIDATES:
        path = shutil.which(cand)
        if path:
            return path
    return None


class AdbTransport:
    """Uniform adb access with automatic backend fallback.

    backend: ``auto`` (adbutils, fallback to system adb) | ``adbutils`` | ``system``.
    """

    def __init__(
        self,
        serial: Optional[str] = None,
        connect: Optional[str] = None,
        adb_host: str = DEFAULT_ADB_HOST,
        adb_port: int = DEFAULT_ADB_PORT,
        timeout: int = DEFAULT_TIMEOUT,
        backend: str = "auto",
    ) -> None:
        self.serial = serial
        self.connect = connect
        self.adb_host = adb_host
        self.adb_port = adb_port
        self.timeout = timeout
        self.backend = backend
        self.fallback_reason: Optional[str] = None
        self._client = None
        self._device = None

    # ------------------------------------------------------------ system adb

    def _system_base(self) -> List[str]:
        adb = _adb_binary()
        if adb is None:
            raise AdbServerUnavailableError(
                host=self.adb_host, port=self.adb_port, detail="adb binary not on PATH"
            )
        cmd = [adb]
        remote_server = not (
            self.adb_host in ("127.0.0.1", "localhost") and self.adb_port == 5037
        )
        if remote_server:
            cmd += ["-H", self.adb_host, "-P", str(self.adb_port)]
        if self.serial and not self.connect:
            cmd += ["-s", self.serial]
        return cmd

    def _shell_system(self, cmd: str, timeout: int) -> bytes:
        p = subprocess.run(
            self._system_base() + ["exec-out", cmd],
            capture_output=True,
            timeout=timeout,
        )
        return p.stdout

    # ------------------------------------------------------------- adbutils

    def _client_adbutils(self):
        if self._client is None:
            try:
                import adbutils
            except ImportError as e:
                raise AdbServerUnavailableError(
                    host=self.adb_host, port=self.adb_port, detail=f"adbutils: {e}"
                )
            self._client = adbutils.AdbClient(host=self.adb_host, port=self.adb_port)
        return self._client

    def _device_adbutils(self):
        if self._device is None:
            client = self._client_adbutils()
            if self.connect:
                try:
                    client.connect(self.connect, timeout=10.0)
                except Exception as e:
                    raise AdbServerUnavailableError(
                        host=self.adb_host, port=self.adb_port,
                        detail=f"adb connect {self.connect}: {e}",
                    )
                serial = self.connect
            else:
                serial = self.serial
            if serial:
                if serial not in [s for s, _ in self.devices()]:
                    raise DeviceNotFoundError(serial=serial, known=self._known_str())
                self._device = client.device(serial, timeout=self.timeout)
            else:
                devs = [d for d in client.device_list() if d.serial]
                if not devs:
                    raise NoDeviceError()
                self._device = devs[0]
        return self._device

    def _shell_adbutils(self, cmd: str, timeout: int) -> bytes:
        return self._device_adbutils().shell(
            cmd, encoding=None, rstrip=False, timeout=timeout
        )

    # -------------------------------------------------------------- public

    def _known_str(self) -> str:
        try:
            return ", ".join(s for s, _ in self.devices()) or "-"
        except Exception:
            return "-"

    def _try(self, cmd: str, timeout: int) -> bytes:
        """Run via selected backend(s); ``auto`` falls back to system adb."""
        order = {
            "auto": ("adbutils", "system"),
            "adbutils": ("adbutils",),
            "system": ("system",),
        }[self.backend]
        last: Optional[BaseException] = None
        for i, backend in enumerate(order):
            try:
                out = (
                    self._shell_adbutils(cmd, timeout)
                    if backend == "adbutils"
                    else self._shell_system(cmd, timeout)
                )
                if backend == "system" and i > 0:
                    self.fallback_reason = repr(last)
                return out
            except (AdbServerUnavailableError, DeviceNotFoundError, NoDeviceError):
                raise  # deterministic: do not mask with a fallback
            except Exception as e:  # transient: try next backend
                last = e
        raise AdbServerUnavailableError(
            host=self.adb_host, port=self.adb_port, detail=last
        )

    def shell(self, cmd: str, timeout: Optional[int] = None) -> bytes:
        """Run a shell command on the device; returns raw bytes."""
        return self._try(cmd, timeout or self.timeout)

    def shell_text(self, cmd: str, timeout: Optional[int] = None) -> str:
        """Run a shell command, returning decoded text."""
        return self.shell(cmd, timeout).decode("utf-8", errors="ignore")

    def devices(self) -> List[Tuple[str, str]]:
        """[(serial, state)] visible to the adb server."""
        try:
            out = []
            for d in self._client_adbutils().device_list():
                try:
                    state = d.get_state()
                except Exception:
                    state = "device"
                out.append((d.serial, state))
            return out
        except Exception:
            p = subprocess.run(
                self._system_base() + ["devices"], capture_output=True, timeout=10
            )
            devs = []
            for line in p.stdout.decode(errors="ignore").splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    devs.append((parts[0], parts[1]))
            return devs

    def has_root(self) -> bool:
        try:
            return b"uid=0" in self.shell("su -c id", timeout=20)
        except Exception:
            return False

    def require_root(self) -> None:
        if not self.has_root():
            raise RootRequiredError()

    def pull_tar(self, cd: str, rels: str, timeout: Optional[int] = None) -> bytes:
        """Stream ``cd/rels`` (shell globs allowed) as an in-memory tar."""
        return self.shell(
            f"su -c 'cd {cd} && tar -cf - {rels} 2>/dev/null'", timeout
        )

    def pull_tar_members(self, cd: str, rels: str, dest_root) -> int:
        """Pull ``cd/rels`` and extract members under ``dest_root``; 0 if empty."""
        from .errors import TarCorruptError
        from .unpack import extract_tar_stream

        data = self.pull_tar(cd, rels)
        if not data:
            return 0
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                return extract_tar_stream(tf, dest_root)
        except tarfile.TarError as e:
            raise TarCorruptError(detail=e)
