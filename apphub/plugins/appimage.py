import contextlib
import os
import shutil
import subprocess
from pathlib import Path

from apphub.core.models import AppFormat, AppManifest, AppRuntime
from apphub.core.utils import is_cmd_available
from apphub.plugins.base import PluginBase

# Common locations where AppImages are stored
_SEARCH_DIRS = [
    Path.home() / "Applications",
    Path.home() / ".local" / "share" / "applications",
    Path("/opt"),
    Path("/usr/local/bin"),
]


class AppImagePlugin(PluginBase):

    def list_apps(self) -> list[AppManifest]:
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
                        apps.append(self.inspect(entry))
            except PermissionError as e:
                self.logger.warning(f"Permission Error while listing apps across {directory}: {str(e)}")
                continue

        return apps

    def inspect(self, path: Path) -> AppManifest:
        if not path.exists():
            raise FileNotFoundError(f"AppImage file not found: {path}")

        stem = path.stem
        parts = stem.split("-")

        name_parts: list[str] = []
        version = "unknown"

        for part in parts:
            if part.lower() in {"x86_64", "amd64", "arm64", "aarch64"}:
                break
            if part and part[0].isdigit():
                version = part
                break
            name_parts.append(part)

        name = " ".join(name_parts) if name_parts else stem

        size_bytes: int | None = None
        with contextlib.suppress(OSError):
            size_bytes = path.stat().st_size

        description = None
        icon_path = None
        publisher = "unknown"
        runtime = AppRuntime.NATIVE
        if is_cmd_available("unsquashfs"):
            try:
                if not os.access(path, os.X_OK):
                    path.chmod(path.stat().st_mode | 0o111)

                offset = int(
                    subprocess.check_output([str(path), "--appimage-offset"])
                    .decode()
                    .strip()
                )

                import tempfile
                import configparser

                with tempfile.TemporaryDirectory() as tmp:
                    tmp_path = Path(tmp)

                    subprocess.run(
                        [
                            "unsquashfs",
                            "-f",
                            "-q",
                            "-o", str(offset),
                            "-d", str(tmp_path),
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
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                    files = [f for f in tmp_path.rglob("*") if f.is_file()]
                    names = {f.name for f in files}

                    if (
                        "chrome-sandbox" in names
                        or "libnode.so" in names
                        or any(n.endswith(".asar") for n in names)
                    ):
                        runtime = AppRuntime.ELECTRON

                    elif any("tauri" in n.lower() for n in names):
                        runtime = AppRuntime.TAURI

                    elif any(n.endswith(".jar") for n in names):
                        runtime = AppRuntime.JAVA

                    elif "site-packages" in names and any(n.endswith(".py") for n in names):
                        runtime = AppRuntime.PYTHON

                    elif "package.json" in names or "node_modules" in names:
                        runtime = AppRuntime.NODE

                    elif "libcef.so" in names or "chrome" in names:
                        runtime = AppRuntime.CHROMIUM

                    desktop = next(tmp_path.rglob("*.desktop"), None)

                    icon_name = None

                    if desktop:

                        config = configparser.ConfigParser(interpolation=None)
                        content = desktop.read_text(errors="ignore")

                        if "[Desktop Entry]" not in content:
                            content = "[Desktop Entry]\n" + content

                        config.read_string(content)

                        if config.has_section("Desktop Entry"):
                            entry = config["Desktop Entry"]

                            publisher = (
                                entry.get("X-AppImage-Publisher")
                                or entry.get("X-AppImage-Author")
                                or entry.get("X-AppImage-Developer")
                                or publisher
                            )
                            
                            name = entry.get("Name", name)
                            description = entry.get("Comment", description)

                            if version == "unknown":
                                version = entry.get("Version", version)

                            icon_name = entry.get("Icon")
                        
                        import xml.etree.ElementTree as ET

                        appstream_files = (
                            list(tmp_path.rglob("*.appdata.xml")) +
                            list(tmp_path.rglob("*.metainfo.xml"))
                        )

                        if appstream_files:
                            try:
                                tree = ET.parse(appstream_files[0])
                                root = tree.getroot()

                                if publisher == "unknown":
                                    dev = root.find(".//developer_name")
                                    if dev is not None and dev.text:
                                        publisher = dev.text.strip()

                                if description is None:
                                    summary = root.find(".//summary")
                                    if summary is not None and summary.text:
                                        description = summary.text.strip()

                                if version == "unknown":
                                    release = root.find(".//release")
                                    if release is not None:
                                        version = release.attrib.get("version", version)

                            except Exception:
                                pass

                    icon_file = tmp_path / ".DirIcon"

                    if not icon_file.exists():
                        candidates = []

                        if icon_name:
                            candidates.extend(
                                tmp_path.rglob(f"{icon_name}*.png"))
                            candidates.extend(
                                tmp_path.rglob(f"{icon_name}*.svg"))

                        # fallback: pick largest png
                        if not candidates:
                            candidates = list(tmp_path.rglob(
                                "*.png")) + list(tmp_path.rglob("*.svg"))

                        if candidates:
                            icon_file = max(candidates, key=lambda p: p.stat().st_size if p.exists() else 0)

                    if icon_file.exists():
                        cache = Path.home() / ".local/share/apphub/icons"
                        cache.mkdir(parents=True, exist_ok=True)

                        cached_icon = cache / \
                            f"appimage_{path.stem}{icon_file.suffix}"
                        shutil.copy2(icon_file, cached_icon)
                        icon_path = str(cached_icon)

            except Exception as e:
                self.logger.warning(f"AppImage metadata extraction failed: {e}")

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
            runtime=runtime
        )
    
    def install(self, query_or_path: str, launch: bool) -> bool:
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

        self._create_desktop_entry(dest_path)

        if launch:
            try:
                # Use gtk-launch to ensure it uses the desktop entry logic
                desktop_id = f"apphub-{dest_path.stem}.desktop"
                subprocess.Popen(["gtk-launch", desktop_id], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                self.logger.error(f"Failed to launch app: {e}")

        return True

    def _create_desktop_entry(self, app_path: Path):
        desktop_dir = Path.home() / ".local/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        manifest = self.inspect(app_path)

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

            subprocess.run(
                ["update-desktop-database", str(desktop_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.logger.info(f"Created desktop entry: {desktop_file}")
        except Exception as e:
            self.logger.error(f"Failed to create desktop entry: {e}")
            raise