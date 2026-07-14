"""Snap plugin — mocked run_cmd + pure history/meta helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from apphub.core.models import AppCategory, AppFormat, LifeCycleEvent
from apphub.plugins.snap import SnapPlugin
from tests.conftest import make_manifest


@pytest.mark.asyncio
async def test_snap_lifecycle(tmp_path: Path):
    plugin = SnapPlugin()
    snap = tmp_path / "vlc.snap"
    snap.write_bytes(b"x")

    async def ok(*cmd):
        c = list(cmd)
        if c[:2] == ["snap", "list"]:
            return (
                0,
                "Name Version Rev Tracking Publisher Notes\n"
                "vlc 3.0 1 latest/stable videolan* -\n",
                "",
            )
        if c[:2] == ["snap", "find"]:
            return (
                0,
                "Name Version Publisher Notes Summary\n" "vlc 3.0 videolan* - media\n",
                "",
            )
        if c[:2] == ["snap", "info"]:
            return 0, "name: vlc\nversion: 3.0\npublisher: v\nsummary: m\n", ""
        if c[:2] == ["snap", "changes"]:
            return (
                0,
                '1 Done 2026-06-01T10:00:00Z 2026-06-01T10:00:05Z Install "vlc" snap\n',
                "",
            )
        if "unsquashfs" in c:
            return 0, 'name: foo\nversion: "2"\nsummary: bar\n', ""
        return 0, "", ""

    with (
        patch("apphub.plugins.snap.run_cmd", side_effect=ok),
        patch.object(
            plugin, "_read_snap_meta", return_value=("m", AppCategory.DESKTOP)
        ),
        patch.object(plugin, "_get_snap_size", return_value=10),
    ):
        assert (await plugin.list_apps())[0].name == "vlc"
        assert (await plugin.search("vlc"))[0].name == "vlc"
        assert (await plugin.inspect(str(snap))).name == "vlc"
        assert await plugin.install("vlc", False) is True
        assert await plugin.install(str(snap), False) is True
        assert await plugin.uninstall(make_manifest("vlc", fmt=AppFormat.SNAP), True)
        assert len(await plugin.history()) == 1

    async def info_fail(*cmd):
        if list(cmd)[:2] == ["snap", "info"]:
            return 1, "", "x"
        if "unsquashfs" in cmd:
            return 0, 'name: foo\nversion: "2"\nsummary: bar\n', ""
        return 1, "", ""

    with (
        patch("apphub.plugins.snap.run_cmd", side_effect=info_fail),
        patch("apphub.plugins.snap.is_cmd_available", return_value=True),
    ):
        assert (await plugin.inspect(str(snap))).name == "foo"

    async def fail(*_):
        return 1, "", "no"

    with patch("apphub.plugins.snap.run_cmd", side_effect=fail):
        assert await plugin.install("x", False) is False
        assert await plugin.uninstall(make_manifest(fmt=AppFormat.SNAP), False) is False
        assert await plugin.history() == []

    async def install_ok_launch_fail(*cmd):
        if list(cmd)[:3] == ["sudo", "snap", "install"]:
            return 0, "", ""
        return 1, "", "no launch"

    with patch("apphub.plugins.snap.run_cmd", side_effect=install_ok_launch_fail):
        assert await plugin.install("vlc", launch=True) is False

    async def boom(*_):
        raise RuntimeError("down")

    with patch("apphub.plugins.snap.run_cmd", side_effect=boom):
        assert await plugin.list_apps() == []
        assert await plugin.search("x") == []
        assert await plugin.inspect("x") is None


def test_snap_history_lines():
    plugin = SnapPlugin()
    ok = "123  Done  2026-06-01T10:00:00Z  2026-06-01T10:00:05Z  " 'Install "vlc" snap'
    recs = plugin._parse_snap_change_line(ok, None)
    assert len(recs) == 1
    assert recs[0].app_name == "vlc"
    assert recs[0].lifecycle_event == LifeCycleEvent.INSTALLED
    assert plugin._parse_snap_change_line("ID Status ...", None) == []
    assert (
        plugin._parse_snap_change_line(
            ok.replace("Install", "Remove"), [LifeCycleEvent.INSTALLED]
        )
        == []
    )


def test_snap_meta_and_size(tmp_path: Path):
    plugin = SnapPlugin()
    name = "myapp"
    meta = tmp_path / "snap.yaml"
    meta.write_text("summary: cool\ntype: app\n")
    gui = tmp_path / "gui"
    gui.mkdir()
    (gui / "a.desktop").write_text("[Desktop Entry]\n")
    blob = tmp_path / "myapp_9.snap"
    blob.write_bytes(b"1234")
    orig = Path

    def path_factory(arg=None, *a, **k):
        mapping = {
            f"/snap/{name}/current/meta/snap.yaml": meta,
            f"/snap/{name}/current/meta/gui": gui,
            f"/var/lib/snapd/snaps/{name}_9.snap": blob,
        }
        if arg in mapping:
            return mapping[arg]
        return orig() if arg is None else orig(arg, *a, **k)

    with patch("apphub.plugins.snap.Path", path_factory):
        s, cat = plugin._read_snap_meta(name)
        assert s == "cool" and cat == AppCategory.DESKTOP
        assert plugin._get_snap_size(name, "9") == 4
        meta.write_text("summary: c\ntype: base\n")
        assert plugin._read_snap_meta(name)[1] == AppCategory.SYSTEM
