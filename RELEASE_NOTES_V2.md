# Broomstick 2.0 Release Notes

## 🎉 Major Release: Mole-Inspired Mode System

Broomstick 2.0 is a complete reimagining of the Python environment cleanup experience, inspired by the elegant Mole application for macOS. This release introduces a sophisticated mode-based interface, enhanced TUI capabilities, and comprehensive installation options.

## 🆕 What's New in 2.0

### Mode Selection System

The headline feature of 2.0 is the beautiful mode selection system:

- **List Mode** - Safe, read-only browsing and exploration
- **Delete Mode** - Powerful cleanup with safety confirmations
- **Analyze Mode** - Deep package analysis, duplicates, and conflicts
- **Package Manager** - Granular package-level management

### Enhanced TUI

- **Beautiful Startup Screen** - ASCII art mode selection with statistics
- **Smart Scrolling** - Automatic scroll management for lists of any size
- **Help Overlay** - Press 'h' or '?' for contextual help anywhere
- **Real-time Search** - Press '/' to filter items instantly
- **Progress Indicators** - Visual feedback during delete/uninstall operations
- **Breadcrumb Navigation** - Always know your location in the hierarchy

### Core Improvements

- **Package-Level Management** - Drill into venvs and uninstall specific packages
- **Recursive .venv Detection** - Finds project venvs deep in directory trees
- **Modern Tool Support** - Full support for uv, ruff, piptools, PDM, Hatch
- **Enhanced Path Display** - Project-relative paths and intelligent shortening
- **Better Performance** - Optimized scanning with parallel package probing

## 📦 Installation Options

### Homebrew (Recommended for macOS/Linux)
```bash
brew install https://raw.githubusercontent.com/haydenso/broomstick/main/broomstick.rb
```

### pip (All Platforms)
```bash
# From GitHub
pip install git+https://github.com/haydenso/broomstick.git

# In development mode
git clone https://github.com/haydenso/broomstick.git
cd broomstick
pip install -e .
```

### Direct Download
```bash
git clone https://github.com/haydenso/broomstick.git
cd broomstick
chmod +x broomstick
./broomstick
```

## 🎯 Key Features

### Discovery
- Python interpreters: system, Homebrew, pyenv, asdf, conda, uv
- Virtual environments: venv, virtualenv, poetry, pipenv, pipx, conda, hatch, pdm, uv
- Recursive project venv scanning (configurable depth)
- macOS mdfind/Spotlight integration for lightning-fast searches

### Management
- View all environments and packages in interactive hierarchy
- Delete entire venvs or drill down to remove specific packages
- Analyze duplicates and version conflicts across all environments
- Search and filter by name, size, age, or manager type

### Safety
- System path protection (never touches system Python)
- Dry-run mode for previewing operations
- Confirmation prompts before any deletion
- Real-time progress feedback

## 🚀 Quick Start

### Interactive Mode (Recommended)
```bash
broomstick
```

**Basic Workflow:**
1. Launch → See mode selection screen
2. Choose a mode → Select category (Interpreters/Venvs/Analysis)
3. Browse items → Mark with Space, delete with 'd', uninstall with 'u'
4. ESC to go back → 'q' to quit

### CLI Mode
```bash
# List all Python interpreters
broomstick interpreters

# List virtual environments
broomstick venvs

# View packages in a venv
broomstick packages --venv /path/to/.venv

# Uninstall a package
broomstick uninstall numpy --from /path/to/.venv

# Delete a venv
broomstick clean --target /path/to/.venv --dry-run
broomstick clean --target /path/to/.venv --yes

# Search for venvs
broomstick search myproject

# Fast scanning on macOS
broomstick --mdfind venvs
```

## 📊 Typical Use Cases

### 1. Clean Up Old Projects
Find and remove virtual environments for projects you no longer work on:
- Launch in Delete Mode
- Browse venvs sorted by age
- Mark old ones (1y+ ago)
- Delete to free gigabytes of space

### 2. Find Package Duplicates
Discover packages installed across multiple environments:
- Launch in Analyze Mode
- View duplicate packages
- See version conflicts
- Identify optimization opportunities

### 3. Manage Package Bloat
Remove unnecessary packages from specific venvs:
- Launch in Package Manager Mode
- Drill into a bloated venv
- Browse packages by size
- Uninstall unused dependencies

### 4. System Audit
Get a complete overview of your Python ecosystem:
- Launch in List Mode (safe, read-only)
- Browse interpreters and venvs
- Check sizes and ages
- Export data with JSON

## 🎨 UI/UX Highlights

### Mode Selection Screen
```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║                  🧹  BROOMSTICK  🧹                           ║
║                                                                ║
║           Python Environment & Package Cleaner                 ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝

Found: 3 Python interpreters (21.6GB)
Found: 21 virtual environments (7.5GB)

Select Mode:

  1. List Mode
     Browse and explore environments (read-only)

  2. Delete Mode
     Remove unwanted environments and packages

  3. Analyze Mode
     Deep analysis of packages and duplicates

  4. Package Manager
     Manage packages within environments

  5. Quit
     Exit Broomstick
```

### Navigation
- **Hierarchical browsing** with breadcrumbs showing your path
- **Color-coded items** (red for system paths, yellow for selections)
- **Real-time statistics** (marked items count, total size to delete)
- **Contextual help** in footer showing available actions

## 🔧 Technical Details

- **Zero Dependencies** - Pure Python stdlib (no external packages)
- **Python 3.8+** - Compatible with modern Python versions
- **Curses-Based TUI** - Works in any terminal with curses support
- **Cross-Platform** - macOS, Linux, Unix (Windows with caveats)
- **Lightweight** - Single 1900-line Python file
- **Fast** - Parallel package probing, smart path detection

## 📝 Documentation

- [README.md](README.md) - Full feature documentation
- [INSTALL.md](INSTALL.md) - Detailed installation guide
- [HOMEBREW.md](HOMEBREW.md) - Homebrew tap setup guide
- [EXAMPLES.md](EXAMPLES.md) - Usage examples and workflows
- [WHATS_NEW_V2.md](WHATS_NEW_V2.md) - Version 2 feature guide
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Technical overview

## 🙏 Credits

Inspired by [Mole](https://pilotmoon.com/mole/) - the beautiful macOS cleanup tool that sets the standard for intuitive system maintenance UIs.

## 📜 License

MIT License - See [LICENSE](LICENSE) file

## 🐛 Reporting Issues

Found a bug or have a feature request? Please open an issue on GitHub:
https://github.com/haydenso/broomstick/issues

## 🤝 Contributing

Contributions welcome! This is a single-file Python project with no dependencies, making it easy to hack on.

## ⚡ Next Steps

After installing:

1. Run `broomstick` to see the mode selection screen
2. Try List Mode first to explore safely
3. Use Delete Mode to clean up old venvs
4. Use Package Manager to trim package bloat
5. Use Analyze Mode to find duplicates

Happy cleaning! 🧹✨
