import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from apphub.core.models import (
    AppCategory,
    AppFormat,
    AppManifest,
    AppRuntime,
    HistoryRecords,
    LifeCycleEvent,
)
from apphub.core.utils import run_cmd
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
    INSTALL_OR_REMOVE_RE = re.compile(
        r"(?P<name>[^:,]+):[^\s]+\s+\((?P<version>[^)]+)\)"
    )

    UPGRADE_RE = re.compile(
        r"(?P<name>[^:,]+):[^\s]+\s+\((?P<old_version>[^,]+),\s*(?P<new_version>[^)]+)\)"
    )

    LOG_FILE_PATH = "/var/log/apt/history.log"
    APT_LOG_KEYS = {
        "start-date",
        "end-date",
        "commandline",
        "requested-by",
        "install",
        "upgrade",
        "remove",
        "purge",
    }

    @classmethod
    def _detect_category(cls, priority: str, section: str, name: str) -> AppCategory:
        if priority in ("required", "important", "essential"):
            return AppCategory.SYSTEM

        if name.startswith("lib") and not name.endswith("-bin"):
            return AppCategory.SYSTEM

        section_key = section.rsplit("/", 1)[-1] if "/" in section else section
        return cls._SECTION_MAP.get(section_key, AppCategory.CLI)

    async def _get_app_manifest_in_bulk(
        self, app_names: list[str]
    ) -> list[AppManifest]:
        try:
            cmd = [
                "dpkg-query",
                "-W",
                "-f=${Package}|${Version}|${Maintainer}|${Installed-Size}|${binary:Summary}\n",
            ] + app_names
            code, stdout, _ = await run_cmd(*cmd)

            if code != 0:
                return [
                    AppManifest(
                        name=name,
                        id=f"apt:{name}",
                        format=AppFormat.DEBIAN,
                        installed=True,
                        category=AppCategory.CLI,
                        version="-",
                    )
                    for name in app_names
                ]

            apps = []
            for line in stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|", maxsplit=4)
                name = parts[0]
                version = parts[1] if len(parts) > 1 else "-"
                publisher = parts[2] if len(parts) > 2 else None
                size = (
                    int(parts[3]) * 1024
                    if len(parts) > 3 and parts[3].isdigit()
                    else None
                )
                description = parts[4] if len(parts) > 4 else None
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
                        size_bytes=size,
                    )
                )

            return apps

        except Exception as e:
            self.logger.warning(f"Apt Failed to get package metadata: {e}")
            return []

    async def inspect(self, path: Path) -> AppManifest:
        if not path.exists():
            raise FileNotFoundError(f".deb not found: {path}")

        max_list_size = 100 * 1024 * 1024

        fields = [
            "Package",
            "Version",
            "Maintainer",
            "Depends",
            "Description",
            "Installed-Size",
        ]

        _, stdout, _ = await run_cmd(*(["dpkg-deb", "-f", str(path)] + fields))
        metadata = {}
        for line in stdout.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                metadata[k] = v

        installed_size = metadata.get("Installed-Size")
        if installed_size and isinstance(installed_size, str):
            size_bytes = int(installed_size) * 1024
        else:
            size_bytes = path.stat().st_size

        icon_path = None
        runtime = AppRuntime.NATIVE

        file_size = path.stat().st_size
        if file_size <= max_list_size:
            best_icon = None
            best_icon_size = 0
            names = set()

            try:
                _, stdout, _ = await run_cmd("dpkg-deb", "-c", str(path))
                for line in stdout.splitlines():
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
                        await run_cmd("dpkg-deb", "-x", str(path), tmp)
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

    async def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)
        if path.exists():
            cmd = ["sudo", "apt", "install", str(path.resolve()), "-y"]
        else:
            cmd = []
            self.logger.error("APT install failed as search is not implemented")

        app_detail = await self.inspect(path=path)
        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"APT install failed: {stderr}")
            return False
        if launch:
            code_launch, stdout, stderr_launch = await run_cmd(
                "dpkg", "-L", app_detail.name
            )
            if code_launch != 0:
                self.logger.error(f"Launch failed: {stderr}")
                return False

            for line in stdout.splitlines():
                if line.endswith(".desktop"):
                    desktop_id = Path(line).stem
                    await run_cmd("gtk-launch", desktop_id)
                    break
        return True

    async def list_apps(self) -> list[AppManifest]:
        apps = []
        try:
            _, stdout, _ = await run_cmd("apt-mark", "showmanual")

            potential_apps = []
            for name in stdout.strip().split("\n"):
                if not name:
                    continue

                if (
                    name.startswith("lib") and not name.endswith("-bin")
                ) or name.endswith(("-dbgsym", "-dbg", "-dev", "-doc")):
                    continue

                potential_apps.append(name)
            if not potential_apps:
                return apps

            response = await self._get_app_manifest_in_bulk(app_names=potential_apps)
            apps.extend(response)

        except Exception as e:
            self.logger.warning(f"APT list_apps failed : {e}")

        return apps

    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        if clean_uninstall:
            cmd = [
                "sudo",
                "apt",
                "purge",
                app_info.name,
                "-y",
                "&&",
                "sudo",
                "apt",
                "autoremove",
                "-y",
            ]
        else:
            cmd = ["sudo", "apt", "purge", app_info.name, "-y"]

        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"APT uninstall failed : {stderr}")
            return False

        return True

    @staticmethod
    def __get_lifecycle_event(data: dict) -> LifeCycleEvent:
        if "install" in data:
            return LifeCycleEvent.INSTALLED
        elif "remove" in data:
            return LifeCycleEvent.UNINSTALLED
        else:
            return LifeCycleEvent.UPGRADED

    def __parse_installed_or_uninstalled(self, entry: str):
        results = []
        for m in self.INSTALL_OR_REMOVE_RE.finditer(entry):
            name = m.group("name").strip()
            version = m.group("version").split(",")[0].strip()
            results.append(
                {
                    "app_name": name,
                    "app_id": name,
                    "version_id": version,
                }
            )
        return results

    def __parse_upgraded(self, entry: str):
        results = []
        for m in self.UPGRADE_RE.finditer(entry):
            name = m.group("name").strip()
            old_version = m.group("old_version").split(",")[0].strip()
            new_version = m.group("new_version").split(",")[0].strip()
            results.append(
                {
                    "app_name": name,
                    "app_id": name,
                    "version_id": new_version,
                    "old_version_id": old_version,
                }
            )
        return results

    @staticmethod
    def __parse_timestamp(start_date: str) -> datetime:
        normalized = " ".join(start_date.split())
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )

    async def history(
        self, action_categories: list[LifeCycleEvent] | None = None
    ) -> list[HistoryRecords]:
        path = Path(self.LOG_FILE_PATH)
        history_records = []
        if path.exists():
            try:
                entries = path.read_text(encoding="utf-8").split("\n\n")
                for entry in entries:
                    if not entry.strip():
                        continue
                    data = {}
                    current_key = None
                    for line in entry.splitlines():
                        if not line:
                            continue
                        if not line[0].isspace() and ": " in line:
                            key, value = line.split(": ", 1)
                            key = key.strip().lower()
                            data[key] = value.strip()
                            current_key = key
                        elif current_key and line.strip():
                            data[current_key] += " " + line.strip()

                    if "start-date" not in data:
                        continue

                    try:
                        timestamp = self.__parse_timestamp(data["start-date"])
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to parse timestamp {data.get('start-date')}: {e}"
                        )
                        continue

                    if (
                        action_categories is None
                        or LifeCycleEvent.INSTALLED in action_categories
                    ):
                        for package in self.__parse_installed_or_uninstalled(
                            data.get("install", "")
                        ):
                            history_records.append(
                                HistoryRecords(
                                    timestamp=timestamp,
                                    format=AppFormat.DEBIAN,
                                    lifecycle_event=LifeCycleEvent.INSTALLED,
                                    app_name=package["app_name"],
                                    app_id=f"apt:{package['app_name']}",
                                    version_id=package["version_id"],
                                )
                            )
                    if (
                        action_categories is None
                        or LifeCycleEvent.UNINSTALLED in action_categories
                    ):
                        for package in self.__parse_installed_or_uninstalled(
                            data.get("remove", "")
                        ):
                            history_records.append(
                                HistoryRecords(
                                    timestamp=timestamp,
                                    format=AppFormat.DEBIAN,
                                    lifecycle_event=LifeCycleEvent.UNINSTALLED,
                                    app_name=package["app_name"],
                                    app_id=f"apt:{package['app_name']}",
                                    version_id=package["version_id"],
                                )
                            )
                        for package in self.__parse_installed_or_uninstalled(
                            data.get("purge", "")
                        ):
                            history_records.append(
                                HistoryRecords(
                                    timestamp=timestamp,
                                    format=AppFormat.DEBIAN,
                                    lifecycle_event=LifeCycleEvent.UNINSTALLED,
                                    app_name=package["app_name"],
                                    app_id=f"apt:{package['app_name']}",
                                    version_id=package["version_id"],
                                )
                            )
                    if (
                        action_categories is None
                        or LifeCycleEvent.UPGRADED in action_categories
                    ):
                        for package in self.__parse_upgraded(data.get("upgrade", "")):
                            history_records.append(
                                HistoryRecords(
                                    timestamp=timestamp,
                                    format=AppFormat.DEBIAN,
                                    lifecycle_event=LifeCycleEvent.UPGRADED,
                                    app_name=package["app_name"],
                                    app_id=f"apt:{package['app_name']}",
                                    version_id=package["version_id"],
                                    old_version_id=package["old_version_id"],
                                )
                            )
            except Exception as e:
                self.logger.error(f"Failed to read or parse APT history log: {e}")
        return history_records
