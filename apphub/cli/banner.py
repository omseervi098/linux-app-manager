from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

# Block-style wordmark — reads clearly at typical terminal widths.
_LOGO_LINES = [
    r" ██╗     ██╗███╗   ██╗███╗   ███╗ █████╗ ███╗   ██╗",
    r" ██║     ██║████╗  ██║████╗ ████║██╔══██╗████╗  ██║",
    r" ██║     ██║██╔██╗ ██║██╔████╔██║███████║██╔██╗ ██║",
    r" ██║     ██║██║╚██╗██║██║╚██╔╝██║██╔══██║██║╚██╗██║",
    r" ███████╗██║██║ ╚████║██║ ╚═╝ ██║██║  ██║██║ ╚████║",
    r" ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝",
]

# Gradient stops (top → bottom) — cyan → blue → magenta.
_GRADIENT = [
    "bright_cyan",
    "cyan",
    "deep_sky_blue1",
    "dodger_blue1",
    "medium_purple",
    "medium_orchid",
]

_TAGLINE = "Linux App Manager  ·  apt  ·  snap  ·  flatpak  ·  appimage"
_SUB = "one CLI  ·  every format  ·  zero friction"


def render_logo() -> Text:
    """Return a colorized LINMAN wordmark."""
    logo = Text()
    for i, line in enumerate(_LOGO_LINES):
        style = _GRADIENT[i % len(_GRADIENT)]
        logo.append(line + "\n", style=f"bold {style}")
    return logo


def print_banner(
    console: Console | None = None,
    *,
    version: str = "0.1.0",
    show_panel: bool = True,
) -> None:
    """Print the linman logo banner to the terminal."""
    console = console or Console()

    logo = render_logo()
    tagline = Text(_TAGLINE, style="bold white")
    sub = Text(_SUB, style="dim italic")
    ver = Text(f"v{version}", style="dim cyan")

    body = Group(
        Align.center(logo),
        Align.center(tagline),
        Align.center(sub),
        Align.center(ver),
    )

    if show_panel:
        console.print(
            Panel(
                body,
                border_style="bright_cyan",
                padding=(1, 2),
                title="[bold bright_magenta]◆[/] [bold white]linman[/]",
                title_align="left",
                subtitle="[dim]unified package hub[/]",
                subtitle_align="right",
            )
        )
    else:
        console.print(body)
        console.print()
