---
name: alipay-mp-extract
description: >
  Extract and decompile Alipay (Android) mini-program packages from a rooted
  device. Use when the user wants to dump/unpack/decompile Alipay mini-program
  source code, inspect the plugins a mini-program declares, or list the
  mini-programs cached on a phone via adb.
---

# Alipay Mini-Program Extractor

Extract + decompile Alipay mini-programs (and, optionally, the plugins they
declare) from a rooted Android device over adb. Packages on the device are
plain tar archives — no decryption needed.

## When to use

- "导出/提取/反编译支付宝小程序源码" (dump Alipay mini-program source)
- "看看这个小程序依赖了什么插件" (inspect declared plugins)
- "手机上缓存了哪些支付宝小程序" (list cached mini-programs)

Requirements: adb-connected device with root (`adb shell su -c id` → uid=0),
Python 3.8+.

## CLI quick reference

```bash
uvx alipay-mp-extractor list                 # all cached mini-programs
uvx alipay-mp-extractor search <名称>         # search by name/appId/plugin alias
uvx alipay-mp-extractor info <名称>           # details incl. declared plugins
uvx alipay-mp-extractor export <名称>         # unpack + decompile
uvx alipay-mp-extractor export <名称> --with-plugins   # also export declared plugins
uvx alipay-mp-extractor export <名称1> <名称2> # multiple apps
uvx alipay-mp-extractor export-all           # everything
uvx alipay-mp-extractor plugins              # plugin table (provider / used by)
uvx alipay-mp-extractor framework --export   # official runtime packages

# device selection (all commands)
--serial <序列号>                     # USB serial
--connect 127.0.0.1:5555             # network device
--backend auto|adbutils|system       # adb transport
--lang zh|en                         # UI language (auto by locale)
```

## Library usage

```python
from alipay_mp_extractor import AlipayMPExtractor

mp = AlipayMPExtractor()                       # or AlipayMPExtractor(connect="127.0.0.1:5555")
mp.sync()                             # pull from device (root required)
mp.list(); mp.search("<名称>"); mp.query("<appId>")
out = mp.export("<名称>")              # -> Path with decompiled/ tree
mp.plugins(); mp.framework(); mp.export_framework()
```

## Export layout

```
apps/<小程序名称>/
├── src/                      compiled bundle (untouched)
└── decompiled/
    ├── PAGES.md              route / subpackage / chunk / worker line index
    ├── REPORT.md             domains & app info
    ├── app/                  main-package worker + render (beautified js)
    ├── subpackages/<分包>/    per-subpackage chunks + README
    ├── shared/               cross-subpackage chunks
    └── *.extracted.css       CSS recovered from the render bundle
plugins/<插件别名>/             with --with-plugins, same structure
```

Details: see [references/package-format.md](references/package-format.md) for
on-device storage & bundle format, and
[references/troubleshooting.md](references/troubleshooting.md) for common
errors.
