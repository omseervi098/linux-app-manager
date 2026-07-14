# linman

`linman` is a terminal-based application manager for Linux. It provides a unified CLI to work with multiple package formats from one place.

## Features

- **Multi-backend support** — manage apps across:
  - `apt` (Debian packages)
  - `snap`
  - `flatpak` (Flathub)
  - `appimage`
- **System app detection** — identify and categorize system utilities and libraries
- **Application manifests** — consistent view of versions, publishers, sizes, and categories
- **Categorization** — group software into `system`, `cli`, and `desktop`

## Installation

Requires Python **3.11+**.

### pipx (recommended)

```bash
pipx install linman
```

### uv

```bash
uv tool install linman
```

After install, the CLI is available as:

```bash
linman --help
linman --version
```

### Upgrade

```bash
pipx upgrade linman
# or
uv tool upgrade linman
```

## Usage

### Common options

| Flag       | Short | Description                                                     | Commands                                                  |
|------------|-------|-----------------------------------------------------------------|-----------------------------------------------------------|
| `--json`   |       | Output results as JSON                                          | `list`, `search`, `inspect`, `info`, `storage`, `history` |
| `--format` | `-f`  | Filter by package format (`snap`, `apt`, `flatpak`, `appimage`) | `list`, `search`, `install`, `storage`, `history`         |
| `--sort`   | `-s`  | Sort by field (e.g. name, version, format, timestamp)           | `list`, `history`                                         |
| `--count`  | `-n`  | Print only the number of matching items                         | `list`, `search`                                          |

### Commands

#### `linman list`

List installed applications (name, format, version, publisher).

```bash
linman list                       # List all applications
linman list <query>               # Filter installed apps by name
linman list -e                    # Exclude system/default packages
linman list -f snap               # Filter by format (repeatable)
linman list -s version            # Sort by field (name, version, format)
```

#### `linman search`

Search available applications across supported registries.

```bash
linman search <query>
linman search <query> -f flatpak
linman search <query> -n
```

#### `linman inspect`

Inspect a local package file (e.g. `.AppImage`, `.deb`) and print its manifest.

```bash
linman inspect <path_to_file>
linman inspect <path_to_file> --json
```

#### `linman install`

Install from a registry name or a local file. Format is auto-detected for local files.

```bash
linman install <name_or_path>
linman install <name_or_path> -y   # Auto-confirm
linman install <name_or_path> -l   # Launch after install
linman install <name> -f snap      # Restrict search to a format
```

#### `linman uninstall`

Remove an installed application.

```bash
linman uninstall <application_name>
linman uninstall <application_name> -y   # Auto-confirm
linman uninstall <application_name> -c   # Clean uninstall (associated data)
```

#### `linman info`

Show detailed metadata for an application.

```bash
linman info <application_name>
linman info <application_name> --json
```

#### `linman storage`

Disk usage by installed applications.

```bash
linman storage
linman storage -f snap
linman storage -t 10
linman storage --json
```

#### `linman history`

Installation / upgrade / uninstall history.

```bash
linman history
linman history -f flatpak
linman history -a installed       # installed | upgraded | uninstalled
linman history -s timestamp -d
linman history -t 10
```

## Contributing

Contributions are welcome. Open an issue for larger changes, or submit a pull request.

## License

MIT
