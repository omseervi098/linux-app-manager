import asyncio
from typing import Any, Dict
from pathlib import Path

from apphub.core.exceptions import InstallError, UninstallError
from apphub.core.models import AppFormat, AppManifest
from apphub.core.utils import detect_distro_info, detect_format, is_cmd_available
from apphub.core.logger import get_logger

from apphub.plugins.appimage import AppImagePlugin
from apphub.plugins.apt import AptPlugin
from apphub.plugins.flatpak import FlatpakPlugin
from apphub.plugins.snap import SnapPlugin


class AppHubCore:
    plugins: Dict[AppFormat, Any] = {
        AppFormat.DEBIAN: AptPlugin(),
        AppFormat.APPIMAGE: AppImagePlugin(),
    }

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

        self.distro_info = detect_distro_info()
        self._add_format()

    def _add_format(self):
        if is_cmd_available("flatpak"):
            self.plugins[AppFormat.FLATPAK] = FlatpakPlugin()
        if is_cmd_available("snap"):
            self.plugins[AppFormat.SNAP] = SnapPlugin()
        if self.distro_info.id in (
            "ubuntu",
            "debian",
            "linuxmint",
            "pop",
            "elementary",
        ):
            self.plugins[AppFormat.DEBIAN] = AptPlugin()
        # TODO: Add Support for `dnf`

    async def inspect(self, path: str) -> AppManifest:
        result = await self.plugins[detect_format(path=path)].inspect(Path(path))
        return result

    async def search(
        self, query: str, formats: list[AppFormat] | None = None
    ) -> list[AppManifest]:
        apps = []
        tasks = []
        for plugin_format, plugin in self.plugins.items():
            if formats and plugin_format not in formats:
                continue
            tasks.append(plugin.search(query))

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
            result = await self.plugins[app_info.format].uninstall(app_info, clean_uninstall)
        except NotImplementedError:
            raise
        except Exception as e:
            raise UninstallError(f"Installation Error: {str(e)}") from None
        return result

    async def list_apps(
        self,
        query: str | None = None,
        formats: list[AppFormat] | None = None,
        exclude_defaults: bool = False,
    ) -> list[AppManifest]:
        apps = []
        tasks = []

        for plugin_format, plugin in self.plugins.items():
            if formats and plugin_format not in formats:
                continue
            tasks.append(plugin.list_apps())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"List Error: {str(result)}")
                continue

            for app in result:
                if exclude_defaults and app.category == "system":
                    continue
                if query and query.lower() not in app.name.lower():
                    continue
                apps.append(app)
        return apps

    async def info(self, query: str) -> AppManifest | None:
        matches = await self.list_apps(query=query)
        exact = [a for a in matches if a.name.lower() == query.lower()]
        return exact[0] if exact else (matches[0] if matches else None)

    async def storage(
        self, formats: list[AppFormat] | None = None, top: int | None = None
    ) -> list[AppManifest]:
        apps = await self.list_apps(formats=formats)
        apps = sorted(apps, key=lambda a: a.size_bytes or 0, reverse=True)
        if top is not None:
            apps = apps[:top]
        return apps
