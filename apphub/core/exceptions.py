class AppHubError(Exception):
    """Base error for AppHub."""

    pass


class PluginError(AppHubError):
    """Raised when Plugin need to raise exception"""

    def __init__(self, plugin_name: str, msg: str):
        super().__init__(msg)
        self.plugin_name = plugin_name


class PluginNotAvailableError(PluginError):
    """Raised when a required backend (e.g. snap, flatpak) is not installed."""

    def __init__(self, plugin_name: str):
        super().__init__(
            plugin_name=plugin_name,
            msg=f"Plugin backend not available: '{plugin_name}'. Is it installed?",
        )


class AppNotFoundError(AppHubError):
    """Raised when a requested application cannot be found."""

    def __init__(self, app_name: str):
        super().__init__(f"Application not found: '{app_name}'")
        self.app_name = app_name


class InstallError(AppHubError):
    """Raised when an installation fails."""

    def __init__(self, app_name: str, reason: str = ""):
        msg = f"Failed to install '{app_name}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.app_name = app_name


class UninstallError(AppHubError):
    """Raised when an uninstallation fails."""

    def __init__(self, app_name: str, reason: str = ""):
        msg = f"Failed to uninstall '{app_name}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.app_name = app_name
