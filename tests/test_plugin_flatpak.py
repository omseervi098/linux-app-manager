"""Flatpak plugin — mocked run_cmd + pure size/manifest helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from apphub.core.models import AppCategory, AppFormat
from apphub.plugins.flatpak import (
    FlatpakPlugin,
    _categorize_flatpak,
    _parse_flatpak_size,
)
from tests.conftest import make_manifest


def test_flatpak_helpers():
    assert _parse_flatpak_size("") is None
    assert _parse_flatpak_size("-") is None
    assert _parse_flatpak_size("1.5 MB") == int(1.5 * 1024**2)
    assert _parse_flatpak_size("bad") is None
    assert _categorize_flatpak("runtime/x", "x") == AppCategory.SYSTEM
    assert _categorize_flatpak("app/x", "x") == AppCategory.DESKTOP

    plugin = FlatpakPlugin()
    parts = [
        "Firefox",
        "org.mozilla.firefox",
        "128",
        "flathub",
        "Browser",
        "250 MB",
        "app/org.mozilla.firefox",
    ]
    m = plugin._manifest_from_list_line(parts, size_bytes=123)
    assert m is not None and m.name == "Firefox" and m.size_bytes == 123
    assert plugin._manifest_from_list_line(["a"], None) is None


@pytest.mark.asyncio
async def test_flatpak_lifecycle(tmp_path: Path):
    plugin = FlatpakPlugin()
    bundle = tmp_path / "a.flatpak"
    bundle.write_bytes(b"fp")
    row = (
        "Firefox\torg.mozilla.firefox\t128\tflathub\tBrowser\t250 MB"
        "\tapp/org.mozilla.firefox"
    )
    hist = "Jun\u2007 1 12:00:00\tinstall\torg.mozilla.firefox\tabc\t-"

    async def ok(*cmd):
        c = list(cmd)
        if c[:2] == ["flatpak", "list"]:
            return 0, row + "\n", ""
        if c[:3] == ["flatpak", "info", "--show-size"]:
            return 0, "1048576", ""
        if c[:2] == ["flatpak", "search"]:
            return 0, "Firefox\tBrowser\torg.mozilla.firefox\n", ""
        if c[:2] == ["flatpak", "info"]:
            return 0, "Name: Firefox\nID: org.mozilla.firefox\nVersion: 128\n", ""
        if c[:2] == ["flatpak", "history"]:
            return 0, hist + "\n", ""
        return 0, "", ""

    with patch("apphub.plugins.flatpak.run_cmd", side_effect=ok):
        apps = await plugin.list_apps()
        assert apps[0].name == "Firefox" and apps[0].size_bytes == 1048576
        assert (await plugin.search("f"))[0].id.endswith("firefox")
        assert (await plugin.inspect(str(bundle))).name == "Firefox"
        assert await plugin.inspect("x") is None
        assert await plugin.install("org.mozilla.firefox", True) is True
        assert await plugin.install(str(bundle), False) is True
        m = make_manifest("Firefox", fmt=AppFormat.FLATPAK)
        assert await plugin.uninstall(m, False) is True
        assert await plugin.uninstall(m, True) is True
        assert len(await plugin.history()) == 1

    async def human_size(*cmd):
        c = list(cmd)
        if c[:3] == ["flatpak", "info", "--show-size"]:
            return 0, "2.0 MB", ""
        if c[:2] == ["flatpak", "list"]:
            return 0, "A\tid\t1\torigin\td\t2.0 MB\tapp/id\n", ""
        return 1, "", ""

    with patch("apphub.plugins.flatpak.run_cmd", side_effect=human_size):
        assert (await plugin.list_apps())[0].size_bytes == int(2 * 1024**2)

    async def fail(*_):
        return 1, "", "e"

    with patch("apphub.plugins.flatpak.run_cmd", side_effect=fail):
        assert await plugin.install("x", False) is False
        assert (
            await plugin.uninstall(make_manifest(fmt=AppFormat.FLATPAK), False) is False
        )
        assert await plugin.history() == []

    async def boom(*_):
        raise RuntimeError("x")

    with patch("apphub.plugins.flatpak.run_cmd", side_effect=boom):
        assert await plugin.list_apps() == []
        assert await plugin.search("x") == []
        assert await plugin._get_exact_size("x") is None
