# Linux App Manager

`linman` is a terminal-based application management tool for Linux.
It provides a unified interface to interact with various package
managers and applications.

⚠️  **Work in Progress**  
This project is under development. Expect bugs, breaking changes, and incomplete features.

## Features

- **Multi-backend Support**: Manage applications from different sources. Currently it supports the following formats:
    - `apt` Debian Package Manager
    - `snap` Snap Package Manager
    - `flatpak` Flathub
    - `appimage` AppImage Format

- **System App Detection**: Automatically identify and categorize installed system utilities and libraries.
- **Application Manifests**: Standardized view of application metadata including versions, publishers, dependencies, and
  categories.
- **Categorization**: Intelligent grouping of software into categories like `system`, `cli`, and `desktop`.

## Project Structure

```
apphub/
├── main.py                   # Entry point — routes Typer CLI or TUI
├── core/
│   ├── hub.py                # AppHubCore — orchestrates plugins & filters
│   ├── models.py             # Pydantic models: AppManifest, AppFormat
│   ├── exceptions.py         # Standardized error types
│   ├── logger.py             # Logger configuration
│   └── utils.py              # Common utility functions
├── plugins/
│   ├── base.py               # PluginBase ABC
│   ├── apt.py                # APT plugin
│   ├── snap.py               # Snap plugin
│   ├── flatpak.py            # Flatpak plugin
│   └── appimage.py           # Scans ~/Applications for .AppImage files
└── cli/
    ├── commands.py           # Typer subcommands
    ├── formatters.py         # Rich tables, panels, progress bars
    └── serializers.py        # JSON serialization via Pydantic models
```

## Installation

- Install from source globally using pipx:

```bash
git clone https://github.com/omseervi098/linux-app-hub.git
cd linux-app-hub
pipx install -e .
```

After installation, the CLI tool is available via the command `linman`.

## Usage

### Common Options

These flags are shared across multiple subcommands:

| Flag       | Short | Description                                                     | Supported Commands                                        |
|------------|-------|-----------------------------------------------------------------|-----------------------------------------------------------|
| `--json`   |       | Output results in JSON format                                   | `list`, `search`, `inspect`, `info`, `storage`, `history` |
| `--format` | `-f`  | Filter by package format (`snap`, `apt`, `flatpak`, `appimage`) | `list`, `search`, `install`, `storage`, `history`         |
| `--sort`   | `-s`  | Sort results by field (e.g., name, version, format, timestamp)  | `list`, `history`                                         |
| `--count`  | `-n`  | Return only the number of matching items                        | `list`, `search`                                          |

---

### Commands

#### `linman list`

List all installed applications in a table view (name, format, version, publisher).

```bash
linman list                       # List all applications
linman list <query>               # Search installed apps by name
linman list -e                    # Exclude system/default packages
linman list -f snap               # Filter by format (can be specified multiple times)
linman list -s version            # Sort by field (name, version, format)
```

#### `linman search`

Search available applications across supported registries.

```bash
linman search <query>             # Search registry by name/description
linman search <query> -f flatpak  # Search within a specific format
linman search <query> -n          # Print only the number of matching apps
```

#### `linman inspect`

Inspect a local installable package file (e.g., `.AppImage`) and print its manifest details.

```bash
linman inspect <path_to_file>     # Print detailed metadata
linman inspect <path_to_file> --json # Print metadata as JSON
```

#### `linman install`

Install an application from a registry or a local file. The format is auto-detected for local files.

```bash
linman install <name_or_path>     # Install by name (interactive choice if multiple) or path
linman install <name_or_path> -y  # Auto-confirm installation
linman install <name_or_path> -l  # Launch the application immediately after installation
linman install <name> -f snap     # Restrict search registry to a specific format
```

#### `linman uninstall`

Remove an installed application.

```bash
linman uninstall <application_name>
linman uninstall <application_name> -y # Auto-confirm uninstallation
linman uninstall <application_name> -c # Clean uninstall (removes associated data)
```

#### `linman info`

Display detailed metadata for a specific application.

```bash
linman info <application_name>        # Show app details
linman info <application_name> --json # Show app details in JSON format
```

#### `linman storage`

Analyze disk space used by installed applications.

```bash
linman storage                    # Show storage for all apps
linman storage -f snap            # Filter by format
linman storage -t 10              # Show top N apps by size
linman storage --json             # Output storage analysis as JSON
```

#### `linman history`

View installation and uninstallation history.

```bash
linman history                    # Show full history
linman history -f flatpak         # Filter by format
linman history -a installed       # Filter by action category (installed|upgraded|uninstalled)
linman history -s timestamp -d    # Sort by field descending (name|version|timestamp)
linman history -t 10              # Show top N records
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to
discuss what you would like to change.

## License

This project is licensed under the MIT License.
