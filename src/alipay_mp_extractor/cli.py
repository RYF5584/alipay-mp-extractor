"""Command line interface (fully localized, incl. help texts).

::

    alipay-mp sync [--force] [--full]
    alipay-mp list [--json]
    alipay-mp search <keyword> [--json]
    alipay-mp info <key> [--json]
    alipay-mp export <key>... [-o DIR] [--no-beautify] [--with-plugins] [--overwrite]
    alipay-mp export-all [-o DIR] [--kind app|plugin|all]
    alipay-mp plugins [--json]
    alipay-mp framework [--export] [--json]
    alipay-mp help [command]

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
    p.add_argument("--serial", metavar="ID", help=t("help.serial"))
    p.add_argument("--connect", metavar="IP:PORT", help=t("help.connect"))
    p.add_argument("--adb-host", default="127.0.0.1", help=t("help.adb_host"))
    p.add_argument("--adb-port", type=int, default=5037, help=t("help.adb_port"))
    p.add_argument(
        "--backend",
        choices=["auto", "adbutils", "system"],
        default="auto",
        help=t("help.backend"),
    )
    p.add_argument(
        "-w", "--workdir", default="./alipay_mp_workspace", help=t("help.workdir")
    )
    p.add_argument("--lang", choices=["zh", "en"], help=t("help.lang"))
    p.add_argument("-v", "--verbose", action="store_true", help=t("help.verbose"))


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


def cmd_help(args, parser: argparse.ArgumentParser) -> int:
    choices = parser._subparsers._group_actions[0].choices  # noqa: SLF001
    if not args.topic:
        parser.print_help()
        return 0
    sub = choices.get(args.topic)
    if sub is None or args.topic == "help":
        print(f"unknown command: {args.topic}", file=sys.stderr)
        print(
            f"available: {', '.join(k for k in choices if k != 'help')}",
            file=sys.stderr,
        )
        return 1
    sub.print_help()
    return 0


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="alipay-mp",
        description=t("help.prog"),
        epilog=t("help.examples"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    top.add_argument("--lang", choices=["zh", "en"], help=t("help.lang"))
    sub = top.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sync", help=t("help.sync"), description=t("help.sync"))
    p.add_argument("--force", action="store_true", help=t("help.sync_force"))
    p.add_argument("--full", action="store_true", help=t("help.sync_full"))
    _add_device_args(p)
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("list", help=t("help.list"), description=t("help.list"))
    p.add_argument("--json", action="store_true", help=t("help.json"))
    _add_device_args(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help=t("help.search"), description=t("help.search"))
    p.add_argument("keyword", help=t("help.keyword"))
    p.add_argument("--json", action="store_true", help=t("help.json"))
    _add_device_args(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("info", help=t("help.info"), description=t("help.info"))
    p.add_argument("key", help=t("help.key"))
    p.add_argument("--json", action="store_true", help=t("help.json"))
    _add_device_args(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("export", help=t("help.export"), description=t("help.export"))
    p.add_argument("keys", nargs="+", help=t("help.keys"))
    p.add_argument("-o", "--out", help=t("help.export_out"))
    p.add_argument(
        "--no-beautify",
        dest="beautify",
        action="store_false",
        help=t("help.no_beautify"),
    )
    p.add_argument(
        "--with-plugins",
        dest="plugins",
        action="store_true",
        help=t("help.with_plugins"),
    )
    p.add_argument("--overwrite", action="store_true", help=t("help.overwrite"))
    _add_device_args(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser(
        "export-all", help=t("help.export_all"), description=t("help.export_all")
    )
    p.add_argument("-o", "--out", help=t("help.out"))
    p.add_argument(
        "--kind", choices=["all", "app", "plugin"], default="all", help=t("help.kind")
    )
    p.add_argument(
        "--no-beautify", dest="beautify", action="store_false", help=t("help.no_beautify")
    )
    p.add_argument(
        "--with-plugins",
        dest="plugins",
        action="store_true",
        help=t("help.with_plugins"),
    )
    _add_device_args(p)
    p.set_defaults(func=cmd_export_all)

    p = sub.add_parser("plugins", help=t("help.plugins"), description=t("help.plugins"))
    p.add_argument("--json", action="store_true", help=t("help.json"))
    _add_device_args(p)
    p.set_defaults(func=cmd_plugins)

    p = sub.add_parser(
        "framework", help=t("help.framework"), description=t("help.framework")
    )
    p.add_argument("--export", action="store_true", help=t("help.framework_export"))
    p.add_argument("--json", action="store_true", help=t("help.json"))
    _add_device_args(p)
    p.set_defaults(func=cmd_framework)

    p = sub.add_parser("help", help=t("help.cmd_help"), description=t("help.cmd_help"))
    p.add_argument("topic", nargs="?", help=t("help.topic"))
    _add_device_args(p)  # accept the common global options for consistency
    p.set_defaults(func=None)

    return top


def _preset_lang(argv: Optional[List[str]]) -> None:
    """Apply --lang before parsing so help texts are localized too."""
    items = list(argv if argv is not None else sys.argv[1:])
    for i, a in enumerate(items):
        if a == "--lang" and i + 1 < len(items):
            set_lang(items[i + 1])
            return
        if a.startswith("--lang="):
            set_lang(a.split("=", 1)[1])
            return
    set_lang(None)


def main(argv: Optional[List[str]] = None) -> int:
    _preset_lang(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None) == "help":
        return cmd_help(args, parser)
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
