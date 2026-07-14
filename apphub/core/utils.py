import asyncio
import shutil
from functools import lru_cache
from pathlib import Path

from apphub.core.exceptions import AppHubError, PluginNotAvailableError
from apphub.core.models import AppFormat, DistroInfo


@lru_cache(maxsize=1)
def detect_distro_info() -> DistroInfo:
    try:
        with open("/etc/os-release") as f:
            name, name_id, version_id = None, None, None
            for line in f:
                if line.startswith("NAME"):
                    name = line.strip().split("=", 1)[1].strip('"')
                if line.startswith("ID="):
                    name_id = line.strip().split("=", 1)[1].strip('"').lower()
                if line.startswith("VERSION_ID="):
                    version_id = line.strip().split("=", 1)[1].strip('"').lower()
            return DistroInfo(name=name, id=name_id, version_id=version_id)
    except FileNotFoundError:
        raise AppHubError("Unable to locate /etc/os-release.") from None


def detect_format(path: str) -> AppFormat:
    if not Path(path).exists():
        raise AppHubError(f"Path Doesn't Exists : {path}.") from None
    suffix = Path(path).suffix[1:].lower()
    format_key = "apt" if suffix == "deb" else suffix
    try:
        return AppFormat(format_key)
    except ValueError:
        raise PluginNotAvailableError(format_key or "unknown") from None


def is_cmd_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


async def run_cmd(*cmd: str) -> tuple[int | None, str, str]:
    cmd_list = list(cmd)

    proc = await asyncio.create_subprocess_exec(
        *cmd_list,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    return (
        proc.returncode,
        stdout.decode(),
        stderr.decode(),
    )
