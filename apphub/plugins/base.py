from abc import ABC, abstractmethod
from logging import Logger
from pathlib import Path

from apphub.core.logger import get_logger
from apphub.core.models import AppManifest, DistroInfo, HistoryRecords, LifeCycleEvent
from apphub.core.utils import detect_distro_info


class PluginBase(ABC):
    """Base class for package-manager plugins"""

    def __init__(self) -> None:
        self.logger: Logger = get_logger(self.__class__.__name__)
        self.distro_info: DistroInfo = detect_distro_info()
        super().__init__()

    @abstractmethod
    async def list_apps(self) -> list[AppManifest]:
        """List installed applications for this format."""

    @abstractmethod
    async def inspect(self, path: Path) -> AppManifest:
        """Inspect a local package/file and return an AppManifest."""

    async def search(self, query: str) -> list[AppManifest]:
        """Search remote registries. Optional — not all formats support it."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support search()"
        )

    @abstractmethod
    async def install(self, query_or_path: str, launch: bool) -> bool:
        """Install an application from a registry name or local path."""

    @abstractmethod
    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        """Uninstall an application; optionally purge associated data."""

    async def history(
        self, action_categories: list[LifeCycleEvent] | None = None
    ) -> list[HistoryRecords]:
        """Return lifecycle history. Optional — not all formats support it."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support history()"
        )
