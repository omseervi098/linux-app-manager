from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from apphub.core.models import AppManifest, AppRuntime, HistoryRecords, LifeCycleEvent

console = Console()


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def format_app_table(apps: list[AppManifest], title: str = "Applications") -> Table:
    """Styled Rich table for a list of AppManifest objects."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        highlight=True,
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Name", style="bold white", min_width=20)
    table.add_column("Format", style="yellow", justify="center")
    table.add_column("Version", style="magenta")
    table.add_column("Publisher", style="green")
    table.add_column("Category", style="dim cyan")

    for app in apps:
        table.add_row(
            app.name,
            app.format.value,
            app.version,
            app.publisher or "—",
            app.category or "—",
        )
    return table


def format_app_panel(app: AppManifest) -> Panel:
    """Rich Panel for `apphub info <name>`."""
    lines = [
        f"[bold]Name[/bold]:        {app.name}",
        f"[bold]ID[/bold]:          {app.id}",
        f"[bold]Format[/bold]:      {app.format.value}",
        f"[bold]Version[/bold]:     {app.version}",
        f"[bold]Publisher[/bold]:   {app.publisher or '—'}",
        f"[bold]Category[/bold]:    {app.category or '—'}",
        f"[bold]Installed[/bold]:   {'✓' if app.installed else '✗'}",
        f"[bold]Size[/bold]:        {_format_size(app.size_bytes)}",
    ]
    if app.description:
        lines.append(f"\n[bold]Description[/bold]:\n  {app.description}")

    if app.icon:
        lines.append(f"\n[bold]Icon[/bold]: {app.icon}")

    if app.runtime != AppRuntime.NATIVE.value:
        lines.append(f"\n[bold]Runtime[/bold]: {app.runtime.value}")

    return Panel(
        "\n".join(lines),
        title=f"[bold cyan]{app.name}[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


def format_storage_table(apps: list[AppManifest], top: int | None = None) -> Table:
    """Storage breakdown table, sorted by size descending."""
    sized = sorted(
        [a for a in apps if a.size_bytes is not None],
        key=lambda a: a.size_bytes or 0,
        reverse=True,
    )
    unsized = [a for a in apps if a.size_bytes is None]
    ordered = sized + unsized

    if top is not None:
        ordered = ordered[:top]

    table = Table(
        title="Storage Usage",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("Name", style="bold white", min_width=20)
    table.add_column("Format", style="yellow", justify="center")
    table.add_column("Size", style="magenta", justify="right")

    for app in ordered:
        table.add_row(app.name, app.format.value, _format_size(app.size_bytes))

    return table


def format_history_table(
    history_records: list[HistoryRecords], title: str = "HistoryRecords"
) -> Table:
    """Styled Rich table for a list of HistoryRecords objects."""

    table = Table(
        title=title,
        box=box.ROUNDED,
        highlight=True,
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("Name", style="bold white", min_width=20)
    table.add_column("Format", style="yellow", justify="center")
    table.add_column("Timestamp", style="magenta")
    table.add_column("LifeCycle Event", style="red")
    table.add_column("Version", style="green")

    for record in history_records:
        table.add_row(
            record.app_name,
            record.format.value,
            record.timestamp.strftime("%B %d, %Y, %I:%M %p"),
            record.lifecycle_event,
            f"{record.old_version_id} -> {record.version_id}"
            if record.lifecycle_event == LifeCycleEvent.UPGRADED
            else record.version_id,
        )
    return table
