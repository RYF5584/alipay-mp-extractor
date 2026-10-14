"""Decompilation: beautify JS, recover CSS, organise output by subpackage."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import jsbeautifier

from .i18n import t

CSS_RULE = re.compile(r"[.#@][\w\-., :#\[\]=\"'()>~^$*+]{0,300}?\{[^{}]{1,3000}\}")
CSS_BODY = re.compile(r"[\w-]+\s*:\s*[^;{}]+;")
PKG_ROOT = re.compile(r"(packages/[^/]+)")

_EXTRAS = [
    "appConfig.json",
    "meta.json",
    "manifest.json",
    "api_permission",
    "index.html",
    "_fileList",
]


def extract_css(js: str) -> str:
    """Pull compiled CSS rule strings out of the render bundle."""
    found, seen = [], set()
    for m in CSS_RULE.finditer(js):
        frag = m.group(0).strip()
        if CSS_BODY.search(frag) and frag not in seen:
            seen.add(frag)
            found.append(frag)
    return "\n".join(found) + ("\n" if found else "")


_beautify_opts = None


def beautify_js(src: Path, dst: Path, enabled: bool = True) -> bool:
    """Format JS in-process via the pure-python jsbeautifier; on failure the
    original file is copied as-is."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        try:
            global _beautify_opts
            if _beautify_opts is None:
                _beautify_opts = jsbeautifier.default_options()
                _beautify_opts.indent_size = 2
            text = jsbeautifier.beautify_file(str(src), _beautify_opts)
            dst.write_text(text, errors="ignore")
            return True
        except Exception:
            pass
    shutil.copy2(src, dst)
    return False


def subpackage_root(page: str) -> str:
    """``packages/mine/pages/x`` -> ``packages/mine``; main-package -> ''."""
    m = PKG_ROOT.match(page)
    return m.group(1) if m else ""


def _write_css(css: str, target: Path) -> None:
    if css:
        target.with_suffix(".extracted.css").write_text(css, errors="ignore")


def _page_index(pages: Dict[str, dict], pretty_worker: str) -> List[str]:
    lines = [
        "# Page index",
        "",
        "| route | subpackage | render chunk | logic layer (worker.js line) |",
        "|---|---|---|---|",
    ]
    for page in sorted(pages):
        root = subpackage_root(page) or "(main)"
        rend = (
            ", ".join(f"`{r}`" for r in pages[page].get("render", []))
            or "`app/index.js`"
        )
        loc = ""
        if pretty_worker:
            idx = pretty_worker.find(f'"{page}"')
            if idx < 0:
                idx = pretty_worker.find(page)
            if idx >= 0:
                loc = "~line {}".format(pretty_worker.count("\n", 0, idx) + 1)
        lines.append(f"| `{page}` | {root} | {rend} | {loc} |")
    return lines


def decompile_app(
    src: Path,
    dec: Path,
    beautify: bool = True,
    app_name: str = "",
    app_id: str = "",
    log: Optional[object] = None,
) -> None:
    """Decompile an unpacked ``src`` tree into a readable ``dec`` tree.

    Layout::

        dec/
          PAGES.md          page index (route / subpackage / chunks / line hint)
          REPORT.md         domains & app info
          app/              main-package worker + render bundles (beautified)
          subpackages/<r>/  per-subpackage chunks + README
          shared/           chunks used by more than one subpackage
    """
    src, dec = Path(src), Path(dec)
    dec.mkdir(parents=True, exist_ok=True)

    meta = {}
    meta_path = src / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(errors="ignore"))
        except json.JSONDecodeError:
            pass
    pages = meta.get("pages", {})

    chunk_pages: Dict[str, List[str]] = {}
    for page, dep in pages.items():
        for f in dep.get("render", []):
            chunk_pages.setdefault(f, []).append(page)

    def chunk_owner(f: str) -> str:
        roots = {subpackage_root(p) for p in chunk_pages.get(f, [])}
        return roots.pop() if len(roots) == 1 else "shared"

    app_dir = dec / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    done = set()
    beautify_warned = False

    def convert(f: Path, out: Path) -> None:
        nonlocal beautify_warned
        ok = beautify_js(f, out, beautify)
        if beautify and not ok and not beautify_warned and log is not None:
            log.warn(t("err.beautify"))
            beautify_warned = True
        _write_css(extract_css(f.read_text(errors="ignore")), out)

    # main entry bundles always live in app/
    for entry in ("index.worker.js", "index.js"):
        f = src / entry
        if f.exists():
            convert(f, app_dir / entry)
            done.add(entry)

    for f, owner in sorted({f: chunk_owner(f) for f in chunk_pages}.items()):
        if f in done or not (src / f).exists():
            continue
        done.add(f)
        if owner == "":
            target_dir = app_dir
        elif owner == "shared":
            target_dir = dec / "shared"
        else:
            target_dir = dec / "subpackages" / owner.split("/", 1)[1]
        convert(src / f, target_dir / Path(f))

    # subpackage READMEs
    by_pkg: Dict[str, List[str]] = {}
    for page in pages:
        by_pkg.setdefault(subpackage_root(page), []).append(page)
    for root, plist in by_pkg.items():
        if not root:
            continue
        d = dec / "subpackages" / root.split("/", 1)[1]
        d.mkdir(parents=True, exist_ok=True)
        body = "".join(f"\n- `{p}`" for p in sorted(plist))
        (d / "README.md").write_text(
            f"# subpackage {root}\n\n{len(plist)} pages:{body}\n", errors="ignore"
        )

    # plain-text configs
    for extra in _EXTRAS:
        p = src / extra
        if p.exists():
            shutil.copy2(p, dec / extra)

    # PAGES.md (line hints resolved against the beautified worker bundle)
    pretty_worker = ""
    pw = app_dir / "index.worker.js"
    if pw.exists():
        pretty_worker = pw.read_text(errors="ignore")
    (dec / "PAGES.md").write_text(
        "\n".join(_page_index(pages, pretty_worker)) + "\n", errors="ignore"
    )

    # REPORT.md
    urls = set()
    for js in src.rglob("*.js"):
        try:
            urls |= set(
                re.findall(
                    r"https?://[\w\-.]+(?::\d+)?(?:/[\w\-./%?=&]*)?",
                    js.read_text(errors="ignore"),
                )
            )
        except OSError:
            continue
    urls = {u for u in urls if "w3.org" not in u and "appx/" not in u}
    title = f"# {app_name or app_id}" + (f" ({app_id})" if app_name and app_id else "")
    report = [
        title,
        "",
        f"pages: {len(pages)}",
        "",
        "see PAGES.md for the page index",
        "",
    ]
    if urls:
        report.append(f"## domains ({len(urls)})")
        report.append("")
        report += [f"- {u}" for u in sorted(urls)[:100]]
    (dec / "REPORT.md").write_text("\n".join(report) + "\n", errors="ignore")
