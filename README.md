# AppHub CLI

AppHub CLI is a terminal-based application management tool for Linux.
It provides a unified interface to interact with various package
managers and applications.


⚠️  **Work in Progress**  
This project is under development. Expect bugs, breaking changes, and incomplete features.

## Features

- **Multi-backend Support**: Manage applications from different sources. Currently it supports follwing formats.
    - `apt` Debian Package Manager
    - `snap` Snap Package Manager
    - `flatpak` Flathub 
    - `appimage` AppImage Format

- **System App Detection**: Automatically identify and categorize installed system utilities and libraries.
- **Application Manifests**: Standardized view of application metadata including versions, publishers, dependencies and categories.
- **Categorization**: Intelligent grouping of software into categories like `system`, `cli`, `dev`, and `other`.

## Project Structure

```
apphub/
├── main.py                   # Entry point — routes Typer CLI or TUI
├── core/
│   ├── hub.py                # AppHubCore — orchestrates plugins & filters
│   ├── models.py             # Pydantic models: AppManifest, AppFormat
│   └── exceptions.py         # Standardized error types
├── plugins/
│   ├── base.py               # PluginBase ABC
│   ├── apt.py                # APT plugin
│   ├── snap.py
│   ├── flatpak.py
│   └── appimage.py           # Scans ~/Applications for .AppImage files
└── cli/
    ├── commands.py           # Typer subcommands
    ├── formatters.py         # Rich tables, panels, progress bars
    └── serializers.py        # --json output via Pydantic model_dump()
```

## Installation

- Install from source:
```bash
git clone https://github.com/omseervi098/linux-app-hub.git
cd linux-app-hub
pip install -e .
```
## Usage

### Global Options

These flags can be used across multiple commands:

| Flag | Short | Description                                                                    | Supported Commands |
|------|-------|--------------------------------------------------------------------------------|--------------------|
| `--json` | | Output results in JSON format                                                  | `list`, `info`, `storage`, `history` |
| `--format` | `-f` | Filter by package format (`snap`, `apt`, `flatpak`, `appimage`)                | `list`, `storage`, `history` |
| `--sort` | `-s` | Sort results by field (name, size, version)                                    | `list`, `storage` |
| `--count` | `-n` | Return only the number of results                                              | `list`, `history` |

---

### Commands

#### `apphub list`

List all installed applications in a table view (name, format, version, publisher).

```bash
apphub list                       # List all applications
apphub list <query>               # Search by name
apphub list -e                    # Exclude system/default packages
apphub list -f snap               # Filter by format
apphub list -c dev                # Filter by category (system|cli|dev|other)
```

#### `apphub install`

Install an application from a local file. The format is auto-detected.

```bash
apphub install <path>             # Install an application
apphub install <path> -l          # Install and launch immediately
```

#### `apphub uninstall`

Remove an installed application.

```bash
apphub uninstall <application_name>
```

#### `apphub info`

Display detailed metadata for a specific application.

```bash
apphub info <application_name>    # Show app details
```

#### `apphub storage`

Analyze disk space used by installed applications.

```bash
apphub storage                    # Show storage for all apps
apphub storage -f snap            # Filter by format
apphub storage -t 10              # Show top N apps by size
```

#### `apphub history`

View installation and uninstallation history.

```bash
apphub history                    # Show full history
apphub history -f flatpak         # Filter by format
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

This project is licensed under the MIT License.
