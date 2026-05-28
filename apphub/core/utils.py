from functools import lru_cache
from pathlib import Path
import shutil
import asyncio

from apphub.core.exceptions import AppHubError, PluginNotAvailableError
from apphub.core.models import DistroInfo, AppFormat


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
    try:
        return AppFormat("apt" if suffix == "deb" else suffix)
    except ValueError:
        raise PluginNotAvailableError(
            f"Plugin Not Available for this format : {suffix}"
        ) from None


def is_cmd_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


async def run_cmd(*cmd: str) -> tuple[int|None, str, str]:
    cmd_list = list(cmd)
    if cmd_list and cmd_list[0] == "sudo" and "-n" not in cmd_list:
        cmd_list.insert(1, "-n")

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