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
