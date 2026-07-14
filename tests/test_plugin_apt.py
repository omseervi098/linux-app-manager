"""APT plugin — mocked run_cmd + history log parsing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from apphub.core.models import AppFormat, LifeCycleEvent
from apphub.plugins.apt import AptPlugin
from tests.conftest import make_manifest


def test_apt_history_parsing(tmp_path: Path):
    plugin = AptPlugin()
    entry = "Start-Date: 2026-01-10 12:00:00\nInstall: foo:amd64 (1.0.0)"
    data = plugin._parse_log_entry(entry)
    recs = plugin._records_from_entry(data, None)
    assert len(recs) == 1
    assert recs[0].app_name == "foo"
    assert recs[0].timestamp == datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert plugin._records_from_entry(data, [LifeCycleEvent.UNINSTALLED]) == []

    up = plugin._parse_log_entry(
        "Start-Date: 2026-01-11 09:30:00\nUpgrade: bar:amd64 (1.0, 2.0)"
    )
    urecs = plugin._records_from_entry(up, None)
    assert urecs[0].lifecycle_event == LifeCycleEvent.UPGRADED
    assert urecs[0].old_version_id == "1.0"

    log = tmp_path / "history.log"
    log.write_text(
        "Start-Date: 2026-01-10 12:00:00\nInstall: foo:amd64 (1.0.0)\n\n"
        "Start-Date: 2026-01-11 09:30:00\nUpgrade: bar:amd64 (1.0, 2.0)\n\n"
        "Start-Date: 2026-01-12 08:00:00\nRemove: baz:amd64 (3.0.0)\n",
        encoding="utf-8",
    )
    plugin.LOG_FILE_PATH = str(log)
    assert len(asyncio.run(plugin.history())) == 3
    assert plugin._detect_category("required", "admin", "x").value == "system"
    assert plugin._detect_category("optional", "utils", "jq").value == "cli"


@pytest.mark.asyncio
async def test_apt_lifecycle(tmp_path: Path):
    plugin = AptPlugin()
    deb = tmp_path / "pkg.deb"
    deb.write_bytes(b"deb")
    fields = (
        "Package: foo\nVersion: 1.2.3\nMaintainer: Dev\n"
        "Description: hello\nInstalled-Size: 10\n"
    )
    listing = (
        "-rw-r--r-- root/root 100 2020-01-01 00:00 ./usr/share/icons/hicolor/i.png\n"
        "-rw-r--r-- root/root 1 2020-01-01 00:00 ./usr/lib/chrome-sandbox\n"
    )

    async def ok(*cmd):
        c = list(cmd)
        if c[:2] == ["apt-mark", "showmanual"]:
            return 0, "foo\nlibfoo\nbar-dev\n", ""
        if c[0] == "dpkg-query":
            return 0, "foo|1.2.3|Dev|10|hello\n", ""
        if c[:2] == ["dpkg-deb", "-f"]:
            return 0, fields, ""
        if c[:2] == ["dpkg-deb", "-c"]:
            return 0, listing, ""
        if c[:2] == ["dpkg-deb", "-x"]:
            dest = Path(c[3])
            icon = dest / "usr/share/icons/hicolor/i.png"
            icon.parent.mkdir(parents=True, exist_ok=True)
            icon.write_bytes(b"PNG")
            return 0, "", ""
        if c[:2] == ["dpkg", "-L"]:
            return 0, "/usr/share/applications/foo.desktop\n", ""
        return 0, "", ""

    with patch("apphub.plugins.apt.run_cmd", side_effect=ok):
        names = {a.name for a in await plugin.list_apps()}
        assert "foo" in names and "libfoo" not in names
        info = await plugin.inspect(deb)
        assert info.name == "foo" and info.runtime.value == "electron"
        assert await plugin.install(str(deb), True) is True
        assert await plugin.uninstall(make_manifest("foo", fmt=AppFormat.DEBIAN), True)

    async def bulk_fail(*cmd):
        if list(cmd)[0] == "dpkg-query":
            return 1, "", "e"
        if list(cmd)[:2] == ["apt-mark", "showmanual"]:
            return 0, "only\n", ""
        return 1, "", ""

    with patch("apphub.plugins.apt.run_cmd", side_effect=bulk_fail):
        assert (await plugin.list_apps())[0].version == "-"

    async def boom(*_):
        raise RuntimeError("x")

    with patch("apphub.plugins.apt.run_cmd", side_effect=boom):
        assert await plugin.list_apps() == []
        assert await plugin._get_app_manifest_in_bulk(["a"]) == []

    with patch("apphub.plugins.apt.run_cmd", side_effect=lambda *_: (1, "", "e")):
        assert (
            await plugin.uninstall(make_manifest(fmt=AppFormat.DEBIAN), False) is False
        )
