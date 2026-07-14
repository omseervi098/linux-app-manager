from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from apphub.cli.serializers import to_json, to_json_single
from apphub.core.exceptions import AppNotFoundError, InstallError, UninstallError
from apphub.core.hub import AppHubCore, filter_manifests
from apphub.core.models import (
    AppCategory,
    AppFormat,
    AppRuntime,
    DistroInfo,
    HistoryRecords,
    LifeCycleEvent,
)
from apphub.core.runtime import detect_runtime_from_names, parse_appimage_stem
from apphub.core.utils import (
    detect_distro_info,
    detect_format,
    is_cmd_available,
    run_cmd,
)
from tests.conftest import make_manifest

# ── pure helpers ──────────────────────────────────────────────────────────────


def test_runtime_and_stem_parsing():
    assert parse_appimage_stem("Cool-App-2.0-x86_64") == ("Cool App", "2.0")
    assert parse_appimage_stem("JustName") == ("JustName", "unknown")
    assert parse_appimage_stem("App-amd64") == ("App", "unknown")
    assert detect_runtime_from_names({"chrome-sandbox"}) == AppRuntime.ELECTRON
    assert detect_runtime_from_names({"app.asar"}) == AppRuntime.ELECTRON
    assert detect_runtime_from_names({"libtauri.so"}) == AppRuntime.TAURI
    assert detect_runtime_from_names({"x.jar"}) == AppRuntime.JAVA
    assert detect_runtime_from_names({"package.json"}) == AppRuntime.NODE
    assert detect_runtime_from_names({"node_modules"}) == AppRuntime.NODE
    assert detect_runtime_from_names({"libcef.so"}) == AppRuntime.CHROMIUM
    assert detect_runtime_from_names({"chrome"}) == AppRuntime.CHROMIUM
    assert detect_runtime_from_names({"main.py"}) == AppRuntime.PYTHON
    assert detect_runtime_from_names({"site-packages"}) == AppRuntime.PYTHON
    assert detect_runtime_from_names({"bin"}) == AppRuntime.NATIVE


def test_utils_distro_format_cmd(tmp_path: Path):
    content = 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="24.04"\n'
    detect_distro_info.cache_clear()
    with patch("builtins.open", mock_open(read_data=content)):
        info = detect_distro_info()
    assert info.id == "ubuntu"
    detect_distro_info.cache_clear()

    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(Exception, match="os-release"):
            detect_distro_info()
    detect_distro_info.cache_clear()

    deb = tmp_path / "p.deb"
    deb.write_bytes(b"")
    assert detect_format(str(deb)) == AppFormat.DEBIAN
    ai = tmp_path / "A.AppImage"
    ai.write_bytes(b"")
    assert detect_format(str(ai)) == AppFormat.APPIMAGE
    with pytest.raises(Exception):
        detect_format(str(tmp_path / "missing.deb"))
    weird = tmp_path / "f.xyz"
    weird.write_bytes(b"")
    with pytest.raises(Exception):
        detect_format(str(weird))

    with patch("apphub.core.utils.shutil.which", return_value="/bin/x"):
        assert is_cmd_available("x") is True
    with patch("apphub.core.utils.shutil.which", return_value=None):
        assert is_cmd_available("x") is False


@pytest.mark.asyncio
async def test_run_cmd_decode():
    class Proc:
        returncode = 0

        async def communicate(self):
            return b"out", b"err"

    with patch(
        "apphub.core.utils.asyncio.create_subprocess_exec",
        return_value=Proc(),
    ):
        code, out, err = await run_cmd("echo")
    assert (code, out, err) == (0, "out", "err")


def test_exceptions_and_serializers():
    assert "vlc" in str(AppNotFoundError("vlc"))
    assert "network" in str(InstallError("a", reason="network"))
    assert "a" in str(InstallError("a"))
    assert "b" in str(UninstallError("b"))
    assert "why" in str(UninstallError("b", reason="why"))
    app = make_manifest("A", fmt=AppFormat.DEBIAN)
    assert "A" in to_json([app])
    assert "A" in to_json_single(app)


