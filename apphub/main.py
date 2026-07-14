import typer
from rich.console import Console

from apphub.cli.banner import print_banner
from apphub.cli.commands import cli_app
from apphub.core.logger import get_logger

logger = get_logger("root")
console = Console()

__version__ = "0.1.0"

app = typer.Typer(
    name="linman",
    no_args_is_help=False,
    add_completion=True,
    rich_markup_mode="rich",
    help="[bold cyan]linman[/] — manage Linux apps across apt, snap, flatpak & AppImage.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        print_banner(console, version=__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show logo + version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Linux App Manager — unified CLI for every package format."""
    if ctx.invoked_subcommand is None:
        print_banner(console, version=__version__)
        console.print()
        console.print(ctx.get_help())
        raise typer.Exit()


# Mount subcommands at root: `linman list`, `linman search`, ...
app.add_typer(cli_app, name="")

if __name__ == "__main__":
    app()
