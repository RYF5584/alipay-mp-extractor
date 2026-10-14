"""Discover and identify packages inside a synced device dump.

Dump layout (created by :meth:`AlipayMPExtractor.sync`)::

    <dump>/
      <SandboxHash>/database/ccdn/caches/app/data/<md5>/0.dc   business apps+plugins
      nebulaApp/<appId>/<ver>/<appId>.tar                      legacy apps
      nebulaInstallApps/<appId>/<md5>/...                      framework packages
      *.db                                                     container sqlite dbs
"""

from __future__ import annotations

import json
import re
import sqlite3
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from .models import FrameworkPackage, MiniApp, PluginInfo

APP_TABLE = "nebulax_resource_app_table"
PLUGIN_TABLE = "nebulax_resource_plugin_table"


# ------------------------------------------------------------------ helpers

def iter_dc_packages(dump: Path) -> List[Path]:
    if not dump.exists():
        return []
    return sorted(dump.glob("*/database/ccdn/caches/app/data/*/0.dc"))


def iter_legacy_tars(dump: Path) -> List[Path]:
    if not dump.exists():
        return []
    return [p for p in dump.glob("nebulaApp/*/*/*.tar") if p.stem.isdigit()]


def tar_member_appid(pkg: Path) -> Optional[str]:
    """appId = first all-digit ``*.tar`` member of the package."""
    try:
        with tarfile.open(str(pkg)) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".tar"):
                    stem = Path(m.name).name[:-4]
                    if stem.isdigit():
                        return stem
    except (tarfile.TarError, OSError):
        pass
    return None


