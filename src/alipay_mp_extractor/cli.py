"""Command line interface.

::

    alipay-mp sync [--force] [--full]
    alipay-mp list [--json]
    alipay-mp search <keyword> [--json]
    alipay-mp info <key> [--json]
    alipay-mp export <key>... [-o DIR] [--no-beautify] [--with-plugins] [--overwrite]
    alipay-mp export-all [-o DIR] [--kind app|plugin|all]
    alipay-mp plugins [--json]
    alipay-mp framework [--export]

Device selection: --serial | --connect IP:PORT | --adb-host/--adb-port.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .client import AlipayMPExtractor
from .console import human_size, print_json, render_table
from .errors import AlipayMPError
from .i18n import set_lang, t
from .models import FrameworkPackage, MiniApp, PluginInfo


def _add_device_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--serial", metavar="ID", help="USB device serial (default: first)")
    p.add_argument(
        "--connect", metavar="IP:PORT", help="network device via adb connect"
    )
    p.add_argument("--adb-host", default="127.0.0.1", help="adb server host")
    p.add_argument("--adb-port", type=int, default=5037, help="adb server port")
    p.add_argument(
        "--backend",
        choices=["auto", "adbutils", "system"],
        default="auto",
        help="adb backend: auto = adbutils with system-adb fallback",
    )
    p.add_argument("-w", "--workdir", default="./alipay_mp_workspace", help="workspace dir")
    p.add_argument("--lang", choices=["zh", "en"], help="UI language (default: auto)")
    p.add_argument("-v", "--verbose", action="store_true")


def _make_client(args: argparse.Namespace) -> AlipayMPExtractor:
    return AlipayMPExtractor(
        serial=args.serial,
        connect=args.connect,
        adb_host=args.adb_host,
        adb_port=args.adb_port,
        backend=args.backend,
        workdir=args.workdir,
        verbose=args.verbose,
        lang=args.lang,
    )


# ------------------------------------------------------------------ render

def _print_apps(apps: List[MiniApp], as_json: bool) -> None:
    if as_json:
        print_json(
            [
                {
                    "app_id": a.app_id,
                    "name": a.name,
                    "kind": a.kind,
                    "version": a.version,
                    "size": human_size(a.size),
                }
                for a in apps
            ]
        )
        return
    if not apps:
        print(t("cli.no_apps"))
        return
    rows = [
        [a.app_id, a.name, a.kind, a.version, human_size(a.size)] for a in apps
    ]
    print(render_table(["appId", "name", "kind", "version", "size"], rows))
    print(f"\n{t('cli.export_hint', n=len(apps))}")


# ------------------------------------------------------------------ commands

def cmd_list(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    _print_apps(mp.list(), args.json)
    return 0


def cmd_search(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    _print_apps(mp.search(args.keyword), args.json)
    return 0


def cmd_info(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    app = mp.query(args.key)
    if args.json:
        print_json(app.to_dict())
        return 0
    rows = [
        ["appId", app.app_id],
        ["name", app.name],
        ["kind", app.kind],
        ["version", app.version],
        ["size", human_size(app.size)],
        ["package", str(app.package_file)],
        ["package_url", app.package_url or "-"],
    ]
    for d in app.plugins:
        rows.append(["plugin", f"{d['alias']} -> {d['provider']} (v{d['version']})"])
    print(render_table(["field", "value"], rows))
    return 0


def cmd_export(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    for key in args.keys:
        mp.export(
            key,
            out=args.out,
            beautify=args.beautify,
            with_plugins=args.plugins,
            overwrite=args.overwrite,
        )
    return 0


def cmd_export_all(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    mp.export_all(
        out=args.out, beautify=args.beautify, kind=args.kind, with_plugins=args.plugins
    )
    return 0


def cmd_sync(args) -> int:
    mp = _make_client(args)
    mp.sync(force=args.force, full=args.full)
    return 0


def cmd_plugins(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    plugins: List[PluginInfo] = mp.plugins()
    if args.json:
        print_json([p.to_dict() for p in plugins])
        return 0
    rows = [
        [p.provider, p.version, p.developer_version, ", ".join(p.used_by) or "-"]
        for p in plugins
    ]
    print(render_table(["provider", "version", "devVersion", "used by"], rows))
    print(f"\n{t('cli.plugin_hint', n=len(plugins))}")
    return 0


def cmd_framework(args) -> int:
    mp = _make_client(args)
    if not mp.is_synced():
        mp.sync()
    fws: List[FrameworkPackage] = mp.framework()
    if args.json:
        print_json([f.to_dict() for f in fws])
    else:
        rows = [[f.app_id, f.name, f.version, f.app_version] for f in fws]
        print(render_table(["appId", "name", "version", "appVersion"], rows))
        print(f"\n{t('cli.fw_hint', n=len(fws))}")
    if args.export:
        mp.export_framework()
    return 0


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="alipay-mp",
        description=(
            "Extract & decompile Alipay mini-programs from a rooted Android device"
        ),
    )
    sub = top.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync", help="pull metadata from the device (fast)")
    p.add_argument("--force", action="store_true", help="re-pull even if dump exists")
    p.add_argument("--full", action="store_true",
                   help="also stream every package payload to disk (slower)")
    _add_device_args(p)
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("list", help="list all mini-programs")
    p.add_argument("--json", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="search by name/appId/plugin alias")
    p.add_argument("keyword")
    p.add_argument("--json", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("info", help="show details of one mini-program")
    p.add_argument("key", help="name or appId")
    p.add_argument("--json", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("export", help="export (unpack + decompile) one or more apps")
    p.add_argument("keys", nargs="+", help="name or appId, multiple allowed")
    p.add_argument("-o", "--out", help="output directory (default <workdir>/apps)")
    p.add_argument(
        "--no-beautify",
        dest="beautify",
        action="store_false",
        help="skip JS formatting (faster, raw files)",
    )
    p.add_argument(
        "--with-plugins",
        dest="plugins",
        action="store_true",
        help="also export the plugins declared by the app(s)",
    )
    p.add_argument("--overwrite", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("export-all", help="export everything")
    p.add_argument("-o", "--out")
    p.add_argument("--kind", choices=["all", "app", "plugin"], default="all")
    p.add_argument("--no-beautify", dest="beautify", action="store_false")
    p.add_argument(
        "--with-plugins",
        dest="plugins",
        action="store_true",
        help="also export the plugins declared by each app",
    )
    _add_device_args(p)
    p.set_defaults(func=cmd_export_all)

    p = sub.add_parser("plugins", help="list known plugins")
    p.add_argument("--json", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_plugins)

    p = sub.add_parser("framework", help="list/extract official framework packages")
    p.add_argument("--export", action="store_true", help="also unpack them")
    p.add_argument("--json", action="store_true")
    _add_device_args(p)
    p.set_defaults(func=cmd_framework)

    return top


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_lang(getattr(args, "lang", None))
    try:
        return args.func(args)
    except AlipayMPError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{t('cli.interrupted')}", file=sys.stderr)
        return 130
    except Exception as e:
        if getattr(args, "verbose", False):
            raise
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
