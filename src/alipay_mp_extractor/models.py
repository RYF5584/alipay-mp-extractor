"""Data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MiniApp:
    """A mini-program (or plugin) package discovered on the device."""

    app_id: str
    name: str = "?"
    version: str = "?"
    size: int = 0
    kind: str = "app"  # "app" | "plugin" | "unknown"
    package_file: Optional[Path] = None
    device_path: Optional[str] = None  # on-device dc path (light sync)
    package_url: Optional[str] = None
    plugins: List[Dict[str, str]] = field(default_factory=list)  # declared deps
    pages: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name if self.name != "?" else self.app_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "size": self.size,
            "package_file": str(self.package_file) if self.package_file else None,
            "package_url": self.package_url,
            "plugins": self.plugins,
            "pages": self.pages,
        }


@dataclass
class PluginInfo:
    """An entry from the container's plugin resource table."""

    provider: str
    version: str = "?"
    developer_version: str = "?"
    package_url: Optional[str] = None
    package_file: Optional[Path] = None
    used_by: List[str] = field(default_factory=list)  # aliases in host apps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "version": self.version,
            "developer_version": self.developer_version,
            "package_url": self.package_url,
            "package_file": str(self.package_file) if self.package_file else None,
            "used_by": self.used_by,
        }


@dataclass
class FrameworkPackage:
    """An official runtime/framework package (nebulaInstallApps)."""

    app_id: str
    name: str = "?"
    version: str = "?"
    app_version: str = "?"
    manifest_dir: Optional[Path] = None
    device_dir: Optional[str] = None  # on-device nebulaInstallApps/<appId>/<md5>

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "app_version": self.app_version,
            "manifest_dir": str(self.manifest_dir) if self.manifest_dir else None,
        }
