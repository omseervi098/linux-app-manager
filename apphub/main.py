import typer

from apphub.cli.commands import cli_app
from apphub.core.logger import get_logger

logger = get_logger("root")
app = typer.Typer(
    no_args_is_help=True, help="Linux App Manager — manage Linux apps across all formats."
)

app.add_typer(cli_app, name="")  # mount subcommands at root level

if __name__ == "__main__":
    app()