def _clean(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "_"


# ------------------------------------------------------------------ dbs

def load_app_meta(dump: Path) -> Dict[str, dict]:
    """appId -> {name, version, package_url} from container dbs."""
    meta: Dict[str, dict] = {}
    for db in sorted(dump.glob("*.db")) if dump.exists() else []:
        try:
            con = sqlite3.connect(str(db))
            rows = con.execute(
                f"SELECT app_id, name, version, package_url FROM {APP_TABLE}"
            ).fetchall()
            for app_id, name, version, url in rows:
                cur = meta.setdefault(
                    str(app_id), {"name": None, "version": None, "package_url": None}
                )
                cur["name"] = cur["name"] or name
                cur["version"] = cur["version"] or version
                cur["package_url"] = cur["package_url"] or url
            con.close()
        except sqlite3.Error:
            continue
    return meta


def load_plugins(dump: Path) -> Dict[str, PluginInfo]:
    """provider -> PluginInfo from the plugin resource table."""
    plugins: Dict[str, PluginInfo] = {}
    for db in sorted(dump.glob("*.db")) if dump.exists() else []:
        try:
            con = sqlite3.connect(str(db))
            rows = con.execute(
                f"SELECT app_id, developerVersion, version, newPackageUrl, packageUrl "
                f"FROM {PLUGIN_TABLE}"
            ).fetchall()
            for app_id, dev_ver, version, new_url, url in rows:
                info = plugins.setdefault(
                    str(app_id),
                    PluginInfo(provider=str(app_id)),
                )
                info.version = info.version if info.version != "?" else (version or "?")
                info.developer_version = dev_ver or "?"
                info.package_url = info.package_url or new_url or url
            con.close()
        except sqlite3.Error:
            continue
    return plugins


# ------------------------------------------------------------------ framework

def scan_framework(dump: Path) -> List[FrameworkPackage]:
    out = []
    for d in sorted(dump.glob("nebulaInstallApps/*/*")) if dump.exists() else []:
        manifest = d / "Manifest.xml"
        if not manifest.exists():
            continue
        name = version = app_version = "?"
        try:
            root = ET.parse(str(manifest)).getroot()
            vals = {c.tag: (c.text or "").strip() for c in root}
            name = vals.get("name", "?")
            version = vals.get("version", "?")
            app_version = vals.get("appVersion", "?")
        except ET.ParseError:
            pass
        out.append(
            FrameworkPackage(
                app_id=d.parent.name,
                name=name,
                version=version,
                app_version=app_version,
                manifest_dir=d,
            )
        )
    return out


# ------------------------------------------------------------------ apps

def _read_declared_plugins(src: Path) -> List[dict]:
    """['alias': .., 'provider': ..] from appConfig.json plugins section."""
    cfg = src / "appConfig.json"
    if not cfg.exists():
        return []
    try:
        data = json.loads(cfg.read_text(errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return []
    return _plugins_of(data)


def _plugins_of(data: dict) -> List[dict]:
    out = []
    for alias, decl in (data.get("plugins") or {}).items():
        if isinstance(decl, dict):
            out.append(
                {
                    "alias": alias,
                    "provider": str(decl.get("provider", "")),
                    "version": str(decl.get("version", "*")),
                }
            )
    return out


def peek_appconfig(pkg: Path) -> Optional[dict]:
    """Read ``appConfig.json`` from inside a package (outer+inner tar)
    without unpacking it to disk."""
    try:
        with tarfile.open(str(pkg)) as outer:
            for m in outer.getmembers():
                if not (m.isfile() and m.name.endswith(".tar")):
                    continue
                if not Path(m.name).stem.isdigit():
                    continue
                inner_io = outer.extractfile(m)
                if inner_io is None:
                    continue
                with tarfile.open(fileobj=inner_io) as inner:
                    for im in inner.getmembers():
                        if im.name == "appConfig.json":
                            f = inner.extractfile(im)
                            if f:
                                return json.loads(f.read())
    except (tarfile.TarError, json.JSONDecodeError, OSError, EOFError):
        return None
    return None


def scan_apps(dump: Path, plugin_index: Optional[Dict[str, PluginInfo]] = None) -> Dict[str, MiniApp]:
    """Discover every business package (apps AND plugins share the same cache)."""
    apps: Dict[str, MiniApp] = {}
    meta = load_app_meta(dump)
    plugins_tbl = plugin_index if plugin_index is not None else load_plugins(dump)

    def register(app_id: str, pkg: Path) -> None:
        info = apps.get(app_id)
        if info is None:
            m = meta.get(app_id, {})
            pl = plugins_tbl.get(app_id)
            info = apps[app_id] = MiniApp(
                app_id=app_id,
                name=m.get("name") or "?",
                version=m.get("version") or (pl.developer_version if pl else "?"),
                package_url=m.get("package_url") or (pl.package_url if pl else None),
                kind="plugin" if app_id in plugins_tbl else "app",
            )
        if info.package_file is None or pkg.stat().st_size > info.package_file.stat().st_size:
            info.package_file = pkg
        info.size = max(info.size, pkg.stat().st_size)

    for dc in iter_dc_packages(dump):
        app_id = tar_member_appid(dc)
        if app_id:
            register(app_id, dc)
    for tar in iter_legacy_tars(dump):
        register(tar.stem, tar)

    # peek appConfig.json in every package: declared plugins, without unpacking
    for app in apps.values():
        if app.package_file is not None:
            cfg = peek_appconfig(app.package_file)
            if cfg:
                app.plugins = _plugins_of(cfg)
                title = (cfg.get("window") or {}).get("defaultTitle")
                if title and app.name == "?":
                    app.name = title

    # link host apps -> plugin usage
    for app in apps.values():
        for decl in app.plugins:
            info = plugins_tbl.get(decl["provider"])
            if info is not None:
                info.used_by.append(f"{app.display_name}:{decl['alias']}")

    return apps


def enrich_from_src(app: MiniApp, src: Path, plugin_index: Dict[str, PluginInfo]) -> None:
    """Fill pages/declared-plugin info after ``src`` has been unpacked."""
    cfg = src / "appConfig.json"
    meta = src / "meta.json"
    app.plugins = _read_declared_plugins(src)
    for decl in app.plugins:
        info = plugin_index.get(decl["provider"])
        if info is not None:
            info.used_by.append(f"{app.display_name}:{decl['alias']}")
    try:
        pages = json.loads(meta.read_text(errors="ignore")).get("pages", {}) if meta.exists() else {}
        app.pages = sorted(pages)
    except (json.JSONDecodeError, OSError):
        pass
    if app.name == "?":
        try:
            data = json.loads(cfg.read_text(errors="ignore"))
            title = (data.get("window") or {}).get("defaultTitle")
            if title:
                app.name = title
        except (json.JSONDecodeError, OSError):
            pass


def clean_name(s: str) -> str:
    """Filesystem-safe directory name from an app name."""
    return _clean(s)


def display_dirname(app_id: str, name: str, duplicate: bool) -> str:
    """Directory name for an exported app: the human name, disambiguated
    with the appId only when a *different* app shares the same name."""
    base = _clean(name) if name and name != "?" else app_id
    if base == app_id or base == "_":
        return app_id
    return f"{base}_{app_id}" if duplicate else base
