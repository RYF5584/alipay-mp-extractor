"""High-level client: sync / list / search / query / export."""

from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from .adb import (
    AdbTransport,
    DEFAULT_ADB_HOST,
    DEFAULT_ADB_PORT,
    DEFAULT_TIMEOUT,
)
from .console import Logger, Progress, human_size
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
    load_alias_cache,
    load_plugins,
    save_alias_cache,
    scan_apps,
    scan_framework,
)
from .unpack import unpack_package

# device paths (Alipay >= 10.x XRiver container; legacy paths probed too)
ALIPAY_PKG = "com.eg.android.AlipayGphone"
_DATA = f"/data/data/{ALIPAY_PKG}"
_SDCARD = f"/sdcard/Android/data/{ALIPAY_PKG}"

# light sync: metadata only (a few hundred KB total)
LIGHT_TARGETS = [
    (
        "container databases",
        f"{_DATA}/databases",
        "nebula_app.db nebulax_app.db xriver_app.db "
        "aomp_mini_app_center.db open_platform_apps.db",
    ),
    ("ccdn profile", f"{_DATA}/shared_prefs", "pref_ccdn_profile.xml"),
]

# full sync: everything incl. package payloads
FULL_TARGETS = [
    ("business packages (ccdn cache)", f"{_DATA}/files/Sandbox", "*/database/ccdn"),
    ("legacy business packages (nebulaApp)", f"{_DATA}/files", "nebulaApp"),
    ("framework packages", f"{_DATA}/files", "nebulaInstallApps"),
] + LIGHT_TARGETS + [
    ("external h5 cache (legacy)", f"{_SDCARD}/files", "nebulaH5App"),
]

SANDBOX_CD = f"{_DATA}/files/Sandbox"
INDEX_NAME = "index.tsv"
FRAMEWORK_INDEX = "framework_index.json"


def _enum_business_packages(self_ref, adb):
    """Enumerate business packages on-device (tar -tf, KBs of output).

    Covers both layouts: the modern ccdn cache and the legacy nebulaApp
    directory, so old Alipay installs are discovered in light sync too.
    """
    cmd = (
        f"su -c 'for f in {SANDBOX_CD}/*/database/ccdn/caches/app/data/*/0.dc; "
        f'do [ -f "$f" ] || continue; echo "=== $f"; tar -tf "$f" 2>/dev/null; done; '
        f"for t in {_DATA}/files/nebulaApp/*/*/*.tar; do "
        f'[ -f "$t" ] || continue; echo "=== $t"; basename "$t"; done\''
    )
    return adb.shell_text(cmd, timeout=120)


def _parse_business_enum(text: str) -> Dict[str, str]:
    """'=== <absolute path>' + a '<appId>.tar' line -> {abs_path: appId}."""
    result: Dict[str, str] = {}
    current = None
    for line in text.splitlines():
        line = line.rstrip("\r")
        if line.startswith("=== "):
            current = line[4:].strip()
            continue
        if current and line.endswith(".tar"):
            stem = line.rsplit("/", 1)[-1][:-4]
            if stem.isdigit():
                result[current] = stem
                current = None
    return result


