#!/usr/bin/env python3
"""
broomstick - Clean up Python environments, interpreters, and packages

A Mole-inspired cleanup tool for Python: discover all Python installations,
virtual environments, and packages; analyze duplicates and outdated versions;
and interactively or programmatically remove what you don't need.

Usage:
  broomstick                              # Interactive TUI mode
  broomstick scan [--json FILE]           # Scan and save results
  broomstick interpreters                 # List all Python interpreters
  broomstick venvs                        # List all virtual environments
  broomstick packages                     # Analyze packages (duplicates, outdated)
  broomstick clean [--target PATH]        # Delete environments/interpreters
"""
from __future__ import annotations

import argparse
import concurrent.futures
import curses
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# ============================================================================
# Configuration and Constants
# ============================================================================

MANAGER_PATHS = {
    "pyenv": [
        "~/.pyenv/versions",
    ],
    "asdf": [
        "~/.asdf/installs/python",
    ],
    "pipx": [
        "~/.local/pipx/venvs",
    ],
    "poetry": [
        "~/.cache/pypoetry/virtualenvs",
        "~/.local/share/pypoetry/virtualenvs",
    ],
    "conda": [
        "~/miniconda3/envs",
        "~/anaconda3/envs",
        "~/miniforge3/envs",
        "/opt/miniconda3/envs",
        "/opt/anaconda3/envs",
    ],
    "pipenv": [
        "~/.local/share/virtualenvs",
    ],
    "hatch": [
        "~/.local/share/hatch/env/virtual",
    ],
    "pdm": [
        "~/.local/share/pdm/venvs",
    ],
}

# System Python paths to avoid deleting
SYSTEM_PYTHON_PATHS = [
    "/usr/bin/python",
    "/usr/bin/python2",
    "/usr/bin/python3",
    "/System/Library/Frameworks/Python.framework",
    "/Library/Frameworks/Python.framework",
    "C:\\Windows\\System32",
    "C:\\Python",
]

# Homebrew and other package manager paths
PACKAGE_MANAGER_PATHS = [
    "/opt/homebrew/bin/python",
    "/opt/homebrew/Cellar/python",
    "/usr/local/bin/python",
    "/usr/local/Cellar/python",
]

# Default scan paths for general search
DEFAULT_SCAN_PATHS = [
    "~",
    "/opt/homebrew",
    "/usr/local",
    "/opt",
]


# ============================================================================
# Utilities
# ============================================================================

