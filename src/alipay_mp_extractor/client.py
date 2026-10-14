"""High-level client: sync / list / search / query / export."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from .adb import (
    AdbTransport,
    DEFAULT_ADB_HOST,
    DEFAULT_ADB_PORT,
    DEFAULT_TIMEOUT,
)
from .console import Logger
from .decompile import decompile_app
from .errors import (
    AmbiguousKeyError,
    AppNotFoundError,
    PullError,
    RootRequiredError,
)
from .i18n import set_lang, t
from .models import FrameworkPackage, MiniApp, PluginInfo
from .packages import (
    clean_name,
    display_dirname,
    enrich_from_src,
    load_plugins,
    scan_apps,
    scan_framework,
)
from .unpack import unpack_package

# device paths (Alipay >= 10.x XRiver container; legacy paths probed too)
ALIPAY_PKG = "com.eg.android.AlipayGphone"
_DATA = f"/data/data/{ALIPAY_PKG}"
_SDCARD = f"/sdcard/Android/data/{ALIPAY_PKG}"

PULL_TARGETS = [
    # (description, device cd dir, tar relative paths / shell globs)
    ("business packages (ccdn cache)", f"{_DATA}/files/Sandbox", "*/database/ccdn"),
    ("legacy business packages (nebulaApp)", f"{_DATA}/files", "nebulaApp"),
    ("framework packages", f"{_DATA}/files", "nebulaInstallApps"),
    (
        "container databases",
        f"{_DATA}/databases",
        "nebula_app.db nebulax_app.db xriver_app.db "
        "aomp_mini_app_center.db open_platform_apps.db",
    ),
    ("ccdn profile", f"{_DATA}/shared_prefs", "pref_ccdn_profile.xml"),
    ("external h5 cache (legacy)", f"{_SDCARD}/files", "nebulaH5App"),
]


def _unpack_to(pkg: Path, dest: Path) -> Path:
    """Unpack a device package into ``dest/src`` (outer metadata discarded)."""
    src = unpack_package(pkg, dest / "pkg")
    shutil.move(str(src), str(dest / "src"))
    shutil.rmtree(dest / "pkg")
    return dest / "src"


@dataclass
class SyncReport:
    entries: int = 0
    targets: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"synced {self.entries} entries from {len(self.targets)} targets"


class AlipayMPExtractor:
    """Extractor & decompiler for Alipay mini-programs on a rooted device.

    Args:
        serial:     USB device serial (omit to use the first device).
        connect:    network device, e.g. ``"127.0.0.1:5555"`` (adb connect).
        adb_host / adb_port: address of the *adb server* (remote adb supported).
        backend:    ``auto`` (adbutils, fallback to system adb) | ``adbutils`` | ``system``.
        workdir:    workspace directory for the dump and exports.
        auto_sync:  run :meth:`sync` automatically when the dump is empty.
        lang:       ``'zh'`` / ``'en'``; None auto-detects (Chinese locales -> zh).
    """

    def __init__(
        self,
        serial: Optional[str] = None,
        connect: Optional[str] = None,
        adb_host: str = DEFAULT_ADB_HOST,
        adb_port: int = DEFAULT_ADB_PORT,
        timeout: int = DEFAULT_TIMEOUT,
        backend: str = "auto",
        workdir: Union[str, Path] = "./alipay_mp_workspace",
        auto_sync: bool = False,
        verbose: bool = False,
        lang: Optional[str] = None,
    ) -> None:
        set_lang(lang)
        self.workdir = Path(workdir)
        self.dump = self.workdir / "device_dump"
        self.export_root = self.workdir / "apps"
        self.log = Logger(verbose=verbose)
        self.adb = AdbTransport(
            serial=serial,
            connect=connect,
            adb_host=adb_host,
            adb_port=adb_port,
            timeout=timeout,
            backend=backend,
        )
        self._apps_cache: Optional[Dict[str, MiniApp]] = None
        self._plugins_cache: Optional[Dict[str, PluginInfo]] = None
        if auto_sync and not self._has_dump():
            self.sync()

    # -------------------------------------------------------------- internal

    def is_synced(self) -> bool:
        """True when a device dump already exists locally."""
        return self._has_dump()

    def _has_dump(self) -> bool:
        return self.dump.exists() and any(self.dump.iterdir())

    def _apps(self) -> Dict[str, MiniApp]:
        if self._apps_cache is None:
            self._apps_cache = scan_apps(self.dump, plugin_index=self._plugin_index())
        return self._apps_cache

    def _plugin_index(self) -> Dict[str, PluginInfo]:
        if self._plugins_cache is None:
            self._plugins_cache = load_plugins(self.dump)
        return self._plugins_cache

    def _resolve(self, key: str, apps: Dict[str, MiniApp]) -> MiniApp:
        """Exact appId, else unique name/alias substring match."""
        if key in apps:
            return apps[key]
        kw = key.lower()
        hits = [
            a
            for a in apps.values()
            if kw in a.name.lower()
            or any(kw in d["alias"].lower() for d in a.plugins)
        ]
        if not hits:
            raise AppNotFoundError(key=key)
        if len(hits) > 1:
            names = ", ".join(f"{h.name}({h.app_id})" for h in hits)
            raise AmbiguousKeyError(key=key, names=names)
        return hits[0]

    # -------------------------------------------------------------- sync

    def devices(self) -> List[tuple]:
        """[(serial, state)] visible to the adb server."""
        return self.adb.devices()

    def sync(self, force: bool = False) -> SyncReport:
        """Pull every package + metadata from the device (root required)."""
        if self._has_dump() and not force:
            self.log.info(t("cli.sync_skip"))
            return SyncReport()
        self.dump.mkdir(parents=True, exist_ok=True)
        # validate device reachability first, so a bad --serial does not
        # surface as a misleading root error
        self.adb.shell("true", timeout=15)
        self.adb.require_root()
        self._apps_cache = None
        self._plugins_cache = None
        report = SyncReport()
        for desc, cd, rels in PULL_TARGETS:
            self.log.info(t("cli.pull_target", desc=desc))
            try:
                n = self.adb.pull_tar_members(cd, rels, self.dump)
            except Exception as e:
                self.log.warn(t("err.pull", desc=desc, detail=e))
                continue
            if n == 0:
                self.log.info(t("cli.pull_skip"))
            report.targets.append(desc)
            report.entries += n
            self.log.debug(f"{desc}: {n} entries")
        if not report.targets:
            raise PullError("err.pull_all_failed")
        self.log.ok(t("cli.sync_done", n=report.entries, path=self.dump))
        return report

    # -------------------------------------------------------------- query

    def list(self) -> List[MiniApp]:
        """All discovered mini-programs and plugins (sorted by size desc)."""
        return sorted(self._apps().values(), key=lambda a: -a.size)

    def search(self, keyword: str) -> List[MiniApp]:
        """Substring match on name, appId, declared plugin alias or provider."""
        kw = keyword.lower()
        return [
            a
            for a in self.list()
            if kw in a.name.lower()
            or kw in a.app_id.lower()
            or any(
                kw in d["alias"].lower() or kw in d["provider"].lower()
                for d in a.plugins
            )
        ]

    def query(self, key: str) -> MiniApp:
        """Resolve one app by exact appId or (unique) name/alias substring."""
        return self._resolve(key, self._apps())

    def plugins(self) -> List[PluginInfo]:
        """All plugins known to the container (with usage info when linked)."""
        self._apps()  # trigger scan so plugin usage links are populated
        return sorted(self._plugin_index().values(), key=lambda p: p.provider)

    def framework(self) -> List[FrameworkPackage]:
        """Official runtime/framework packages found in the dump."""
        return scan_framework(self.dump)

    # -------------------------------------------------------------- export

    def export(
        self,
        key: str,
        out: Optional[Union[str, Path]] = None,
        beautify: bool = True,
        with_plugins: bool = False,
        overwrite: bool = False,
    ) -> Path:
        """Export one app: unpack + decompile, organised by subpackage.

        With ``with_plugins=True`` the plugins declared by the app are also
        exported into ``plugins/<alias>/``. Returns the export directory.
        """
        apps = self._apps()
        app = self._resolve(key, apps)
        out_root = Path(out) if out else self.export_root
        out_root.mkdir(parents=True, exist_ok=True)

        dup = any(
            other.app_id != app.app_id
            and clean_name(other.name) == clean_name(app.name)
            for other in apps.values()
        )
        dest = out_root / display_dirname(app.app_id, app.name, dup)
        if dest.exists():
            if not overwrite:
                self.log.skip(t("cli.export_skip", name=app.display_name, path=dest))
                return dest
            shutil.rmtree(dest)

        if app.package_file is None:
            from .errors import PackageParseError

            raise PackageParseError(
                path=app.app_id, detail=t("err.no_package", app_id=app.app_id)
            )
        _unpack_to(app.package_file, dest)

        plugin_index = self._plugin_index()
        enrich_from_src(app, dest / "src", plugin_index)
        decompile_app(
            dest / "src",
            dest / "decompiled",
            beautify=beautify,
            app_name=app.name,
            app_id=app.app_id,
            log=self.log,
        )
        (dest / "APPINFO.md").write_text(
            f"- appId: `{app.app_id}`\n"
            f"- name: {app.name}\n"
            f"- version: {app.version}\n"
            f"- pages: {len(app.pages)}\n"
            f"- plugins: {', '.join(d['alias'] + '->' + d['provider'] for d in app.plugins) or 'none'}\n",
            errors="ignore",
        )
        self.log.ok(
            t("cli.exported", name=app.display_name, app_id=app.app_id, path=dest)
        )

        if with_plugins and app.plugins:
            self._export_plugins(app, dest / "plugins", beautify, plugin_index, apps)
        return dest

    def _export_plugins(
        self,
        host: MiniApp,
        out: Path,
        beautify: bool,
        plugin_index: Dict[str, PluginInfo],
        apps: Dict[str, MiniApp],
    ) -> None:
        """Export every declared plugin of ``host`` into ``out/<alias>/``."""
        for decl in host.plugins:
            provider = decl["provider"]
            pkg = apps.get(provider)
            if pkg is None or pkg.package_file is None:
                self.log.warn(
                    t("cli.plugin_missing", alias=decl["alias"], provider=provider)
                )
                continue
            pdest = out / decl["alias"]
            if pdest.exists():
                continue
            _unpack_to(pkg.package_file, pdest)
            decompile_app(
                pdest / "src",
                pdest / "decompiled",
                beautify=beautify,
                app_name=f"plugin:{decl['alias']}",
                app_id=provider,
                log=self.log,
            )
            self.log.ok(
                t(
                    "cli.plugin_exported",
                    alias=decl["alias"],
                    provider=provider,
                    version=pkg.version,
                    path=pdest,
                )
            )

    def export_all(
        self,
        out: Optional[Union[str, Path]] = None,
        beautify: bool = True,
        kind: str = "all",
        with_plugins: bool = False,
    ) -> List[Path]:
        """Export everything; ``kind`` filters: all | app | plugin."""
        exported = []
        for app in self.list():
            if kind != "all" and app.kind != kind:
                continue
            try:
                exported.append(
                    self.export(
                        app.app_id,
                        out=out,
                        beautify=beautify,
                        with_plugins=with_plugins,
                    )
                )
            except Exception as e:
                self.log.warn(f"{app.display_name}: {e}")
        return exported

    def export_framework(
        self, out: Optional[Union[str, Path]] = None, beautify: bool = False
    ) -> List[Path]:
        """Unpack all framework packages into ``<out>/<appId>_<name>_v<ver>/``."""
        out_root = Path(out) if out else self.workdir / "framework"
        out_root.mkdir(parents=True, exist_ok=True)
        exported = []
        for fw in self.framework():
            if fw.manifest_dir is None:
                continue
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", fw.name or "?")
            dest = out_root / f"{fw.app_id}_{name}_v{fw.version}"
            if dest.exists():
                continue
            tars = list(fw.manifest_dir.glob("*.tar"))
            if not tars:
                continue
            _unpack_to(tars[0], dest)
            shutil.copy2(fw.manifest_dir / "Manifest.xml", dest / "Manifest.xml")
            n = sum(1 for _ in dest.rglob("*") if _.is_file())
            self.log.ok(
                t("cli.fw_exported", app_id=fw.app_id, name=fw.name, n=n, path=dest)
            )
            exported.append(dest)
        return exported
