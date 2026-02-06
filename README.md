# Broomstick 🧹

A Mole-inspired cleanup tool for Python environments. Discover, analyze, and clean up Python installations, virtual environments, and packages across your system.

## Features

- **Discover All Python Interpreters**: Find Python installations from system, Homebrew, pyenv, asdf, conda, and more
- **Virtual Environment Detection**: Locate venvs from venv, virtualenv, poetry, pipenv, pipx, conda, hatch, pdm
- **Package Analysis**: Detect duplicate packages and version conflicts across environments
- **Interactive TUI**: Navigate with arrow keys, mark items for deletion, browse hierarchically
- **Safe Deletion**: Dry-run mode, confirmations, and system path protection
- **macOS Optimized**: Optional `mdfind` integration for blazing-fast scanning

## Quick Start

```bash
# Install (no dependencies required, stdlib only)
chmod +x broomstick.py

# Interactive mode (default)
./broomstick.py

# Or run specific commands
./broomstick.py interpreters    # List all Python interpreters
./broomstick.py venvs           # List all virtual environments
./broomstick.py packages        # Analyze package duplicates
./broomstick.py scan            # Full scan with JSON output
./broomstick.py clean --target /path/to/venv  # Delete a venv
```

## Usage

### Interactive Mode

```bash
./broomstick.py
# or
./broomstick.py interactive
```

Navigate with:
- `↑/↓` - Move cursor
- `Space` - Mark/unmark item for deletion
- `Enter` - Select menu item
- `d` - Delete marked items
- `ESC` - Go back
- `q` - Quit

### Command Line

**List Python Interpreters**
```bash
./broomstick.py interpreters
```

Sample output:
```
Found 8 Python interpreters:

Manager      Size       Version
--------------------------------------------------------------------------------
[pyenv]      2.3GB      3.11.5 (main, Aug 24 2023)
[conda]      1.8GB      3.10.4 (conda-forge)
[homebrew]   847.2MB    3.12.0 (main, Oct  2 2023)
[system]     156.3MB    3.9.6 (default, Sep 26 2022) (system)

Total size: 5.1GB
```

**List Virtual Environments**
```bash
./broomstick.py venvs
```

**Analyze Packages**
```bash
./broomstick.py packages
```

Shows:
- Total unique packages
- Packages duplicated across venvs
- Version conflicts
- Top duplicated packages

**Scan Everything**
```bash
./broomstick.py scan --json results.json
```

**Clean Up**
```bash
# Dry run (safe, shows what would be deleted)
./broomstick.py clean --target ~/.cache/pypoetry/virtualenvs/old-project --dry-run

# Actually delete
./broomstick.py clean --target ~/.cache/pypoetry/virtualenvs/old-project --yes
```

### macOS Fast Scanning

Use `--mdfind` to leverage Spotlight for much faster discovery:

```bash
./broomstick.py --mdfind venvs
```

## What Gets Detected

### Python Interpreters
- System Python (`/usr/bin/python*`)
- Homebrew (`/opt/homebrew`, `/usr/local/Cellar`)
- pyenv (`~/.pyenv/versions`)
- asdf (`~/.asdf/installs/python`)
- conda/miniconda/anaconda environments
- Custom PATH entries

### Virtual Environments
- `venv` / `virtualenv` (detects `pyvenv.cfg`)
- conda environments
- poetry (`~/.cache/pypoetry/virtualenvs`)
- pipenv (`~/.local/share/virtualenvs`)
- pipx (`~/.local/pipx/venvs`)
- hatch (`~/.local/share/hatch`)
- pdm (`~/.local/share/pdm/venvs`)
- Project-local `.venv`, `venv`, `env` directories

## Safety Features

- **Never deletes system paths** (`/usr/bin`, `/System`, etc.)
- **Dry-run by default** for `clean` command
- **Confirmation prompts** unless `--yes` is used
- **System interpreter warnings** in TUI (shown in red)
- **Size calculations** before deletion

## Requirements

- Python 3.8+
- macOS, Linux, or Windows
- No external dependencies (stdlib only)

## Examples

**Find all venvs older than 90 days and see their sizes:**
```bash
./broomstick.py venvs | sort -k4
```

**Export full scan for analysis:**
```bash
./broomstick.py scan --json python-audit.json
```

**Clean up old poetry venvs:**
```bash
# List them first
ls -lah ~/.cache/pypoetry/virtualenvs/

# Delete specific one
./broomstick.py clean --target ~/.cache/pypoetry/virtualenvs/old-project-py3.9
```

## Architecture

- **Scanner**: Efficiently discovers Python resources using manager-specific paths and markers
- **Analyzer**: Cross-references packages to find duplicates and conflicts
- **TUI**: Curses-based interactive interface for browsing and marking
- **CLI**: Simple subcommands for scripting and automation

## Comparison to Mole

| Feature | Mole | Broomstick |
|---------|------|-----------|
| Target | macOS system cleanup | Python environments |
| Language | Bash + Go | Python (stdlib only) |
| UI | Interactive TUI | Interactive TUI + CLI |
| Focus | Broad system optimization | Python-specific cleanup |
| Package analysis | N/A | Duplicate & conflict detection |

## Contributing

This is a focused tool for Python environment cleanup. Contributions welcome for:
- Additional package manager detection
- Windows compatibility improvements
- Performance optimizations
- Bug fixes

## License

MIT

## Credits

Inspired by [Mole](https://github.com/davesque/mole) - the excellent macOS cleanup tool.
