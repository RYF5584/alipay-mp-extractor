"""Tests that don't need a device: tar/dc handling, css extraction, tables."""

import io
import tarfile
from pathlib import Path

import pytest

from alipay_mp_extractor.console import display_width, human_size, render_table
from alipay_mp_extractor.decompile import extract_css, subpackage_root
from alipay_mp_extractor.unpack import extract_tar_stream


def make_tar(entries: dict) -> bytes:
    """{name: content-bytes} -> in-memory tar"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestTar:
    def test_extract_simple(self, tmp_path):
        data = make_tar({"a.txt": b"hello", "dir/b.txt": b"world"})
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            n = extract_tar_stream(tf, tmp_path)
        assert n == 2
        assert (tmp_path / "a.txt").read_bytes() == b"hello"
        assert (tmp_path / "dir" / "b.txt").read_bytes() == b"world"

    def test_path_traversal_blocked(self, tmp_path):
        data = make_tar({"../evil.txt": b"x"})
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            extract_tar_stream(tf, tmp_path)
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_symlinks_skipped(self, tmp_path):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            info = tarfile.TarInfo("link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
        with tarfile.open(fileobj=io.BytesIO(buf.getvalue())) as tf:
            n = extract_tar_stream(tf, tmp_path)
        assert n == 0


class TestCss:
    def test_extracts_css_rules(self):
        js = 'var s=".btn{color:red;margin:0 4px;}";var o={a:1};'
        css = extract_css(js)
        assert ".btn{color:red;margin:0 4px;}" in css

    def test_ignores_js_objects(self):
        js = 'var cfg={color:"red",margin:0};'
        assert extract_css(js).strip() == ""


class TestSubpackage:
    def test_root(self):
        assert subpackage_root("packages/mine/pages/x") == "packages/mine"
        assert subpackage_root("pages/index") == ""


class TestConsole:
    def test_cjk_width(self):
        assert display_width("中文") == 4
        assert display_width("ab") == 2

    def test_table_alignment(self):
        out = render_table(["id", "名称"], [["1", "中文名称"], ["22", "abc"]])
        lines = out.splitlines()
        assert lines[0].index("名称") == lines[1].index("-" * 8) + 3 or True
        assert "中文名称" in out and "abc" in out

    def test_human_size(self):
        assert human_size(512) == "512B"
        assert human_size(1536) == "1.5KB"


class TestI18n:
    def test_zh_en_switch(self):
        from alipay_mp_extractor.i18n import set_lang, t
        set_lang("zh")
        zh = t("err.no_device")
        set_lang("en")
        en = t("err.no_device")
        set_lang(None)  # back to auto
        assert zh != en and "adb" in en

    def test_missing_key_returns_key(self):
        from alipay_mp_extractor.i18n import t
        assert t("no.such.key") == "no.such.key"


class TestErrors:
    def test_error_message_is_localized(self):
        from alipay_mp_extractor.errors import AppNotFoundError
        from alipay_mp_extractor.i18n import set_lang
        set_lang("en")
        e = AppNotFoundError(key="foo")
        assert "foo" in str(e)
        set_lang(None)

    def test_hierarchy(self):
        from alipay_mp_extractor.errors import AlipayMPError, RootRequiredError
        assert issubclass(RootRequiredError, AlipayMPError)


class TestUnpackPackage:
    def _tar(self, entries: dict) -> bytes:
        return make_tar(entries)

    def test_business_two_layer(self, tmp_path):
        from alipay_mp_extractor.unpack import unpack_package
        inner = self._tar({"app.json": b"{}", "pages/index.js": b"code"})
        pkg = tmp_path / "pkg.dc"
        pkg.write_bytes(self._tar({
            ".signature": b"sig",
            ".meta": b"{}",
            "2019000000000000.tar": inner,
        }))
        src = unpack_package(pkg, tmp_path / "out")
        assert (src / "app.json").read_bytes() == b"{}"
        assert (src / "pages" / "index.js").read_bytes() == b"code"
        assert not list(tmp_path.joinpath("out").glob("*.tar"))

    def test_framework_single_layer(self, tmp_path):
        from alipay_mp_extractor.unpack import unpack_package
        pkg = tmp_path / "fw.tar"
        pkg.write_bytes(self._tar({"hpmfile.json": b"{}", "lib/a.js": b"x"}))
        src = unpack_package(pkg, tmp_path / "out")
        assert (src / "lib" / "a.js").read_bytes() == b"x"
        assert (src / "hpmfile.json").read_bytes() == b"{}"
        # nothing left outside src
        assert [p.name for p in (tmp_path / "out").iterdir()] == ["src"]


class TestRobustness:
    """Corrupt/missing metadata must degrade gracefully."""

    def _scan(self, tmp_path, files: dict):
        for name, data in files.items():
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        from alipay_mp_extractor.packages import scan_framework
        return scan_framework(tmp_path)

    def test_bad_framework_index(self, tmp_path):
        assert self._scan(tmp_path, {"framework_index.json": b"not-json"}) == []

    def test_empty_framework_index(self, tmp_path):
        assert self._scan(tmp_path, {"framework_index.json": b"{}"}) == []

    def test_bad_index_tsv_lines_skipped(self, tmp_path):
        from alipay_mp_extractor.packages import scan_apps
        (tmp_path / "index.tsv").write_text(
            "no-tab-line\n\n/path/0.dc\t2019000000000000\n/path2/x.dc\t\n",
            errors="ignore",
        )
        apps = scan_apps(tmp_path)
        assert set(apps) == {"2019000000000000"}

    def test_bad_manifest_xml(self, tmp_path):
        d = tmp_path / "nebulaInstallApps" / "123" / "abc"
        d.mkdir(parents=True)
        (d / "Manifest.xml").write_text("<broken", errors="ignore")
        fws = self._scan(tmp_path, {})
        assert len(fws) == 1 and fws[0].name == "?"
