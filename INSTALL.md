# Installation Guide

## Quick Install (Recommended)

### Option 1: Homebrew (macOS/Linux - Easiest)
```bash
# Add the tap
brew tap haydenso/broomstick

# Install broomstick
brew install broomstick

# Run from anywhere
broomstick
```

Or install directly from the formula:
```bash
brew install https://raw.githubusercontent.com/haydenso/broomstick/main/broomstick.rb
```

### Option 2: Install from PyPI (when published)
```bash
pip install broomstick
broomstick
```

### Option 3: Install with pip from GitHub
```bash
pip install git+https://github.com/haydenso/broomstick.git
broomstick
```

### Option 4: Direct Download
```bash
# Clone the repository
git clone https://github.com/haydenso/broomstick.git
cd broomstick

# Make executable and run
chmod +x broomstick
./broomstick
```

### Option 5: Install with pip (editable development mode)
```bash
git clone https://github.com/haydenso/broomstick.git
cd broomstick
pip install -e .

# Now you can run from anywhere
broomstick
```

## System Requirements

- Python 3.8 or higher
- macOS, Linux, or Windows
- No external dependencies required (uses Python stdlib only)

## Optional: Add to PATH

### For bash/zsh (macOS/Linux):
```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$PATH:/path/to/broomstick"

# Or create a symlink
sudo ln -s /path/to/broomstick/broomstick /usr/local/bin/broomstick
```

### For Fish:
```fish
# Add to ~/.config/fish/config.fish
set -gx PATH $PATH /path/to/broomstick
```

## Verification

After installation, verify it works:

```bash
broomstick --help
broomstick interpreters
broomstick venvs
```

## Uninstall

### If installed with Homebrew:
```bash
brew uninstall broomstick
```

### If installed with pip:
```bash
pip uninstall broomstick
```

### If using direct download:
```bash
# Just remove the directory
rm -rf /path/to/broomstick
```

## Troubleshooting

### Permission Denied
```bash
chmod +x broomstick.py
# or
chmod +x broomstick
```

### Python Not Found
Make sure Python 3.8+ is installed:
```bash
python3 --version
```

### Interactive Mode Issues
If the TUI doesn't work properly, your terminal may not support curses. Try the CLI commands instead:
```bash
broomstick interpreters
broomstick venvs
broomstick packages
```

## Development Setup

```bash
git clone https://github.com/haydenso/broomstick.git
cd broomstick

# Install in editable mode
pip install -e .

# Run tests (when available)
python -m pytest tests/

# Run the tool
python broomstick.py
```

## macOS Optimization

For faster scanning on macOS, install with Spotlight support:

```bash
# First run will build Spotlight index
broomstick --mdfind scan

# Future runs will be much faster
broomstick --mdfind venvs
```

## Next Steps

After installation:

1. Run `broomstick interpreters` to see all Python installations
2. Run `broomstick venvs` to see all virtual environments
3. Try interactive mode with just `broomstick`
4. Analyze packages with `broomstick packages`
5. Clean up with `broomstick clean --target /path/to/old-venv --dry-run`

Enjoy cleaning! 🧹
