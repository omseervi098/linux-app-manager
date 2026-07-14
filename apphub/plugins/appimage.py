import configparser
import contextlib
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from apphub.core.models import (
    AppFormat,
    AppManifest,
    AppRuntime,
    HistoryRecords,
    LifeCycleEvent,
)
from apphub.core.runtime import detect_runtime_from_names, parse_appimage_stem
from apphub.core.utils import is_cmd_available, run_cmd
from apphub.plugins.base import PluginBase

# Common locations where AppImages are stored
_SEARCH_DIRS = [
    Path.home() / "Applications",
    Path.home() / ".local" / "share" / "applications",
    Path("/opt"),
    Path("/usr/local/bin"),
]

_HISTORY_LOGS_DIR = Path.home() / ".apphub" / "logs"
_ICON_CACHE_DIR = Path.home() / ".local/share/apphub/icons"


class AppImagePlugin(PluginBase):
    async def list_apps(self) -> list[AppManifest]:
        apps = []
        seen: set[str] = set()

        for directory in _SEARCH_DIRS:
            if not directory.exists():
                continue
            try:
                for entry in directory.iterdir():
                    if entry.suffix.lower() != ".appimage":
                        continue
                    if entry.name in seen:
                        continue
                    seen.add(entry.name)

                    with contextlib.suppress(Exception):
                        apps.append(await self.inspect(entry))
            except PermissionError as e:
                self.logger.warning(
                    f"Permission Error while listing apps across {directory}: {str(e)}"
                )
                continue

        return apps

    def _read_desktop_metadata(
        self, desktop: Path
    ) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        config = configparser.ConfigParser(interpolation=None)
        content = desktop.read_text(errors="ignore")
        if "[Desktop Entry]" not in content:
            content = "[Desktop Entry]\n" + content
        config.read_string(content)

        if not config.has_section("Desktop Entry"):
            return None, None, None, None, None

        entry = config["Desktop Entry"]
        publisher = (
            entry.get("X-AppImage-Publisher")
            or entry.get("X-AppImage-Author")
            or entry.get("X-AppImage-Developer")
        )
        return (
            entry.get("Name"),
            entry.get("Comment"),
            entry.get("Version"),
            publisher,
            entry.get("Icon"),
        )

    def _read_appstream_metadata(
        self, root_dir: Path
    ) -> tuple[str | None, str | None, str | None]:
        """Return (publisher, description, version) from AppStream metadata if present."""
        appstream_files = list(root_dir.rglob("*.appdata.xml")) + list(
            root_dir.rglob("*.metainfo.xml")
        )
        if not appstream_files:
            return None, None, None

        try:
            root = ET.parse(appstream_files[0]).getroot()
            publisher = description = version = None

            dev = root.find(".//developer_name")
            if dev is not None and dev.text:
                publisher = dev.text.strip()

            summary = root.find(".//summary")
            if summary is not None and summary.text:
                description = summary.text.strip()

            release = root.find(".//release")
            if release is not None:
                version = release.attrib.get("version")

            return publisher, description, version
        except Exception as e:
            self.logger.warning(f"AppImage AppStream parse failed: {e}")
            return None, None, None

    def _resolve_icon(
        self, root_dir: Path, icon_name: str | None, stem: str
    ) -> str | None:
        """Locate an icon under the extracted tree and cache it; return cache path."""
        icon_file = root_dir / ".DirIcon"
        if not icon_file.exists():
            candidates: list[Path] = []
            if icon_name:
                candidates.extend(root_dir.rglob(f"{icon_name}*.png"))
                candidates.extend(root_dir.rglob(f"{icon_name}*.svg"))
            if not candidates:
                candidates = list(root_dir.rglob("*.png")) + list(
                    root_dir.rglob("*.svg")
                )
            if candidates:
                icon_file = max(
                    candidates,
                    key=lambda p: p.stat().st_size if p.exists() else 0,
                )

        if not icon_file.exists():
            return None

        _ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_icon = _ICON_CACHE_DIR / f"appimage_{stem}{icon_file.suffix}"
        shutil.copy2(icon_file, cached_icon)
        return str(cached_icon)

    async def _extract_embedded_metadata(
        self, path: Path
    ) -> tuple[str, str | None, str, str, str | None, AppRuntime]:
        """Extract (name, description, version, publisher, icon_path, runtime)."""
        name, version = parse_appimage_stem(path.stem)
        description = None
        publisher = "unknown"
        runtime = AppRuntime.NATIVE
        icon_path = None

        if not is_cmd_available("unsquashfs"):
            return name, description, version, publisher, icon_path, runtime

        try:
            if not os.access(path, os.X_OK):
                path.chmod(path.stat().st_mode | 0o111)
            _, stdout, _ = await run_cmd(str(path), "--appimage-offset")
            offset = int(stdout.strip())

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                await run_cmd(
                    "unsquashfs",
                    "-f",
                    "-q",
                    "-o",
                    str(offset),
                    "-d",
                    str(tmp_path),
                    str(path),
                    "*.desktop",
                    ".DirIcon",
                    "usr/share/icons/*",
                    "resources/*",
                    "usr/lib/*",
                    "usr/lib64/*",
                    "usr/share/metainfo/*",
                    "usr/share/appdata/*",
                    "*.jar",
                    "*.json",
                    "*.asar",
                )
                files = [f for f in tmp_path.rglob("*") if f.is_file()]
                names = {f.name for f in files}
                runtime = detect_runtime_from_names(names)

                desktop = next(tmp_path.rglob("*.desktop"), None)
                icon_name = None
                if desktop:
                    d_name, d_desc, d_ver, d_pub, icon_name = (
                        self._read_desktop_metadata(desktop)
                    )
                    if d_name:
                        name = d_name
                    if d_desc:
                        description = d_desc
                    if d_ver and version == "unknown":
                        version = d_ver
                    if d_pub:
                        publisher = d_pub

                    a_pub, a_desc, a_ver = self._read_appstream_metadata(tmp_path)
                    if publisher == "unknown" and a_pub:
                        publisher = a_pub
                    if description is None and a_desc:
                        description = a_desc
                    if version == "unknown" and a_ver:
                        version = a_ver

                icon_path = self._resolve_icon(tmp_path, icon_name, path.stem)

        except Exception as e:
            self.logger.warning(f"AppImage metadata extraction failed: {e}")

        return name, description, version, publisher, icon_path, runtime

    async def inspect(self, path: Path) -> AppManifest:
        if not path.exists():
            raise FileNotFoundError(f"AppImage file not found: {path}")

        size_bytes = None
        with contextlib.suppress(OSError):
            size_bytes = path.stat().st_size

        name, description, version, publisher, icon_path, runtime = (
            await self._extract_embedded_metadata(path)
        )

        return AppManifest(
            name=name,
            id=f"appimage:{path.name}",
            format=AppFormat.APPIMAGE,
            version=version,
            installed=False,
            publisher=publisher,
            size_bytes=size_bytes,
            description=description,
            icon=icon_path,
            runtime=runtime,
        )

    async def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path).resolve()
        if not path.exists():
            self.logger.error(f"Path does not exist: {path}")
            raise FileNotFoundError

        apps_dir = Path.home() / "Applications"
        apps_dir.mkdir(parents=True, exist_ok=True)

        dest_path = apps_dir / path.name

        if path != dest_path:
            try:
                shutil.copy2(path, dest_path)
                self.logger.info(f"Copied {path.name} to {apps_dir}")
            except Exception as e:
                self.logger.error(f"Failed to copy AppImage: {e}")
                raise

        try:
            dest_path.chmod(dest_path.stat().st_mode | 0o111)
        except Exception as e:
            self.logger.error(f"Failed to set executable permission: {e}")
            raise

        await self._create_desktop_entry(dest_path)

        try:
            manifest = await self.inspect(dest_path)
            self._record_history(
                LifeCycleEvent.INSTALLED,
                app_name=manifest.name,
                app_id=manifest.id,
                version_id=manifest.version,
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to record install history for {dest_path.name}: {e}"
            )

        if launch:
            try:
                desktop_id = f"apphub-{dest_path.stem}.desktop"
                await run_cmd("gtk-launch", desktop_id)
            except Exception as e:
                self.logger.error(f"Failed to launch app: {e}")

        return True

    async def _create_desktop_entry(self, app_path: Path):
        desktop_dir = Path.home() / ".local/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        manifest = await self.inspect(app_path)

        name = manifest.name
        icon = manifest.icon or "utilities-terminal"

        desktop_file = desktop_dir / f"apphub-{app_path.stem}.desktop"
        exec_cmd = str(app_path)

        if manifest.runtime == AppRuntime.ELECTRON:
            exec_cmd += " --no-sandbox"

        exec_cmd += " %U"

        content = [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={name}",
            f"Exec={exec_cmd}",
            f"TryExec={app_path}",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=Utility;",
            "Comment=Installed via AppHub Terminal",
            f"X-AppHub-Path={app_path}",
        ]

        try:
            desktop_file.write_text("\n".join(content) + "\n")
            await run_cmd("update-desktop-database", str(desktop_dir))
            self.logger.info(f"Created desktop entry: {desktop_file}")
        except Exception as e:
            self.logger.error(f"Failed to create desktop entry: {e}")
            raise

    def _record_history(
        self,
        event: LifeCycleEvent,
        app_name: str,
        app_id: str,
        version_id: str | None = None,
    ):
        history_file = _HISTORY_LOGS_DIR / "appimage_history.jsonl"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "format": AppFormat.APPIMAGE.value,
            "lifecycle_event": event.value,
            "app_name": app_name,
            "app_id": app_id,
            "version_id": version_id,
        }
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _remove_sidecar_files(self, app_path: Path) -> None:
        desktop_file = (
            Path.home()
            / ".local/share/applications"
            / f"apphub-{app_path.stem}.desktop"
        )
        if desktop_file.exists():
            try:
                desktop_file.unlink()
                self.logger.info(f"Removed desktop entry: {desktop_file}")
            except Exception as e:
                self.logger.warning(f"Failed to remove desktop entry: {e}")

        if _ICON_CACHE_DIR.exists():
            try:
                for icon in _ICON_CACHE_DIR.glob(f"appimage_{app_path.stem}*"):
                    icon.unlink()
                    self.logger.info(f"Removed icon: {icon}")
            except Exception as e:
                self.logger.warning(f"Failed to remove icons: {e}")

    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        apps_dir = Path.home() / "Applications"
        app_filename = (
            app_info.id.split(":", 1)[1] if ":" in app_info.id else app_info.name
        )
        app_path = apps_dir / app_filename

        removed = False
        if app_path.exists():
            try:
                app_path.unlink()
                self.logger.info(f"Removed AppImage: {app_path}")
                removed = True
            except Exception as e:
                self.logger.error(f"Failed to remove AppImage: {e}")
                return False
        else:
            removed = True

        if clean_uninstall:
            self._remove_sidecar_files(app_path)

        if removed:
            try:
                self._record_history(
                    LifeCycleEvent.UNINSTALLED,
                    app_name=app_info.name,
                    app_id=app_info.id,
                    version_id=app_info.version,
                )
            except Exception as e:
                self.logger.warning(f"Failed to record uninstall history: {e}")

        return True

    async def history(
        self, action_categories: list[LifeCycleEvent] | None = None
    ) -> list[HistoryRecords]:
        history_file = _HISTORY_LOGS_DIR / "appimage_history.jsonl"
        if not history_file.exists():
            return []

        records = []
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        event = LifeCycleEvent(data["lifecycle_event"])
                        if action_categories and event not in action_categories:
                            continue
                        records.append(
                            HistoryRecords(
                                timestamp=datetime.fromisoformat(data["timestamp"]),
                                format=AppFormat.APPIMAGE,
                                lifecycle_event=event,
                                app_name=data.get("app_name"),
                                app_id=data.get("app_id"),
                                version_id=data.get("version_id"),
                            )
                        )
                    except Exception as e:
                        self.logger.warning(f"Error parsing history line: {e}")
        except Exception as e:
            self.logger.error(f"Failed to read AppImage history: {e}")
        return records
