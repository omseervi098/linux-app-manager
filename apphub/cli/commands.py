import typer
import asyncio
from pathlib import Path
from rich.console import Console

from apphub.cli.formatters import (
    format_app_panel,
    format_app_table,
    format_storage_table,
)
from apphub.cli.serializers import to_json, to_json_single
from apphub.core.hub import AppHubCore
from apphub.core.models import AppFormat

cli_app = typer.Typer(no_args_is_help=True)
hub = AppHubCore()
console = Console()


@cli_app.command(name="list")
def list_apps(
    query: str | None = typer.Argument(None, help="Filter applications by name"),
    formats: list[AppFormat] | None = typer.Option(
        None, "--format", "-f", help="Filter by format"
    ),
    exclude_defaults: bool = typer.Option(
        False, "--exclude-defaults", "-e", help="Exclude system/default packages"
    ),
    sort_by: str | None = typer.Option(
        None, "--sort", "-s", help="Sort by field: name, version, format"
    ),
    count: bool = typer.Option(
        False, "--count", "-n", help="Print only the number of matching apps"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List installed applications across all package managers."""
    apps = asyncio.run(hub.list_apps(query=query, formats=formats, exclude_defaults=exclude_defaults))

    if sort_by:
        apps = sorted(apps, key=lambda a: getattr(a, sort_by, "") or "")

    if count:
        console.print(f"[bold cyan]{len(apps)}[/bold cyan] application(s) found.")
        return

    if output_json:
        console.print(to_json(apps))
        return

    console.print(format_app_table(apps, title=f"Applications ({len(apps)})"))


@cli_app.command(name="search")
def search(
    query: str = typer.Argument(..., help="Search applications by name or description"),
    formats: list[AppFormat] | None = typer.Option(
        None, "--format", "-f", help="Filter by format"
    ),
    count: bool = typer.Option(
        False, "--count", "-n", help="Print only the number of matching apps"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search available applications across supported registries."""
    apps = asyncio.run(hub.search(query=query, formats=formats))

    if count:
        console.print(f"[bold cyan]{len(apps)}[/bold cyan] application(s) found.")
        return

    if output_json:
        console.print(to_json(apps))
        return

    console.print(format_app_table(apps, title=f"Search Results ({len(apps)})"))


@cli_app.command(name="inspect")
def inspect(
    file_path: str = typer.Argument(
        ..., help="Path to the application file or Application Name to be searched"
    ),
    output_json: bool = typer.Option(False, "--json ", help="Output as JSON"),
):
    """Inspect Local Installable File."""

    if not Path(file_path).exists():
        console.print(f"[red] No Application Found: '{file_path}'.[/red]")

    app_info = asyncio.run(hub.inspect(path=file_path))

    if output_json:
        console.print(to_json_single(app_info))
    else:
        console.print(format_app_panel(app_info))


@cli_app.command(name="install")
def install(
    path_or_name: str = typer.Argument(
        ..., help="Path to the application file or Application Name"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto confirm installation"),
    launch: bool = typer.Option(
        False, "--launch", "-l", help="Launch after installation"
    ),
    formats: list[AppFormat] | None = typer.Option(
        None, "--format", "-f", help="Optional format lookup for application"
    ),
):
    """Install an application (from registery or from file)."""

    if Path(path_or_name).exists():
        app_info = asyncio.run(hub.inspect(path=path_or_name))
        console.print(format_app_panel(app_info))
        install_target = path_or_name
        install_format = app_info.format
    else:
        results = asyncio.run(hub.search(query=path_or_name, formats=formats))
        if not results:
            console.print(f"[red]No application found matching '{path_or_name}'.[/red]")
            raise typer.Exit(1)

        if len(results) == 1:
            app_info = results[0]
            console.print(f"Found this on {app_info.format.value}")
            console.print(format_app_panel(app_info))
            install_target = app_info.name
            install_format = app_info.format
        else:
            console.print(f"Found multiple applications matching '{path_or_name}':")
            for idx, app in enumerate(results, start=1):
                desc = app.description or "No description"
                console.print(f"[{idx}] {app.name} ({app.format.value}) - {desc}")

            choice: int = typer.prompt(
                "Select an application to install (number)", type=int
            )
            if choice < 1 or choice > len(results):
                console.print("[red]Invalid selection.[/red]")
                raise typer.Exit(1)

            app_info = results[choice - 1]
            console.print(format_app_panel(app_info))
            install_target = app_info.name
            install_format = app_info.format

    if not yes:
        confirm = typer.confirm("Install this application?")
        if not confirm:
            print("Installation cancelled.")
            raise typer.Exit()

    result = asyncio.run(hub.install(
        query_or_path=install_target, install_format=install_format, launch=launch
    ))

    if result:
        console.print("[green]Installation successful[/green]")


@cli_app.command(name="uninstall")
def uninstall(
    name: str = typer.Argument(..., help="Name of the application to uninstall"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto confirm installation"),
    clean_uninstall: bool = typer.Option(
        False,
        "--clean",
        "-c",
        help="Clean Uninstall, remove data associated with application",
    ),
):
    """Uninstall an installed application."""
    results = asyncio.run(hub.list_apps(query=name))
    if not results:
        console.print(f"[red]No application found matching '{name}'.[/red]")
        raise typer.Exit(1)
    if len(results) == 1:
        console.print(f"[bold yellow]Uninstalling {name}...[/bold yellow]")
        app_info = results[0]
        console.print(format_app_panel(app_info))
    else:
        console.print(
            f"[yellow]Found multiple applications matching '{name}':[/yellow]"
        )
        for idx, app in enumerate(results, start=1):
            desc = app.description or "No description"
            console.print(
                f"[cyan][{idx}] | {app.name} ({app.format.value}) | {desc}[/cyan]"
            )

        choice: int = typer.prompt(
            "Select an application to uninstall (number)", type=int
        )
        if choice < 1 or choice > len(results):
            console.print("[red]Invalid selection.[/red]")
            raise typer.Exit(1)

        app_info = results[choice - 1]
        console.print(format_app_panel(app_info))

    if not yes:
        confirm = typer.confirm("Uninstall this application?")
        if not confirm:
            print("Uninstallation cancelled.")
            raise typer.Exit()

    success = asyncio.run(hub.uninstall(app_info, clean_uninstall))
    if success:
        console.print(f"[green]Successfully uninstalled {name}.[/green]")
    else:
        console.print(
            f"[red]Failed to uninstall {name} or application not found.[/red]"
        )


@cli_app.command(name="info")
def info(
    name: str = typer.Argument(..., help="Name of the application"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show detailed information about an application."""
    app_info = asyncio.run(hub.info(query=name))

    if app_info is None:
        console.print(f"[red]No application found matching '{name}'.[/red]")
        raise typer.Exit(1)

    if output_json:
        console.print(to_json_single(app_info))
    else:
        console.print(format_app_panel(app_info))


@cli_app.command(name="storage")
def storage(
    formats: list[AppFormat] | None = typer.Option(
        None, "--format", "-f", help="Filter by format"
    ),
    top: int | None = typer.Option(None, "--top", "-t", help="Show top N apps by size"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show disk usage by installed applications."""
    apps = asyncio.run(hub.storage(formats=formats, top=top))

    if output_json:
        console.print(to_json(apps))
        return

    console.print(format_storage_table(apps, top=None))  # already sliced


@cli_app.command(name="history")
def history(
    formats: list[AppFormat] | None = typer.Option(
        None, "--format", "-f", help="Filter by format"
    ),
    count: bool = typer.Option(False, "--count", "-n", help="Print only the count"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show installation/uninstallation history."""
    console.print(
        "[yellow]history[/yellow] is not yet implemented. Requires a local history database."
    )
