# Broomstick Usage Examples

This guide walks through common scenarios for using Broomstick to clean up your Python environments.

## Scenario 1: First Time Audit

You want to see what Python stuff is taking up space on your system.

```bash
# Step 1: See all Python interpreters
./broomstick interpreters

# Output:
# Found 8 Python interpreters:
# 
# Manager      Size       Version
# --------------------------------------------------------------------------------
# [pyenv]      2.3GB      3.11.5 (main, Aug 24 2023)
# [conda]      1.8GB      3.10.4 (conda-forge)
# [homebrew]   847.2MB    3.12.0 (main, Oct  2 2023)
# [system]     156.3MB    3.9.6 (default, Sep 26 2022) (system)
#
# Total size: 5.1GB

# Step 2: See all virtual environments
./broomstick venvs

# Output:
# Found 23 virtual environments:
# 
# Manager      Size       Name                           Modified
# --------------------------------------------------------------------------------
# [conda]      1.8GB      data-science                   2023-12-15 14:23
# [poetry]     456.2MB    my-web-app-py3.11-...         2024-01-08 10:15
# [venv]       234.5MB    old-project                    2022-03-12 09:30
# ...
#
# Total size: 8.3GB

# Step 3: Get the big picture
./broomstick scan --json audit-2024.json

# This saves everything to JSON for later review
```

## Scenario 2: Finding Duplicate Packages

You suspect you have the same packages installed across multiple venvs.

```bash
# Run package analysis
./broomstick packages

# Output:
# ========================================================================
# Package Analysis
# ========================================================================
#
# Total unique packages: 847
# Packages in multiple venvs: 234
# Packages with version conflicts: 45
#
# Top 20 most duplicated packages:
#
#   numpy: 12 copies
#     Versions: 1.21.0, 1.23.5, 1.24.0, 1.24.3, 1.26.0
#   requests: 11 copies
#     Versions: 2.28.0, 2.31.0
#   pandas: 9 copies
#     Versions: 1.5.3, 2.0.0, 2.1.0
#   ...

# This shows you numpy is installed 12 times in different venvs!
```

## Scenario 3: Cleaning Old Virtual Environments

You have old projects you don't use anymore.

```bash
# Step 1: Look for old venvs
./broomstick venvs | grep "2022"

# Output:
# [venv]       234.5MB    old-project      2022-03-12 09:30
# [pipenv]     156.2MB    test-app-xyz     2022-07-15 14:22

# Step 2: Dry-run to see what would happen
./broomstick clean --target ~/.cache/pypoetry/virtualenvs/old-project --dry-run

# Output:
# Target: /Users/you/.cache/pypoetry/virtualenvs/old-project
# Size: 234.5MB
#
# [DRY RUN] Would delete the above

# Step 3: Actually delete it
./broomstick clean --target ~/.cache/pypoetry/virtualenvs/old-project

# Output:
# Target: /Users/you/.cache/pypoetry/virtualenvs/old-project
# Size: 234.5MB
#
# Are you sure you want to delete this? [y/N]: y
#
# ✓ Deleted /Users/you/.cache/pypoetry/virtualenvs/old-project
```

## Scenario 4: Interactive Cleanup Session

You want to browse and clean interactively.

```bash
# Launch interactive mode
./broomstick

# You'll see a menu:
# 
# BROOMSTICK - Python Environment Cleaner
# 
# 1. Python Interpreters (8 found)
# 2. Virtual Environments (23 found)
# 3. Package Analysis
# 4. Quit
#
# Use ↑/↓ to navigate, Enter to select, 'q' to quit

# Press Enter on "Virtual Environments"
# You'll see a list:
#
# Virtual Environments
# --------------------------------------------------------------------------------
# [ ] [conda]      1.8GB      data-science
# [ ] [poetry]     456.2MB    my-web-app-py3.11-...
# [X] [venv]       234.5MB    old-project          <- marked with space
# [ ] [venv]       156.2MB    test-venv
# ...
#
# ↑/↓: navigate | Space: mark | d: delete marked | ESC: back | 1 marked

# Navigation:
# - Use ↑/↓ arrow keys to move
# - Press Space to mark items for deletion
# - Press 'd' to delete all marked items
# - Press ESC to go back
# - Press 'q' to quit
```

## Scenario 5: Cleaning Multiple Environments

You want to clean several old poetry venvs at once.