def test_filter_manifests():
    apps = [
        make_manifest("Firefox"),
        make_manifest("systemd", category=AppCategory.SYSTEM),
        make_manifest("Chrome"),
    ]
    assert [a.name for a in filter_manifests(apps, query="fire")] == ["Firefox"]
    assert all(
        a.category != AppCategory.SYSTEM
        for a in filter_manifests(apps, exclude_defaults=True)
    )


# ── hub ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def hub():
    with (
        patch(
            "apphub.core.hub.detect_distro_info",
            return_value=DistroInfo(name="Ubuntu", id="ubuntu", version_id="24.04"),
        ),
        patch("apphub.core.hub.is_cmd_available", return_value=True),
        patch("apphub.core.hub.AptPlugin"),
        patch("apphub.core.hub.AppImagePlugin"),
        patch("apphub.core.hub.FlatpakPlugin"),
        patch("apphub.core.hub.SnapPlugin"),
    ):
        h = AppHubCore()
        fp = MagicMock()
        sn = MagicMock()
        apt = MagicMock()
        ai = MagicMock()

        fp.list_apps = AsyncMock(return_value=[make_manifest("Firefox", size_bytes=10)])
        sn.list_apps = AsyncMock(
            return_value=[make_manifest("vlc", fmt=AppFormat.SNAP, size_bytes=100)]
        )
        apt.list_apps = AsyncMock(
            return_value=[
                make_manifest(
                    "coreutils", fmt=AppFormat.DEBIAN, category=AppCategory.SYSTEM
                )
            ]
        )
        ai.list_apps = AsyncMock(return_value=[])

        fp.search = AsyncMock(return_value=[make_manifest("Firefox")])
        sn.search = AsyncMock(return_value=[])
        apt.search = AsyncMock(side_effect=NotImplementedError())
        ai.search = AsyncMock(side_effect=NotImplementedError())

        fp.install = AsyncMock(return_value=True)
        sn.install = AsyncMock(side_effect=RuntimeError("boom"))
        fp.uninstall = AsyncMock(return_value=True)
        sn.uninstall = AsyncMock(side_effect=RuntimeError("boom"))

        fp.history = AsyncMock(
            return_value=[
                HistoryRecords(
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    format=AppFormat.FLATPAK,
                    lifecycle_event=LifeCycleEvent.INSTALLED,
                    app_name="Firefox",
                )
            ]
        )
        sn.history = AsyncMock(return_value=[])
        apt.history = AsyncMock(return_value=None)
        ai.history = AsyncMock(side_effect=RuntimeError("hist"))
        fp.inspect = AsyncMock(return_value=make_manifest("Firefox"))

        h.plugins = {
            AppFormat.FLATPAK: fp,
            AppFormat.SNAP: sn,
            AppFormat.DEBIAN: apt,
            AppFormat.APPIMAGE: ai,
        }
        yield h


@pytest.mark.asyncio
async def test_hub_orchestration(hub, tmp_path: Path):
    apps = await hub.list_apps()
    assert {a.name for a in apps} >= {"Firefox", "vlc", "coreutils"}
    assert (await hub.list_apps(query="fire", exclude_defaults=True))[
        0
    ].name == "Firefox"
    assert all(
        a.format == AppFormat.SNAP
        for a in await hub.list_apps(formats=[AppFormat.SNAP])
    )
    assert any(a.name == "Firefox" for a in await hub.search("fire"))
    assert (await hub.storage(top=1))[0].name == "vlc"
    assert len(await hub.history()) == 1
    assert await hub.install("Firefox", AppFormat.FLATPAK) is True
    with pytest.raises(InstallError):
        await hub.install("x", AppFormat.SNAP)
    assert await hub.uninstall(make_manifest("Firefox"), False) is True
    with pytest.raises(UninstallError):
        await hub.uninstall(make_manifest("vlc", fmt=AppFormat.SNAP), False)
    with pytest.raises(AppNotFoundError):
        hub.list_apps = AsyncMock(return_value=[])
        await hub.info("missing")
    hub.list_apps = AsyncMock(
        return_value=[make_manifest("Fire"), make_manifest("Firefox")]
    )
    assert (await hub.info("Firefox")).name == "Firefox"
    f = tmp_path / "a.flatpak"
    f.write_bytes(b"x")
    with patch("apphub.core.hub.detect_format", return_value=AppFormat.FLATPAK):
        assert (await hub.inspect(str(f))).name == "Firefox"