def _enum_framework_manifests(self_ref, adb):
    """Read every framework Manifest.xml on-device (a few KB each)."""
    cmd = (
        f"su -c 'cd {_DATA}/files/nebulaInstallApps && for d in */*/; "
        f'do echo "=== $d"; cat "${{d}}Manifest.xml" 2>/dev/null; echo; done\''
    )
    text = adb.shell_text(cmd, timeout=120)
    out: Dict[str, str] = {}
    current = None
    buf: List[str] = []
    for line in text.splitlines():
        if line.startswith("=== "):
            if current is not None:
                out[current] = "\n".join(buf)
            current = line[4:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)
    return out


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
        self._alias_cache: Dict[str, dict] = {}
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
            self._alias_cache = load_alias_cache(self.dump)
            self._apps_cache = scan_apps(self.dump, plugin_index=self._plugin_index())
            # light sync only knows provider ids; restore human aliases
            # recorded during earlier exports
            for app in self._apps_cache.values():
                for d in app.plugins:
                    cached = self._alias_cache.get(d["provider"])
                    if cached and d["alias"] == d["provider"]:
                        d["alias"] = cached["alias"]
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

    def sync(self, force: bool = False, full: bool = False) -> SyncReport:
        """Pull package metadata from the device (root required).

        Light sync (default) transfers a few hundred KB: container databases
        plus an on-device enumeration of business packages. Package payloads
        are pulled on demand at :meth:`export` time. ``full=True`` streams
        every package to disk instead.
        """
        marker = self.dump / INDEX_NAME
        if self._has_dump() and not force and (full is False and marker.exists()):
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

        if not full:
            for desc, cd, rels in LIGHT_TARGETS:
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
            try:
                self.log.info(t("cli.pull_target", desc="package index (on-device)"))
                raw = _enum_business_packages(self, self.adb)
                mapping = _parse_business_enum(raw)
                index = self.dump / INDEX_NAME
                index.write_text(
                    "".join(f"{rel}\t{aid}\n" for rel, aid in mapping.items()),
                    errors="ignore",
                )
                self.log.info(t("cli.index_done", n=len(mapping)))
                report.targets.append("package index")
                report.entries += len(mapping)
                self.log.info(
                    t("cli.pull_target", desc=f"framework manifests (on-device)")
                )
                fw = _enum_framework_manifests(self, self.adb)
                (self.dump / FRAMEWORK_INDEX).write_text(
                    json.dumps(fw, ensure_ascii=False), errors="ignore"
                )
            except Exception as e:
                self.log.warn(t("err.pull", desc="on-device index", detail=e))
        else:
            for desc, cd, rels in FULL_TARGETS:
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
        self.log.ok(
            t("cli.sync_done", n=report.entries, path=self.dump)
            + ("" if full else " " + t("cli.sync_light"))
        )
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

        pkg_file = self._ensure_package(app)
        _unpack_to(pkg_file, dest)

        plugin_index = self._plugin_index()
        enrich_from_src(app, dest / "src", plugin_index)
        for d in app.plugins:
            self._alias_cache[d["provider"]] = {
                "alias": d["alias"], "app_id": app.app_id,
            }
        save_alias_cache(self.dump, self._alias_cache)
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

    def _ensure_package(self, app: MiniApp) -> Path:
        """Return a local package file, pulling just that dc on demand."""
        if app.package_file is not None and app.package_file.exists():
            return app.package_file
        if not app.device_path:
            from .errors import PackageParseError

            raise PackageParseError(
                path=app.app_id,
                detail=t("err.no_package", app_id=app.app_id)
                + " "
                + t("err.need_device"),
            )
        cache_dir = self.dump / "packages"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = cache_dir / f"{app.app_id}.dc"
        if not cache.exists():
            # device must be reachable; light dumps keep payloads on it.
            # validate the device first so a missing one is not reported as
            # a root problem; then cd into the dc's directory so the tar
            # member name is bare - a prefixed member would defeat
            # unpack_package's layout logic
            self.adb.shell("true", timeout=15)
            self.adb.require_root()
            pkg_dir, _, pkg_name = app.device_path.rpartition("/")
            self.log.info(
                t("cli.pull_pkg", name=app.display_name, size=human_size(app.size))
            )
            data = self.adb.pull_tar(pkg_dir, pkg_name or "0.dc")
            if data:
                # the pull wraps the dc in a transport tar (single member
                # "0.dc"); unwrap so cache holds the business archive itself
                try:
                    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                        names = tf.getnames()
                        if names == ["0.dc"]:
                            with tf.extractfile("0.dc") as f:
                                data = f.read()
                except tarfile.TarError:
                    pass
            if not data:
                from .errors import PackageParseError

                raise PackageParseError(
                    path=app.device_path, detail=t("err.pull", desc=app.device_path,
                                                  detail="empty stream")
                )
            cache.write_bytes(data)
        app.package_file = cache
        app.size = cache.stat().st_size
        return cache

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
            if pkg is None or (pkg.package_file is None and not pkg.device_path):
                self.log.warn(
                    t("cli.plugin_missing", alias=decl["alias"], provider=provider)
                )
                continue
            pdest = out / decl["alias"]
            if pdest.exists():
                continue
            _unpack_to(self._ensure_package(pkg), pdest)
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
        targets = [
            a for a in self.list() if kind == "all" or a.kind == kind
        ]
        exported = []
        progress = Progress(len(targets), t("cli.progress_export"), enabled=None)
        for app in targets:
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
            progress.step(app.display_name)
        progress.done()
        return exported

    def export_framework(
        self, out: Optional[Union[str, Path]] = None, beautify: bool = False
    ) -> List[Path]:
        """Unpack all framework packages into ``<out>/<appId>_<name>_v<ver>/``."""
        out_root = Path(out) if out else self.workdir / "framework"
        out_root.mkdir(parents=True, exist_ok=True)
        frameworks = self.framework()
        self._framework_xml = {}
        idx = self.dump / FRAMEWORK_INDEX
        if idx.exists():
            try:
                self._framework_xml = json.loads(idx.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        progress = Progress(len(frameworks), t("cli.progress_framework"), enabled=None)
        exported = []
        for fw in frameworks:
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", fw.name or "?")
            dest = out_root / f"{fw.app_id}_{name}_v{fw.version}"
            if dest.exists():
                continue
            if fw.manifest_dir is not None:
                tars = list(fw.manifest_dir.glob("*.tar"))
                if not tars:
                    continue
                _unpack_to(tars[0], dest)
            elif fw.device_dir:
                # light mode: pull just this framework directory on demand
                cache_dir = self.dump / "packages"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache = cache_dir / f"fw_{fw.app_id}.tar"
                if not cache.exists():
                    self.adb.require_root()
                    data = self.adb.pull_tar(
                        f"{_DATA}/files/nebulaInstallApps/{fw.device_dir}", "*.tar"
                    )
                    if not data:
                        self.log.warn(
                            t("err.pull", desc=fw.device_dir, detail="empty stream")
                        )
                        continue
                    cache.write_bytes(data)
                _unpack_to(cache, dest)
            else:
                continue
            if fw.manifest_dir is not None:
                shutil.copy2(fw.manifest_dir / "Manifest.xml", dest / "Manifest.xml")
            else:
                (dest / "Manifest.xml").write_text(
                    self._framework_xml.get(fw.device_dir, ""), errors="ignore"
                )
            n = sum(1 for _ in dest.rglob("*") if _.is_file())
            self.log.ok(
                t("cli.fw_exported", app_id=fw.app_id, name=fw.name, n=n, path=dest)
            )
            exported.append(dest)
            progress.step(f"{fw.app_id} {fw.name}")
        progress.done()
        return exported