```bash
# Step 1: See what's in poetry cache
ls -lh ~/.cache/pypoetry/virtualenvs/

# Step 2: Use interactive mode and mark multiple
./broomstick
# Navigate to Virtual Environments
# Use Space to mark multiple old venvs
# Press 'd' to delete them all

# Or use CLI with a script
for venv in old-project-1 old-project-2 old-project-3; do
  ./broomstick clean --target ~/.cache/pypoetry/virtualenvs/$venv-* --yes
done
```

## Scenario 6: Removing Old Python Versions

You have multiple Python versions from pyenv you don't need.

```bash
# Step 1: See all pyenv versions
./broomstick interpreters | grep pyenv

# Output:
# [pyenv]      1.2GB      3.9.0 (main, Oct  5 2020)
# [pyenv]      1.3GB      3.10.0 (main, Oct  4 2021)
# [pyenv]      1.4GB      3.11.5 (main, Aug 24 2023)

# Step 2: Remove old version (CAREFUL!)
# First verify it's not system
./broomstick interpreters

# Step 3: Delete using pyenv directly (safer)
pyenv uninstall 3.9.0

# Or if it's a conda env
conda env remove -n old-env-name
```

## Scenario 7: Regular Maintenance

Set up a monthly cleanup routine.

```bash
# Create a simple script: ~/bin/python-cleanup.sh
cat > ~/bin/python-cleanup.sh <<'EOF'
#!/bin/bash
echo "=== Python Environment Audit ==="
echo ""
echo "Interpreters:"
~/broomstick/broomstick interpreters
echo ""
echo "Virtual Environments:"
~/broomstick/broomstick venvs
echo ""
echo "Package Analysis:"
~/broomstick/broomstick packages
echo ""
echo "Review and clean old environments interactively:"
read -p "Launch interactive mode? [y/N]: " response
if [[ "$response" =~ ^[Yy]$ ]]; then
  ~/broomstick/broomstick
fi
EOF

chmod +x ~/bin/python-cleanup.sh

# Run monthly
~/bin/python-cleanup.sh
```

## Scenario 8: Pre-Project Cleanup

Before starting a new project, clean up old stuff.

```bash
# Quick audit
./broomstick venvs | head -20

# See package duplicates
./broomstick packages | grep -A 5 "Top duplicates"

# Launch interactive and mark old venvs
./broomstick

# Verify disk space saved
df -h ~
```

## Scenario 9: Using with CI/CD

Generate reports for your team about Python environment usage.

```bash
# Generate JSON report
./broomstick scan --json python-report-$(date +%Y%m%d).json

# Parse it with jq
cat python-report-*.json | jq '.venvs | length'
cat python-report-*.json | jq '.venvs | map(.size_bytes) | add'

# Email or post to Slack
```

## Scenario 10: Fast Scanning on macOS

Use mdfind for much faster discovery.

```bash
# First run might take a moment as Spotlight indexes
./broomstick --mdfind venvs

# Future runs are instant
./broomstick --mdfind scan --json quick-scan.json

# Works great for large systems
time ./broomstick --mdfind interpreters
# real    0m2.534s (vs 0m45s without --mdfind)
```

## Pro Tips

1. **Always dry-run first**: Use `--dry-run` to preview deletions
2. **Check size before deleting**: Look at the size to ensure you're deleting the right thing
3. **Export before major cleanup**: `./broomstick scan --json backup.json`
4. **Use mdfind on macOS**: Much faster for discovery
5. **Mark system interpreters as warning**: They show in red in TUI
6. **Review packages regularly**: Find bloated venvs with duplicate packages
7. **Keep pyenv/conda envs separate**: Don't mix management tools
8. **Document your venvs**: Name them clearly (project-python3.11)

## Common Issues

### "Permission denied"
```bash
chmod +x broomstick
chmod +x broomstick.py
```

### "Python not found"
```bash
python3 --version  # Make sure Python 3.8+ is installed
```

### "TUI doesn't work"
```bash
# Use CLI commands instead
./broomstick venvs
./broomstick interpreters
./broomstick packages
```

### "Scanning takes forever"
```bash
# Use --mdfind on macOS
./broomstick --mdfind scan

# Or reduce scan depth by only checking specific paths
./broomstick scan --paths ~/.pyenv ~/.cache/pypoetry
```

## Safety Checklist

Before deleting:

- [ ] Checked it's not a system path
- [ ] Verified the size makes sense
- [ ] Confirmed the last modified date
- [ ] Ran with --dry-run first
- [ ] Backed up if unsure (`./broomstick scan --json backup.json`)
- [ ] Checked it's not your current project's venv

Happy cleaning! 🧹
