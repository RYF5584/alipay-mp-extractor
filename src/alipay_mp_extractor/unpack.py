"""Safe tar handling (python 3.8+ compatible, path-traversal hardened)."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Union


def _safe_dest(base: Path, name: str) -> Optional[Path]:
    dest = base / name
    try:
        resolved = dest.resolve()
        resolved.relative_to(base)
    except (OSError, ValueError):
        return None
    return dest


def extract_tar_stream(tf: tarfile.TarFile, dest_root: Path) -> int:
    """Extract regular files/dirs from an open TarFile into ``dest_root``.

    Skips symlinks/devices and anything escaping ``dest_root``.
    Returns the number of extracted entries.
    """
    base = Path(dest_root)
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()
    n = 0
    for m in tf.getmembers():
        if not (m.isfile() or m.isdir()):
            continue
        dest = _safe_dest(base, m.name)
        if dest is None:
            continue
        try:
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            n += 1
        except OSError:
            continue
    return n


def extract_tar_file(tar_path: Union[str, Path], dest_root: Path) -> int:
    with tarfile.open(str(tar_path)) as tf:
        return extract_tar_stream(tf, Path(dest_root))


def unpack_package(pkg: Path, out: Path) -> Path:
    """Unpack a device package into ``out/src`` and return that directory.

    Two layouts exist on the device:
      - business packages: outer tar (``.signature``/``.meta``/``.manifest``
        plus ``<appId>.tar``) whose inner tar expands to ``src``
      - framework packages: a plain content tar; its entries become ``src``
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    extract_tar_file(pkg, out)
    src = out / "src"
    src.mkdir(exist_ok=True)
    inner_tars = [p for p in out.glob("*.tar") if p.is_file()]
    if inner_tars:
        # business package: expand every inner tar into src
        for inner in inner_tars:
            extract_tar_file(inner, src)
            inner.unlink()
    else:
        # framework package: the extracted entries ARE the content
        for item in list(out.iterdir()):
            if item.name == "src":
                continue
            shutil.move(str(item), str(src / item.name))
    return src
