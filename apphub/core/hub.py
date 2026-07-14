import asyncio
from pathlib import Path
from typing import Any

from apphub.core.exceptions import AppNotFoundError, InstallError, UninstallError
from apphub.core.logger import get_logger
from apphub.core.models import (
    AppCategory,
    AppFormat,
    AppManifest,
    HistoryRecords,
    LifeCycleEvent,
)
from apphub.core.utils import detect_distro_info, detect_format, is_cmd_available
from apphub.plugins.appimage import AppImagePlugin
from apphub.plugins.apt import AptPlugin
from apphub.plugins.flatpak import FlatpakPlugin
from apphub.plugins.snap import SnapPlugin


def filter_manifests(
    apps: list[AppManifest],
    query: str | None = None,
    exclude_defaults: bool = False,
) -> list[AppManifest]:
    filtered: list[AppManifest] = []
    query_lower = query.lower() if query else None
    for app in apps:
        if exclude_defaults and app.category == AppCategory.SYSTEM:
            continue
        if query_lower and query_lower not in app.name.lower():
            continue
        filtered.append(app)
    return filtered


class AppHubCore:
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.distro_info = detect_distro_info()
        self.plugins: dict[AppFormat, Any] = {
            AppFormat.APPIMAGE: AppImagePlugin(),
        }
        self._register_platform_plugins()

    def _register_platform_plugins(self) -> None:
        if self.distro_info.id in (
            "ubuntu",
            "debian",
            "linuxmint",
            "pop",
            "elementary",
        ):
            self.plugins[AppFormat.DEBIAN] = AptPlugin()
        if is_cmd_available("flatpak"):
            self.plugins[AppFormat.FLATPAK] = FlatpakPlugin()
        if is_cmd_available("snap"):
            self.plugins[AppFormat.SNAP] = SnapPlugin()
        # TODO: Add Support for `dnf`

    def _plugins_for(
        self, formats: list[AppFormat] | None = None
    ) -> list[tuple[AppFormat, Any]]:
        return [
            (fmt, plugin)
            for fmt, plugin in self.plugins.items()
            if not formats or fmt in formats
        ]

    async def inspect(self, path: str) -> AppManifest:
        result = await self.plugins[detect_format(path=path)].inspect(Path(path))
        return result

    async def search(
        self, query: str, formats: list[AppFormat] | None = None
    ) -> list[AppManifest]:
        apps = []
        tasks = [plugin.search(query) for _, plugin in self._plugins_for(formats)]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Search Error: {str(result)}")
                continue
            apps.extend(result)
        return apps

    async def install(
        self, query_or_path: str, install_format: AppFormat, launch: bool = False
    ) -> bool:
        try:
            result = await self.plugins[install_format].install(query_or_path, launch)
        except NotImplementedError:
            raise
        except Exception as e:
            raise InstallError(f"Installation Error: {str(e)}") from None
        return result

    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        try:
            result = await self.plugins[app_info.format].uninstall(
                app_info, clean_uninstall
            )
        except NotImplementedError:
            raise
        except Exception as e:
            raise UninstallError(f"Uninstallation Error: {str(e)}") from None
        return result

    async def list_apps(
        self,
        query: str | None = None,
        formats: list[AppFormat] | None = None,
        exclude_defaults: bool = False,
    ) -> list[AppManifest]:
        tasks = [plugin.list_apps() for _, plugin in self._plugins_for(formats)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        apps: list[AppManifest] = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"List Error: {str(result)}")
                continue
            apps.extend(result)

        return filter_manifests(apps, query=query, exclude_defaults=exclude_defaults)

    async def info(self, query: str) -> AppManifest:
        matches = await self.list_apps(query=query)
        if not matches:
            raise AppNotFoundError(query)
        exact = [a for a in matches if a.name.lower() == query.lower()]
        return exact[0] if exact else matches[0]

    async def storage(
        self, formats: list[AppFormat] | None = None, top: int | None = None
    ) -> list[AppManifest]:
        apps = await self.list_apps(formats=formats)
        apps = sorted(apps, key=lambda a: a.size_bytes or 0, reverse=True)
        if top is not None:
            apps = apps[:top]
        return apps

    async def history(
        self,
        formats: list[AppFormat] | None = None,
        action_categories: list[LifeCycleEvent] | None = None,
    ) -> list[HistoryRecords]:
        history_records: list[HistoryRecords] = []
        tasks = [
            plugin.history(action_categories=action_categories)
            for _, plugin in self._plugins_for(formats)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"History Error: {str(result)}")
                continue
            if not result:
                continue
            history_records.extend(result)
        return history_records
