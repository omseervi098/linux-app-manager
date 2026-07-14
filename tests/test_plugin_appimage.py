"""AppImage plugin — filesystem lifecycle + mocked unsquashfs extract."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from apphub.core.models import AppFormat, AppManifest, LifeCycleEvent
from apphub.plugins.appimage import AppImagePlugin


@pytest.mark.asyncio
async def test_appimage_lifecycle(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    import apphub.plugins.appimage as ai_mod

    apps_dir = home / "Applications"
    apps_dir.mkdir(parents=True)
    monkeypatch.setattr(ai_mod, "_SEARCH_DIRS", [apps_dir])
    monkeypatch.setattr(ai_mod, "_HISTORY_LOGS_DIR", home / ".apphub" / "logs")
    monkeypatch.setattr(ai_mod, "_ICON_CACHE_DIR", home / "icons")

    plugin = AppImagePlugin()
    src = tmp_path / "CoolApp-1.2.3-x86_64.AppImage"
    src.write_bytes(b"AI")
    (apps_dir / src.name).write_bytes(b"AI")

    with (
        patch("apphub.plugins.appimage.run_cmd", return_value=(0, "", "")),
        patch("apphub.plugins.appimage.is_cmd_available", return_value=False),
    ):
        info = await plugin.inspect(src)
        assert info.name == "CoolApp" and info.version == "1.2.3"
        assert any(a.name == "CoolApp" for a in await plugin.list_apps())

        other = tmp_path / "Other-2.0.AppImage"
        other.write_bytes(b"AI2")
        assert await plugin.install(str(other), True) is True
        dest = apps_dir / other.name
        assert dest.exists()
        assert any(
            r.lifecycle_event == LifeCycleEvent.INSTALLED
            for r in await plugin.history()
        )
        m = AppManifest(
            name="Other",
            id=f"appimage:{other.name}",
            version="2.0",
            format=AppFormat.APPIMAGE,
        )
        assert await plugin.uninstall(m, True) is True
        assert not dest.exists()

    # unsquashfs + desktop metadata
    app = tmp_path / "FooApp.AppImage"
    app.write_bytes(b"AI")
    app.chmod(0o755)

    async def extract(*cmd):
        c = list(cmd)
        if c[-1] == "--appimage-offset" or (
            len(c) == 2 and c[1] == "--appimage-offset"
        ):
            return 0, "100\n", ""
        if c[0] == "unsquashfs":
            dest = Path(c[c.index("-d") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "foo.desktop").write_text(
                "[Desktop Entry]\nName=Foo Desktop\nComment=c\n"
                "Version=9.9\nIcon=foo\nX-AppImage-Publisher=PubCo\n"
            )
            (dest / "foo.png").write_bytes(b"PNG")
            (dest / "chrome-sandbox").write_bytes(b"x")
            return 0, "", ""
        return 0, "", ""

    with (
        patch("apphub.plugins.appimage.run_cmd", side_effect=extract),
        patch("apphub.plugins.appimage.is_cmd_available", return_value=True),
        patch("apphub.plugins.appimage.os.access", return_value=True),
    ):
        info = await plugin.inspect(app)
        assert info.name == "Foo Desktop"
        assert info.publisher == "PubCo"
        assert info.runtime.value == "electron"

    # helpers + history edge cases
    desktop = tmp_path / "a.desktop"
    desktop.write_text(
        "Name=Bare\nComment=c\nVersion=3\nIcon=i\nX-AppImage-Author=Me\n"
    )
    assert plugin._read_desktop_metadata(desktop)[0] == "Bare"
    (tmp_path / "app.metainfo.xml").write_text(
        "<component><developer_name>DevX</developer_name>"
        '<summary>Sum</summary><release version="4.0"/></component>'
    )
    assert plugin._read_appstream_metadata(tmp_path)[0] == "DevX"
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "b.png").write_bytes(b"12345")
    assert plugin._resolve_icon(tree, None, "s") is not None

    hist = home / ".apphub" / "logs" / "appimage_history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text(
        "\nbad\n"
        + json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "lifecycle_event": "installed",
                "app_name": "A",
                "app_id": "appimage:A",
                "version_id": "1",
            }
        )
        + "\n"
    )
    assert len(await plugin.history()) >= 1
    assert await plugin.history([LifeCycleEvent.UNINSTALLED]) == []
    with pytest.raises(FileNotFoundError):
        await plugin.inspect(tmp_path / "no.AppImage")
