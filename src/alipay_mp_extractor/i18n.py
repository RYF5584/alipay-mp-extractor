"""Minimal i18n: zh (default for Chinese locales) / en, auto-detected."""

from __future__ import annotations

import locale
import os
from typing import Dict, Optional

_MSGS: Dict[str, Dict[str, str]] = {
    "zh": {
        # errors
        "err.adb_server": "无法连接 adb 服务 ({host}:{port})：{detail}。请确认 adb 已启动 (adb start-server)",
        "err.device_not_found": "未找到 adb 设备 '{serial}'。当前可见设备：{known}。可用 `adb devices` 检查，或用 --serial/--connect 指定",
        "err.no_device": "没有可用的 adb 设备。请连接手机（USB）或用 --connect IP:PORT 连接网络设备",
        "err.root_required": "需要 root 权限：`adb shell su -c id` 未返回 uid=0。请在手机上确认已授权 adb 的 su 请求（Magisk/KernelSU 弹窗）",
        "err.pull": "拉取 '{desc}' 失败：{detail}",
        "err.pull_all_failed": "所有数据源拉取均失败，请检查 root 与连接后重试 (--force)",
        "err.tar_corrupt": "tar 流损坏（adb 大流量偶发中断），请重试 sync --force",
        "err.pkg_parse": "解析包失败 '{path}'：{detail}",
        "err.db_parse": "解析数据库 '{path}' 失败：{detail}",
        "err.app_not_found": "未找到匹配 '{key}' 的小程序，先用 list/search 查看",
        "err.ambiguous": "'{key}' 匹配到多个结果：{names}",
        "err.no_package": "{app_id} 没有缓存的包文件，请先 sync()",
        "err.beautify": "JS 美化失败，已保留原始文件",
        # cli / progress
        "cli.pull_target": "拉取 {desc}",
        "cli.pull_skip": "(不存在或为空，跳过 —— 旧版路径缺失属正常)",
        "cli.sync_done": "同步完成：{n} 个条目 -> {path}",
        "cli.sync_skip": "device_dump 已存在，跳过同步 (force=True 重新拉取)",
        "cli.exported": "导出 {name}({app_id}) -> {path}",
        "cli.export_skip": "{name}: 已导出，跳过 (overwrite=True 强制重做)",
        "cli.plugin_exported": "  插件 {alias}({provider}, v{version}) -> {path}",
        "cli.plugin_missing": "插件 {alias}({provider}) 不在缓存中；在手机上打开触发该插件的页面后重新 sync",
        "cli.fw_exported": "框架包 {app_id} {name}：{n} 个文件 -> {path}",
        "cli.no_apps": "未发现业务小程序包；请在支付宝中打开目标小程序后重新执行 sync",
        "cli.export_hint": "{n} 个结果。导出：alipay-mp export <名称|appId>",
        "cli.fw_hint": "共 {n} 个框架包",
        "cli.plugin_hint": "共 {n} 个插件。导出：alipay-mp export <provider>",
        "cli.interrupted": "已中断",
        # help / argparse
        "help.prog": "从已 root 的 Android 设备提取并反编译支付宝小程序",
        "help.sync": "从设备拉取小程序数据",
        "help.sync_force": "数据已存在时强制重新拉取",
        "help.sync_full": "同时把全部包内容拉到本地（较慢，用于完全离线分析）",
        "help.list": "列出设备上全部小程序与插件",
        "help.search": "按名称 / appId / 插件别名搜索",
        "help.keyword": "搜索关键词",
        "help.info": "查看单个小程序详情（含插件声明）",
        "help.key": "小程序名称或 appId",
        "help.export": "导出（解包 + 反编译）一个或多个小程序",
        "help.keys": "名称或 appId，可指定多个",
        "help.export_out": "输出目录（默认 <workdir>/apps）",
        "help.no_beautify": "跳过 JS 美化，保留原始文件",
        "help.with_plugins": "同时导出小程序声明的插件",
        "help.overwrite": "重新导出已存在的目录",
        "help.export_all": "导出全部小程序",
        "help.kind": "导出范围：all=全部 / app=小程序 / plugin=插件",
        "help.plugins": "列出容器已知插件及其使用方",
        "help.framework": "列出官方框架包；--export 同时解包",
        "help.framework_export": "解包全部框架包",
        "help.cmd_help": "显示命令帮助",
        "help.topic": "要查看的子命令名",
        "help.out": "输出目录",
        "help.json": "以 JSON 格式输出",
        "help.serial": "USB 设备序列号（默认取第一台）",
        "help.connect": "通过网络连接设备（adb connect IP:PORT）",
        "help.adb_host": "adb server 主机地址",
        "help.adb_port": "adb server 端口",
        "help.backend": "adb 传输后端：auto=adbutils 失败自动改用系统 adb",
        "help.workdir": "工作目录（存放拉取数据与导出结果）",
        "help.lang": "界面语言（zh/en，默认自动识别）",
        "help.verbose": "显示调试信息",
        "help.examples": (
            "示例：\n"
            "  alipay-mp sync --force          # 重新从手机拉取\n"
            "  alipay-mp list                  # 列出全部小程序\n"
            "  alipay-mp search <名称>          # 搜索\n"
            "  alipay-mp info <名称|appId>     # 查看详情\n"
            "  alipay-mp export <名称|appId>   # 导出并反编译\n"
            "  alipay-mp plugins               # 插件清单"
        ),
        "cli.sync_light": "（轻量模式：包内容将在导出时按需拉取，--full 可全量拉取）",
        "cli.index_done": "已索引 {n} 个业务包",
        "cli.progress_export": "导出",
        "cli.progress_framework": "框架包",
        "cli.pull_pkg": "拉取 {name} 的包（{size}）",
        "cli.batch_done": "批量完成 {n}/{total}",
        "err.need_device": "本地无缓存，需连接设备按需拉取，或执行 sync --full",
    },
    "en": {
        "err.adb_server": "cannot reach adb server ({host}:{port}): {detail}. Is adb running? (adb start-server)",
        "err.device_not_found": "adb device '{serial}' not found. Visible: {known}. Check `adb devices`, or pass --serial/--connect",
        "err.no_device": "no adb device available. Connect a phone (USB) or use --connect IP:PORT",
        "err.root_required": "root required: `adb shell su -c id` did not return uid=0. Approve the su prompt for adb on the phone (Magisk/KernelSU)",
        "err.pull": "pull '{desc}' failed: {detail}",
        "err.pull_all_failed": "all pull targets failed; check root/connection and retry with --force",
        "err.tar_corrupt": "tar stream corrupted (adb hiccup on large transfers), retry sync --force",
        "err.pkg_parse": "failed to parse package '{path}': {detail}",
        "err.db_parse": "failed to parse database '{path}': {detail}",
        "err.app_not_found": "no mini-program matches '{key}'; use list/search first",
        "err.ambiguous": "'{key}' is ambiguous: {names}",
        "err.no_package": "{app_id} has no cached package file; run sync() first",
        "err.beautify": "JS formatting failed; kept the original file",
        "cli.pull_target": "pulling {desc}",
        "cli.pull_skip": "(missing or empty, skipped - legacy path absent is normal)",
        "cli.sync_done": "synced {n} entries -> {path}",
        "cli.sync_skip": "device_dump already exists, skip sync (force=True to redo)",
        "cli.exported": "exported {name}({app_id}) -> {path}",
        "cli.export_skip": "{name}: already exported, skip (overwrite=True to redo)",
        "cli.plugin_exported": "  plugin {alias}({provider}, v{version}) -> {path}",
        "cli.plugin_missing": "plugin {alias}({provider}) not in cache; open a page that triggers it on the device and re-sync",
        "cli.fw_exported": "framework {app_id} {name}: {n} files -> {path}",
        "cli.no_apps": "no business packages found; open a mini-program on the device, then sync again",
        "cli.export_hint": "{n} item(s). export with: alipay-mp export <name|appId>",
        "cli.fw_hint": "{n} framework package(s)",
        "cli.plugin_hint": "{n} plugin(s). export via: alipay-mp export <provider>",
        "cli.interrupted": "interrupted",
        # help / argparse
        "help.prog": "Extract and decompile Alipay mini-programs from a rooted Android device",
        "help.sync": "pull mini-program data from the device",
        "help.sync_force": "re-pull even if data already exists",
        "help.sync_full": "also stream every package payload to disk (slower, for offline analysis)",
        "help.list": "list all mini-programs and plugins on the device",
        "help.search": "search by name / appId / plugin alias",
        "help.keyword": "search keyword",
        "help.info": "show details of one mini-program (incl. declared plugins)",
        "help.key": "mini-program name or appId",
        "help.export": "export (unpack + decompile) one or more mini-programs",
        "help.keys": "name or appId, multiple allowed",
        "help.export_out": "output directory (default <workdir>/apps)",
        "help.no_beautify": "skip JS formatting, keep raw files",
        "help.with_plugins": "also export the plugins declared by the app(s)",
        "help.overwrite": "redo existing export directories",
        "help.export_all": "export everything",
        "help.kind": "what to export: all / app / plugin",
        "help.plugins": "list plugins known to the container and who uses them",
        "help.framework": "list official framework packages; --export also unpacks them",
        "help.framework_export": "also unpack all framework packages",
        "help.cmd_help": "show help for a command",
        "help.topic": "sub-command to inspect",
        "help.out": "output directory",
        "help.json": "output JSON",
        "help.serial": "USB device serial (default: first device)",
        "help.connect": "network device via adb connect IP:PORT",
        "help.adb_host": "adb server host",
        "help.adb_port": "adb server port",
        "help.backend": "adb backend: auto = adbutils with system-adb fallback",
        "help.workdir": "workspace directory for the dump and exports",
        "help.lang": "UI language (zh/en, default: auto)",
        "help.verbose": "show debug output",
        "help.examples": (
            "examples:\n"
            "  alipay-mp sync --force          # re-pull from the phone\n"
            "  alipay-mp list                  # list all mini-programs\n"
            "  alipay-mp search <name>         # search\n"
            "  alipay-mp info <name|appId>     # details\n"
            "  alipay-mp export <name|appId>   # export & decompile\n"
            "  alipay-mp plugins               # plugin list"
        ),
        "cli.sync_light": "(light sync: package payloads are pulled on demand at export; use --full to fetch everything)",
        "cli.index_done": "indexed {n} business packages",
        "cli.progress_export": "export",
        "cli.progress_framework": "framework",
        "cli.pull_pkg": "pulling package of {name} ({size})",
        "cli.batch_done": "batch done {n}/{total}",
        "err.need_device": "not cached locally; connect the device to pull it, or run sync --full",
    },
}

_lang: Optional[str] = None


def detect_lang() -> str:
    """'zh' for Chinese locales (default), 'en' otherwise."""
    for src in (
        os.environ.get("ALIPAY_MP_LANG"),
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
        (locale.getdefaultlocale() or (None,))[0],
    ):
        if src:
            return "zh" if src.lower().startswith("zh") else "en"
    return "en"


def set_lang(lang: Optional[str]) -> None:
    """Override language: 'zh' / 'en'; None re-enables auto-detection."""
    global _lang
    _lang = lang


def t(key: str, **kw) -> str:
    lang = _lang or detect_lang()
    table = _MSGS.get(lang) or _MSGS["en"]
    msg = table.get(key) or _MSGS["en"].get(key) or key
    return msg.format(**kw) if kw else msg
