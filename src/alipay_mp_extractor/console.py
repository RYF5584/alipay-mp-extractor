"""Plain-stdlib console tables (CJK-width aware) and logging helpers."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence


def display_width(s: str) -> int:
    """Terminal cell width (CJK/fullwidth chars count as 2)."""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return w


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


def trunc(s: str, width: int) -> str:
    if display_width(s) <= width:
        return s
    out, w = "", 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if w + cw > width - 1:
            break
        out += ch
        w += cw
    return out + "…"


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    align: Optional[Sequence[str]] = None,
) -> str:
    """Render an aligned table. ``align``: 'l' or 'r' per column."""
    str_rows = [[("" if c is None else str(c)) for c in row] for row in rows]
    ncol = len(headers)
    widths = [display_width(h) for h in headers]
    for row in str_rows:
        for i in range(ncol):
            widths[i] = max(widths[i], display_width(row[i]))
    align = align or ["l"] * ncol

    def fmt(row: Sequence[str]) -> str:
        cells = []
        for i, cell in enumerate(row):
            cells.append(
                pad(cell, widths[i]) if align[i] == "l" else cell.rjust(widths[i])
            )
        return "  ".join(cells).rstrip()

    sep = "  ".join("-" * w for w in widths)
    lines = [fmt(list(headers)), sep]
    lines += [fmt(r) for r in str_rows]
    return "\n".join(lines)


def human_size(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.1f}{unit}" if unit != "B" else f"{int(f)}B"
        f /= 1024
    return f"{f:.1f}GB"


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


class Logger:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def info(self, msg: str) -> None:
        print(msg)

    def ok(self, msg: str) -> None:
        print(f"[+] {msg}")

    def skip(self, msg: str) -> None:
        print(f"[=] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[!] {msg}", flush=True)

    def debug(self, msg: str) -> None:
        if self.verbose:
            print(f"[db] {msg}")