def format_bytes(b: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024.0:
            return f"{b:.1f}{unit}"
        b /= 1024.0
    return f"{b:.1f}PB"


def format_datetime(ts: Optional[float]) -> str:
    """Format timestamp to human-readable string."""
    if ts is None:
        return "unknown"
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")


def get_dir_size(path: str) -> int:
    """Calculate total size of directory in bytes."""
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        total += os.path.getsize(fp)
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def is_system_path(path: str) -> bool:
    """Check if path is a system-managed Python."""
    abs_path = os.path.abspath(path)
    for sys_path in SYSTEM_PYTHON_PATHS:
        if abs_path.startswith(sys_path):
            return True
    return False


def run_python_command(python_exec: str, cmd: str, timeout: int = 10) -> Optional[str]:
    """Run a Python command and return output."""
    try:
        result = subprocess.run(
            [python_exec, "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


# ============================================================================
# Python Interpreter Detection
# ============================================================================

class PythonInterpreter:
    """Represents a Python interpreter installation."""
    
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.version: Optional[str] = None
        self.manager: Optional[str] = None
        self.is_system = is_system_path(path)
        self.size_bytes = 0
        self._detect_info()
    
    def _detect_info(self):
        """Detect version and manager."""
        # Get version
        ver_output = run_python_command(self.path, "import sys; print(sys.version)")
        if ver_output:
            self.version = ver_output.split('\n')[0]
        
        # Detect manager from path
        path_lower = self.path.lower()
        if '.pyenv' in path_lower:
            self.manager = 'pyenv'
        elif '.asdf' in path_lower:
            self.manager = 'asdf'
        elif 'conda' in path_lower or 'miniconda' in path_lower or 'anaconda' in path_lower:
            self.manager = 'conda'
        elif 'homebrew' in path_lower or 'cellar' in path_lower:
            self.manager = 'homebrew'
        elif self.is_system:
            self.manager = 'system'
        else:
            self.manager = 'unknown'
        
        # Calculate size of parent directory if it looks like a version dir
        parent = os.path.dirname(self.path)
        if os.path.basename(parent) == 'bin':
            version_dir = os.path.dirname(parent)
            if os.path.isdir(version_dir):
                self.size_bytes = get_dir_size(version_dir)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'version': self.version,
            'manager': self.manager,
            'is_system': self.is_system,
            'size_bytes': self.size_bytes,
        }


def find_python_interpreters(use_mdfind: bool = False) -> List[PythonInterpreter]:
    """Find all Python interpreters on the system."""
    interpreters = []
    found_paths: Set[str] = set()
    
    # 1. Check manager-specific paths
    for manager, paths in MANAGER_PATHS.items():
        for path_template in paths:
            path = os.path.expanduser(path_template)
            if not os.path.exists(path):
                continue
            
            try:
                for entry in os.scandir(path):
                    if entry.is_dir(follow_symlinks=False):
                        # Look for bin/python*
                        bin_dir = os.path.join(entry.path, 'bin')
                        if os.path.isdir(bin_dir):
                            for py_name in ['python', 'python3', 'python2']:
                                py_path = os.path.join(bin_dir, py_name)
                                if os.path.exists(py_path) and os.access(py_path, os.X_OK):
                                    abs_path = os.path.abspath(os.path.realpath(py_path))
                                    if abs_path not in found_paths:
                                        found_paths.add(abs_path)
                                        interpreters.append(PythonInterpreter(abs_path))
            except PermissionError:
                continue
    
    # 2. Check PATH
    path_env = os.environ.get('PATH', '')
    for path_dir in path_env.split(os.pathsep):
        if path_dir and os.path.isdir(path_dir):
            for py_name in ['python', 'python3', 'python2']:
                py_path = os.path.join(path_dir, py_name)
                if os.path.exists(py_path) and os.access(py_path, os.X_OK):
                    abs_path = os.path.abspath(os.path.realpath(py_path))
                    if abs_path not in found_paths:
                        found_paths.add(abs_path)
                        interpreters.append(PythonInterpreter(abs_path))
    
    # 3. macOS-specific: use mdfind if available
    if use_mdfind and platform.system() == 'Darwin':
        try:
            result = subprocess.run(
                ['mdfind', 'kMDItemFSName == python3'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and os.path.exists(line) and os.access(line, os.X_OK):
                        abs_path = os.path.abspath(os.path.realpath(line))
                        if abs_path not in found_paths:
                            found_paths.add(abs_path)
                            interpreters.append(PythonInterpreter(abs_path))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    
    return interpreters


# ============================================================================
# Virtual Environment Detection
# ============================================================================

class VirtualEnv:
    """Represents a Python virtual environment."""
    
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.name = os.path.basename(path)
        self.python_version: Optional[str] = None
        self.manager: Optional[str] = None
        self.size_bytes = 0
        self.last_modified: Optional[float] = None
        self.packages: List[Dict[str, str]] = []
        self.python_executable: Optional[str] = None
        self._detect_info()
    
    def _detect_info(self):
        """Detect venv details."""
        # Find Python executable
        for candidate in ['bin/python', 'bin/python3', 'Scripts/python.exe']:
            py_path = os.path.join(self.path, candidate)
            if os.path.exists(py_path) and os.access(py_path, os.X_OK):
                self.python_executable = py_path
                break
        
        # Get Python version
        if self.python_executable:
            ver = run_python_command(self.python_executable, "import sys; print(sys.version)")
            if ver:
                self.python_version = ver.split('\n')[0]
        
        # Detect manager from path
        path_lower = self.path.lower()
        if '.pyenv' in path_lower:
            self.manager = 'pyenv'
        elif 'pipx' in path_lower:
            self.manager = 'pipx'
        elif 'poetry' in path_lower:
            self.manager = 'poetry'
        elif 'conda' in path_lower or 'miniconda' in path_lower or 'anaconda' in path_lower:
            self.manager = 'conda'
        elif 'virtualenvs' in path_lower or 'pipenv' in path_lower:
            self.manager = 'pipenv'
        elif 'hatch' in path_lower:
            self.manager = 'hatch'
        elif 'pdm' in path_lower:
            self.manager = 'pdm'
        else:
            self.manager = 'venv'
        
        # Size and last modified
        self.size_bytes = get_dir_size(self.path)
        try:
            self.last_modified = os.path.getmtime(self.path)
        except OSError:
            self.last_modified = None
    
    def probe_packages(self):
        """Probe installed packages in this venv."""
        if not self.python_executable:
            return
        
        try:
            result = subprocess.run(
                [self.python_executable, '-m', 'pip', 'list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0:
                self.packages = json.loads(result.stdout)
        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
            pass
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'name': self.name,
            'python_version': self.python_version,
            'manager': self.manager,
            'size_bytes': self.size_bytes,
            'last_modified': self.last_modified,
            'packages': len(self.packages),
        }


def is_venv(path: str) -> bool:
    """Check if a path is a virtual environment."""
    if not os.path.isdir(path):
        return False
    
    markers = [
        'pyvenv.cfg',
        os.path.join('bin', 'activate'),
        os.path.join('Scripts', 'activate.bat'),
    ]
    
    return any(os.path.exists(os.path.join(path, m)) for m in markers)


def find_venvs(use_mdfind: bool = False) -> List[VirtualEnv]:
    """Find all virtual environments."""
    venvs = []
    found_paths: Set[str] = set()
    
    # 1. Check manager-specific paths
    for manager, paths in MANAGER_PATHS.items():
        for path_template in paths:
            path = os.path.expanduser(path_template)
            if not os.path.exists(path):
                continue
            
            try:
                for entry in os.scandir(path):
                    if entry.is_dir(follow_symlinks=False):
                        if is_venv(entry.path):
                            abs_path = os.path.abspath(entry.path)
                            if abs_path not in found_paths:
                                found_paths.add(abs_path)
                                venvs.append(VirtualEnv(abs_path))
            except PermissionError:
                continue
    
    # 2. Scan common project locations (but not too deep)
    home = os.path.expanduser("~")
    for scan_dir in [home]:
        if not os.path.isdir(scan_dir):
            continue
        
        try:
            for entry in os.scandir(scan_dir):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                
                # Check if this dir itself is a venv
                if is_venv(entry.path):
                    abs_path = os.path.abspath(entry.path)
                    if abs_path not in found_paths:
                        found_paths.add(abs_path)
                        venvs.append(VirtualEnv(abs_path))
                    continue
                
                # Check for common venv subdirs
                for venv_name in ['.venv', 'venv', 'env', '.env']:
                    venv_path = os.path.join(entry.path, venv_name)
                    if is_venv(venv_path):
                        abs_path = os.path.abspath(venv_path)
                        if abs_path not in found_paths:
                            found_paths.add(abs_path)
                            venvs.append(VirtualEnv(abs_path))
        except PermissionError:
            continue
    
    # 3. Use mdfind on macOS for fast discovery
    if use_mdfind and platform.system() == 'Darwin':
        try:
            result = subprocess.run(
                ['mdfind', 'kMDItemFSName == pyvenv.cfg'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        venv_path = os.path.dirname(line)
                        if is_venv(venv_path):
                            abs_path = os.path.abspath(venv_path)
                            if abs_path not in found_paths:
                                found_paths.add(abs_path)
                                venvs.append(VirtualEnv(abs_path))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    
    return venvs


# ============================================================================
# Package Analysis
# ============================================================================

class PackageAnalyzer:
    """Analyze packages across all environments."""
    
    def __init__(self, venvs: List[VirtualEnv]):
        self.venvs = venvs
        self.package_map: Dict[str, List[Tuple[str, VirtualEnv]]] = defaultdict(list)
        self._build_map()
    
    def _build_map(self):
        """Build a map of package name -> [(version, venv)]."""
        for venv in self.venvs:
            if not venv.packages:
                venv.probe_packages()
            
            for pkg in venv.packages:
                name = pkg.get('name', '').lower()
                version = pkg.get('version', '')
                self.package_map[name].append((version, venv))
    
    def get_duplicates(self) -> Dict[str, List[Tuple[str, VirtualEnv]]]:
        """Return packages that appear in multiple venvs."""
        return {
            name: installs
            for name, installs in self.package_map.items()
            if len(installs) > 1
        }
    
    def get_version_conflicts(self) -> Dict[str, Set[str]]:
        """Return packages with different versions across venvs."""
        conflicts = {}
        for name, installs in self.package_map.items():
            versions = set(v for v, _ in installs)
            if len(versions) > 1:
                conflicts[name] = versions
        return conflicts


# ============================================================================
# Interactive TUI
# ============================================================================

class BroomstickTUI:
    """Interactive terminal UI for browsing and cleaning."""
    
    def __init__(self, interpreters: List[PythonInterpreter], venvs: List[VirtualEnv]):
        self.interpreters = interpreters
        self.venvs = venvs
        self.current_view = 'main'  # main, interpreters, venvs, packages
        self.cursor = 0
        self.scroll_offset = 0
        self.selected_items: Set[int] = set()
        self.to_delete: List[Any] = []
    
    def run(self, stdscr):
        """Main TUI loop."""
        curses.curs_set(0)  # Hide cursor
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selected
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)    # Warning
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Success
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)   # Info
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            if self.current_view == 'main':
                self._draw_main_menu(stdscr, height, width)
            elif self.current_view == 'interpreters':
                self._draw_interpreters(stdscr, height, width)
            elif self.current_view == 'venvs':
                self._draw_venvs(stdscr, height, width)
            elif self.current_view == 'packages':
                self._draw_packages(stdscr, height, width)
            
            stdscr.refresh()
            
            # Handle input
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == curses.KEY_UP:
                self.cursor = max(0, self.cursor - 1)
            elif key == curses.KEY_DOWN:
                self.cursor += 1
            elif key == ord('\n') or key == curses.KEY_ENTER or key == 10:
                self._handle_enter()
            elif key == ord(' '):
                self._toggle_selection()
            elif key == ord('d'):
                self._mark_for_deletion()
            elif key == 27:  # ESC
                self._go_back()
    
    def _draw_main_menu(self, stdscr, height, width):
        """Draw main menu."""
        title = "BROOMSTICK - Python Environment Cleaner"
        stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
        
        menu_items = [
            f"1. Python Interpreters ({len(self.interpreters)} found)",
            f"2. Virtual Environments ({len(self.venvs)} found)",
            "3. Package Analysis",
            "4. Quit",
        ]
        
        start_y = 3
        for i, item in enumerate(menu_items):
            attr = curses.color_pair(1) if i == self.cursor else curses.A_NORMAL
            stdscr.addstr(start_y + i, 2, item, attr)
        
        stdscr.addstr(height - 2, 2, "Use ↑/↓ to navigate, Enter to select, 'q' to quit")
    
    def _draw_interpreters(self, stdscr, height, width):
        """Draw Python interpreters list."""
        stdscr.addstr(0, 0, "Python Interpreters", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * width)
        
        list_height = height - 5
        visible_items = self.interpreters[self.scroll_offset:self.scroll_offset + list_height]
        
        for i, interp in enumerate(visible_items):
            y = i + 2
            if y >= height - 3:
                break
            
            idx = self.scroll_offset + i
            is_selected = idx == self.cursor
            is_marked = idx in self.selected_items
            
            # Format line
            manager = f"[{interp.manager}]".ljust(12)
            size = format_bytes(interp.size_bytes).rjust(10)
            version = (interp.version or "unknown")[:40]
            
            line = f"{manager} {size}  {version}"
            if len(line) > width - 4:
                line = line[:width - 4]
            
            prefix = "[X] " if is_marked else "[ ] "
            
            attr = curses.color_pair(1) if is_selected else curses.A_NORMAL
            if interp.is_system:
                attr |= curses.color_pair(2)
            
            stdscr.addstr(y, 2, prefix + line, attr)
        
        # Status bar
        status = f"↑/↓: navigate | Space: mark | d: delete marked | ESC: back | {len(self.selected_items)} marked"
        stdscr.addstr(height - 1, 0, status[:width-1])
    
    def _draw_venvs(self, stdscr, height, width):
        """Draw virtual environments list."""
        stdscr.addstr(0, 0, "Virtual Environments", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * width)
        
        list_height = height - 5
        visible_items = self.venvs[self.scroll_offset:self.scroll_offset + list_height]
        
        for i, venv in enumerate(visible_items):
            y = i + 2
            if y >= height - 3:
                break
            
            idx = self.scroll_offset + i
            is_selected = idx == self.cursor
            is_marked = idx in self.selected_items
            
            # Format line
            manager = f"[{venv.manager}]".ljust(12)
            size = format_bytes(venv.size_bytes).rjust(10)
            name = venv.name[:30]
            
            line = f"{manager} {size}  {name}"
            if len(line) > width - 4:
                line = line[:width - 4]
            
            prefix = "[X] " if is_marked else "[ ] "
            
            attr = curses.color_pair(1) if is_selected else curses.A_NORMAL
            stdscr.addstr(y, 2, prefix + line, attr)
        
        # Status bar
        total_size = sum(v.size_bytes for v in self.venvs)
        marked_size = sum(self.venvs[i].size_bytes for i in self.selected_items if i < len(self.venvs))
        status = f"Total: {format_bytes(total_size)} | Marked: {len(self.selected_items)} ({format_bytes(marked_size)}) | Space: mark | d: delete | ESC: back"
        stdscr.addstr(height - 1, 0, status[:width-1])
    
    def _draw_packages(self, stdscr, height, width):
        """Draw package analysis."""
        stdscr.addstr(0, 0, "Package Analysis", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * width)
        
        analyzer = PackageAnalyzer(self.venvs)
        duplicates = analyzer.get_duplicates()
        conflicts = analyzer.get_version_conflicts()
        
        y = 3
        stdscr.addstr(y, 2, f"Total unique packages: {len(analyzer.package_map)}")
        y += 1
        stdscr.addstr(y, 2, f"Duplicated across venvs: {len(duplicates)}")
        y += 1
        stdscr.addstr(y, 2, f"Version conflicts: {len(conflicts)}")
        y += 2
        
        stdscr.addstr(y, 2, "Top duplicates:", curses.A_BOLD)
        y += 1
        
        sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        for name, installs in sorted_dups:
            versions = set(v for v, _ in installs)
            line = f"  {name}: {len(installs)} copies, versions: {', '.join(sorted(versions))}"
            if y < height - 2:
                stdscr.addstr(y, 2, line[:width-4])
                y += 1
        
        stdscr.addstr(height - 1, 0, "Press ESC to go back")
    
    def _handle_enter(self):
        """Handle Enter key."""
        if self.current_view == 'main':
            if self.cursor == 0:
                self.current_view = 'interpreters'
                self.cursor = 0
                self.scroll_offset = 0
            elif self.cursor == 1:
                self.current_view = 'venvs'
                self.cursor = 0
                self.scroll_offset = 0
            elif self.cursor == 2:
                self.current_view = 'packages'
            elif self.cursor == 3:
                sys.exit(0)
    
    def _toggle_selection(self):
        """Toggle selection of current item."""
        if self.current_view in ['interpreters', 'venvs']:
            if self.cursor in self.selected_items:
                self.selected_items.remove(self.cursor)
            else:
                self.selected_items.add(self.cursor)
    
    def _mark_for_deletion(self):
        """Mark selected items for deletion."""
        if self.current_view == 'venvs':
            for idx in self.selected_items:
                if idx < len(self.venvs):
                    self.to_delete.append(self.venvs[idx])
        elif self.current_view == 'interpreters':
            for idx in self.selected_items:
                if idx < len(self.interpreters):
                    interp = self.interpreters[idx]
                    if not interp.is_system:
                        self.to_delete.append(interp)
        
        self.selected_items.clear()
    
    def _go_back(self):
        """Go back to main menu."""
        self.current_view = 'main'
        self.cursor = 0
        self.scroll_offset = 0


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_scan(args):
    """Scan for all Python resources."""
    print("Scanning for Python interpreters...")
    interpreters = find_python_interpreters(use_mdfind=args.mdfind)
    
    print("Scanning for virtual environments...")
    venvs = find_venvs(use_mdfind=args.mdfind)
    
    # Probe packages if requested
    if not args.no_packages:
        print("Probing packages (this may take a while)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
            executor.map(lambda v: v.probe_packages(), venvs)
    
    data = {
        'scan_time': time.time(),
        'interpreters': [i.to_dict() for i in interpreters],
        'venvs': [v.to_dict() for v in venvs],
    }
    
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nResults saved to {args.json}")
    else:
        print(f"\nFound {len(interpreters)} Python interpreters")
        print(f"Found {len(venvs)} virtual environments")


def cmd_interpreters(args):
    """List all Python interpreters."""
    interpreters = find_python_interpreters(use_mdfind=args.mdfind)
    
    print(f"\nFound {len(interpreters)} Python interpreters:\n")
    print(f"{'Manager':<12} {'Size':<10} {'Version'}")
    print("-" * 80)
    
    for interp in sorted(interpreters, key=lambda x: x.size_bytes, reverse=True):
        manager = f"[{interp.manager}]"
        size = format_bytes(interp.size_bytes)
        version = (interp.version or "unknown")[:50]
        marker = " (system)" if interp.is_system else ""
        print(f"{manager:<12} {size:<10} {version}{marker}")
    
    total_size = sum(i.size_bytes for i in interpreters)
    print(f"\nTotal size: {format_bytes(total_size)}")


def cmd_venvs(args):
    """List all virtual environments."""
    venvs = find_venvs(use_mdfind=args.mdfind)
    
    print(f"\nFound {len(venvs)} virtual environments:\n")
    print(f"{'Manager':<12} {'Size':<10} {'Name':<30} {'Modified'}")
    print("-" * 80)
    
    for venv in sorted(venvs, key=lambda x: x.size_bytes, reverse=True):
        manager = f"[{venv.manager}]"
        size = format_bytes(venv.size_bytes)
        name = venv.name[:30]
        modified = format_datetime(venv.last_modified)
        print(f"{manager:<12} {size:<10} {name:<30} {modified}")
    
    total_size = sum(v.size_bytes for v in venvs)
    print(f"\nTotal size: {format_bytes(total_size)}")


def cmd_packages(args):
    """Analyze packages across environments."""
    print("Scanning virtual environments...")
    venvs = find_venvs(use_mdfind=args.mdfind)
    
    print("Analyzing packages...")
    analyzer = PackageAnalyzer(venvs)
    
    duplicates = analyzer.get_duplicates()
    conflicts = analyzer.get_version_conflicts()
    
    print(f"\n{'='*80}")
    print(f"Package Analysis")
    print(f"{'='*80}\n")
    print(f"Total unique packages: {len(analyzer.package_map)}")
    print(f"Packages in multiple venvs: {len(duplicates)}")
    print(f"Packages with version conflicts: {len(conflicts)}\n")
    
    if duplicates:
        print("Top 20 most duplicated packages:\n")
        sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:20]
        
        for name, installs in sorted_dups:
            versions = set(v for v, _ in installs)
            print(f"  {name}: {len(installs)} copies")
            print(f"    Versions: {', '.join(sorted(versions))}")


def cmd_clean(args):
    """Delete environments or interpreters."""
    if not args.target:
        print("Error: --target PATH required")
        return 1
    
    target = os.path.abspath(args.target)
    
    if not os.path.exists(target):
        print(f"Error: {target} does not exist")
        return 1
    
    if is_system_path(target):
        print(f"Error: Refusing to delete system path: {target}")
        return 1
    
    size = get_dir_size(target) if os.path.isdir(target) else os.path.getsize(target)
    
    print(f"\nTarget: {target}")
    print(f"Size: {format_bytes(size)}")
    
    if args.dry_run:
        print("\n[DRY RUN] Would delete the above")
        return 0
    
    if not args.yes:
        response = input("\nAre you sure you want to delete this? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Cancelled")
            return 0
    
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        print(f"\n✓ Deleted {target}")
    except Exception as e:
        print(f"\n✗ Error deleting: {e}")
        return 1
    
    return 0


def cmd_interactive(args):
    """Launch interactive TUI."""
    print("Scanning for Python resources...")
    interpreters = find_python_interpreters(use_mdfind=args.mdfind)
    venvs = find_venvs(use_mdfind=args.mdfind)
    
    print(f"Found {len(interpreters)} interpreters and {len(venvs)} virtual environments")
    print("Launching interactive mode...\n")
    
    time.sleep(1)
    
    tui = BroomstickTUI(interpreters, venvs)
    curses.wrapper(tui.run)


# ============================================================================
# Main
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='broomstick',
        description='Clean up Python environments, interpreters, and packages'
    )
    parser.add_argument('--mdfind', action='store_true', help='Use mdfind on macOS for faster scanning')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # scan
    scan_parser = subparsers.add_parser('scan', help='Scan for all Python resources')
    scan_parser.add_argument('--json', help='Save results to JSON file')
    scan_parser.add_argument('--no-packages', action='store_true', help='Skip package probing')
    scan_parser.add_argument('--parallel', type=int, default=4, help='Parallel workers for package probing')
    
    # interpreters
    interp_parser = subparsers.add_parser('interpreters', help='List all Python interpreters')
    
    # venvs
    venv_parser = subparsers.add_parser('venvs', help='List all virtual environments')
    
    # packages
    pkg_parser = subparsers.add_parser('packages', help='Analyze packages')
    
    # clean
    clean_parser = subparsers.add_parser('clean', help='Delete environments or interpreters')
    clean_parser.add_argument('--target', help='Path to delete')
    clean_parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    clean_parser.add_argument('--yes', action='store_true', help='Skip confirmation')
    
    # interactive (default)
    interactive_parser = subparsers.add_parser('interactive', help='Launch interactive TUI (default)')
    
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    
    if not args.command or args.command == 'interactive':
        return cmd_interactive(args)
    elif args.command == 'scan':
        return cmd_scan(args)
    elif args.command == 'interpreters':
        return cmd_interpreters(args)
    elif args.command == 'venvs':
        return cmd_venvs(args)
    elif args.command == 'packages':
        return cmd_packages(args)
    elif args.command == 'clean':
        return cmd_clean(args)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
