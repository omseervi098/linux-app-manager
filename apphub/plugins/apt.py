import shutil
import subprocess
import tempfile
from pathlib import Path

from apphub.core.exceptions import PluginNotAvailableError
from apphub.core.models import AppCategory, AppFormat, AppManifest, AppRuntime
from apphub.core.utils import is_cmd_available
from apphub.plugins.base import PluginBase


class AptPlugin(PluginBase):
    # Simplified category mapping
    _SECTION_MAP: dict[str, AppCategory] = {
        # Desktop
        "gnome": AppCategory.DESKTOP,
        "kde": AppCategory.DESKTOP,
        "xfce": AppCategory.DESKTOP,
        "mate": AppCategory.DESKTOP,
        "x11": AppCategory.DESKTOP,
        "web": AppCategory.DESKTOP,
        "graphics": AppCategory.DESKTOP,
        "sound": AppCategory.DESKTOP,
        "video": AppCategory.DESKTOP,
        "editors": AppCategory.DESKTOP,
        "office": AppCategory.DESKTOP,
        "games": AppCategory.DESKTOP,
        # System
        "admin": AppCategory.SYSTEM,
        "base": AppCategory.SYSTEM,
        "kernel": AppCategory.SYSTEM,
        "libs": AppCategory.SYSTEM,
        "devel": AppCategory.SYSTEM,
        # CLI
        "utils": AppCategory.CLI,
        "shells": AppCategory.CLI,
        "net": AppCategory.CLI,
        "python": AppCategory.CLI,
    }

    @classmethod
    def _detect_category(cls, priority: str, section: str, name: str) -> AppCategory:
        if priority in ("required", "important", "essential"):
            return AppCategory.SYSTEM

        if name.startswith("lib") and not name.endswith("-bin"):
            return AppCategory.SYSTEM

        section_key = section.rsplit("/", 1)[-1] if "/" in section else section
        return cls._SECTION_MAP.get(section_key, AppCategory.CLI)

    def _get_package_metadata(
        self, name: str
    ) -> tuple[str | None, str | None, int | None, str | None]:
        try:
            result = subprocess.run(
                [
                    "dpkg-query",
                    "-W",
                    "-f=${Version}|${Maintainer}|${Installed-Size}|${binary:Summary}",
                    name,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return None, None, None, None

            parts = result.stdout.strip().split("|", maxsplit=3)

            version = parts[0] if len(parts) > 0 else None
            publisher = parts[1] if len(parts) > 1 else None
            size = (
                int(parts[2]) * 1024 if len(parts) > 2 and parts[2].isdigit() else None
            )
            description = parts[3] if len(parts) > 3 else None

            return version, publisher, size, description

        except Exception as e:
            self.logger.warning(f"Apt Failed to get package metadata: {e}")
            return None, None, None, None

    def inspect(self, path: Path) -> AppManifest:
        if not path.exists():
            raise FileNotFoundError(f".deb not found: {path}")

        MAX_LIST_SIZE = 100 * 1024 * 1024

        fields = [
            "Package",
            "Version",
            "Maintainer",
            "Depends",
            "Description",
            "Installed-Size",
        ]

        result = subprocess.run(
            ["dpkg-deb", "-f", str(path)] + fields,
            capture_output=True,
            text=True,
            check=True,
        )
        metadata = {}
        for line in result.stdout.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                metadata[k] = v

        installed_size = metadata.get("Installed-Size")
        if installed_size and installed_size.isdigit():
            size_bytes = int(installed_size) * 1024
        else:
            size_bytes = path.stat().st_size

        icon_path = None
        runtime = AppRuntime.NATIVE

        file_size = path.stat().st_size
        if file_size <= MAX_LIST_SIZE:
            best_icon = None
            best_icon_size = 0
            names = set()

            try:
                result = subprocess.run(
                    ["dpkg-deb", "-c", str(path)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) < 6:
                        continue
                    size = int(parts[2])
                    file_path = parts[-1]
                    name = Path(file_path).name
                    names.add(name)

                    if file_path.endswith((".png", ".svg")) and "icons" in file_path:
                        if size > best_icon_size:
                            best_icon = file_path
                            best_icon_size = size

            except Exception as e:
                self.logger.warning(f"APT inspect failed while extract .deb : {e}")
                pass

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
            elif "site-packages" in names or any(n.endswith(".py") for n in names):
                runtime = AppRuntime.PYTHON
            elif "package.json" in names or "node_modules" in names:
                runtime = AppRuntime.NODE
            elif "libcef.so" in names or "chrome" in names:
                runtime = AppRuntime.CHROMIUM

            if best_icon:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        tmp_path = Path(tmp)
                        subprocess.run(
                            ["dpkg-deb", "-x", str(path), tmp],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        icon_file = tmp_path / best_icon.lstrip("./")
                        if icon_file.exists():
                            cache = Path.home() / ".local/share/apphub/icons"
                            cache.mkdir(parents=True, exist_ok=True)
                            cached_icon = cache / f"deb_{path.stem}{icon_file.suffix}"
                            shutil.copy2(icon_file, cached_icon)
                            icon_path = str(cached_icon)
                except Exception as e:
                    self.logger.warning(f"APT inspect failed while extract .deb : {e}")
                    pass

        return AppManifest(
            id=f"apt:{metadata.get('Package')}",
            name=metadata.get("Package", "unknown"),
            version=metadata.get("Version", "unknown"),
            publisher=metadata.get("Maintainer"),
            description=metadata.get("Description"),
            format=AppFormat.DEBIAN,
            size_bytes=size_bytes,
            icon=icon_path,
            runtime=runtime,
        )

    def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)
        if path.exists():
            cmd = ["sudo", "apt", "install", str(path.resolve()), "-y"]
        else:
            cmd = []
            self.logger.error("APT install failed as search is not implemented")

        app_detail = self.inspect(path=path)
        try:
            subprocess.run(cmd, check=True)
            if launch:
                files = subprocess.run(
                    ["dpkg", "-L", app_detail.name],
                    capture_output=True,
                    text=True,
                )

                for line in files.stdout.splitlines():
                    if line.endswith(".desktop"):
                        desktop_id = Path(line).stem
                        subprocess.Popen(["gtk-launch", desktop_id])
                        break
        except subprocess.CalledProcessError as e:
            self.logger.error(f"APT install failed : {e}")
            return False
        return True

    def list_apps(self) -> list[AppManifest]:
        if not is_cmd_available("apt-mark"):
            raise PluginNotAvailableError("apt")

        apps = []
        try:
            result = subprocess.run(
                ["apt-mark", "showmanual"],
                capture_output=True,
                text=True,
            )

            for name in result.stdout.strip().split("\n"):
                if not name:
                    continue

                if (
                    name.startswith("lib") and not name.endswith("-bin")
                ) or name.endswith(("-dbgsym", "-dbg", "-dev", "-doc")):
                    continue

                version, publisher, size_bytes, description = (
                    self._get_package_metadata(name)
                )

                apps.append(
                    AppManifest(
                        name=name,
                        id=f"apt:{name}",
                        format=AppFormat.DEBIAN,
                        version=version,
                        installed=True,
                        publisher=publisher,
                        description=description,
                        category=AppCategory.CLI,
                        size_bytes=size_bytes,
                    )
                )

        except Exception as e:
            self.logger.warning(f"APT list_apps failed : {e}")

        return apps
