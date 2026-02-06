#!/usr/bin/env python3
"""
broomstick - Comprehensive Python environment and package cleaner

A Mole-inspired cleanup tool for Python: discover all Python installations,
virtual environments, and packages; drill down to package level; analyze
duplicates and outdated versions; and interactively or programmatically
remove what you don't need.

Usage:
  broomstick                                    # Interactive TUI mode
  broomstick scan [--json FILE]                 # Scan and save results
  broomstick interpreters                       # List all Python interpreters
  broomstick venvs [--path PATH]                # List virtual environments
  broomstick packages [--venv PATH]             # List/analyze packages
  broomstick uninstall PKG --from VENV          # Uninstall package from venv
  broomstick clean [--target PATH]              # Delete environments/interpreters
  broomstick search PATTERN                     # Search for venvs or packages
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ============================================================================
# Configuration and Constants
# ============================================================================

MANAGER_PATHS = {
    "pyenv": ["~/.pyenv/versions"],
    "asdf": ["~/.asdf/installs/python"],
    "pipx": ["~/.local/pipx/venvs"],
    "poetry": ["~/.cache/pypoetry/virtualenvs", "~/.local/share/pypoetry/virtualenvs"],
    "conda": ["~/miniconda3/envs", "~/anaconda3/envs", "~/miniforge3/envs", 
              "/opt/miniconda3/envs", "/opt/anaconda3/envs"],
    "pipenv": ["~/.local/share/virtualenvs"],
    "hatch": ["~/.local/share/hatch/env/virtual"],
    "pdm": ["~/.local/share/pdm/venvs"],
    "uv": ["~/.local/share/uv/venvs", "~/.cache/uv/venvs"],
}

SYSTEM_PYTHON_PATHS = [
    "/usr/bin/python", "/usr/bin/python2", "/usr/bin/python3",
    "/System/Library/Frameworks/Python.framework",
    "/Library/Frameworks/Python.framework",
    "C:\\Windows\\System32", "C:\\Python",
]

PROJECT_VENV_NAMES = [".venv", "venv", "env", ".env", "virtualenv"]
DEFAULT_SCAN_PATHS = ["~"]

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
    now = datetime.now()
    delta = now - dt
    if delta.days > 365:
        return f"{delta.days // 365}y ago"
    elif delta.days > 30:
        return f"{delta.days // 30}mo ago"
    elif delta.days > 0:
        return f"{delta.days}d ago"
    else:
        return "today"

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
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None

def get_project_name(venv_path: str) -> str:
    """Try to infer project name from venv path."""
    path = Path(venv_path)
    if path.name in PROJECT_VENV_NAMES:
        return path.parent.name
    return path.name

def shorten_path(path: str, max_len: int = 50) -> str:
    """Shorten path for display."""
    if len(path) <= max_len:
        return path
    parts = path.split(os.sep)
    if len(parts) <= 3:
        return path
    return f"...{os.sep}{os.sep.join(parts[-2:])}"

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
        ver_output = run_python_command(self.path, "import sys; print(sys.version)")
        if ver_output:
            self.version = ver_output.split('\n')[0]
        
        path_lower = self.path.lower()
        if '.pyenv' in path_lower:
            self.manager = 'pyenv'
        elif '.asdf' in path_lower:
            self.manager = 'asdf'
        elif 'conda' in path_lower or 'miniconda' in path_lower or 'anaconda' in path_lower:
            self.manager = 'conda'
        elif 'homebrew' in path_lower or 'cellar' in path_lower:
            self.manager = 'homebrew'
        elif 'uv' in path_lower:
            self.manager = 'uv'
        elif self.is_system:
            self.manager = 'system'
        else:
            self.manager = 'unknown'
        
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
    
    for manager, paths in MANAGER_PATHS.items():
        for path_template in paths:
            path = os.path.expanduser(path_template)
            if not os.path.exists(path):
                continue
            try:
                for entry in os.scandir(path):
                    if entry.is_dir(follow_symlinks=False):
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
    
    if use_mdfind and platform.system() == 'Darwin':
        try:
            result = subprocess.run(
                ['mdfind', 'kMDItemFSName == python3'],
                capture_output=True, text=True, timeout=30
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
# Package Management
# ============================================================================

class Package:
    """Represents an installed Python package."""
    
    def __init__(self, name: str, version: str, size_bytes: int = 0):
        self.name = name
        self.version = version
        self.size_bytes = size_bytes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'version': self.version,
            'size_bytes': self.size_bytes,
        }

# ============================================================================
# Virtual Environment Detection
# ============================================================================

class VirtualEnv:
    """Represents a Python virtual environment."""
    
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.name = os.path.basename(path)
        self.project_name = get_project_name(path)
        self.python_version: Optional[str] = None
        self.manager: Optional[str] = None
        self.size_bytes = 0
        self.last_modified: Optional[float] = None
        self.packages: List[Package] = []
        self.python_executable: Optional[str] = None
        self.packages_loaded = False
        self._detect_info()
    
    def _detect_info(self):
        """Detect venv details."""
        for candidate in ['bin/python', 'bin/python3', 'Scripts/python.exe']:
            py_path = os.path.join(self.path, candidate)
            if os.path.exists(py_path) and os.access(py_path, os.X_OK):
                self.python_executable = py_path
                break
        
        if self.python_executable:
            ver = run_python_command(self.python_executable, "import sys; print(sys.version)")
            if ver:
                self.python_version = ver.split('\n')[0]
        
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
        elif 'uv' in path_lower:
            self.manager = 'uv'
        else:
            self.manager = 'venv'
        
        self.size_bytes = get_dir_size(self.path)
        try:
            self.last_modified = os.path.getmtime(self.path)
        except OSError:
            self.last_modified = None
    
    def probe_packages(self, force: bool = False):
        """Probe installed packages in this venv."""
        if self.packages_loaded and not force:
            return
        
        if not self.python_executable:
            return
        
        try:
            result = subprocess.run(
                [self.python_executable, '-m', 'pip', 'list', '--format=json'],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                pkg_list = json.loads(result.stdout)
                self.packages = [Package(p['name'], p['version']) for p in pkg_list]
                self.packages_loaded = True
        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
            pass
    
    def uninstall_package(self, package_name: str, dry_run: bool = False) -> bool:
        """Uninstall a specific package from this venv."""
        if not self.python_executable:
            return False
        
        if dry_run:
            print(f"[DRY RUN] Would uninstall {package_name} from {self.path}")
            return True
        
        try:
            result = subprocess.run(
                [self.python_executable, '-m', 'pip', 'uninstall', '-y', package_name],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'name': self.name,
            'project_name': self.project_name,
            'python_version': self.python_version,
            'manager': self.manager,
            'size_bytes': self.size_bytes,
            'last_modified': self.last_modified,
            'package_count': len(self.packages) if self.packages_loaded else None,
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

def find_venvs(scan_path: Optional[str] = None, use_mdfind: bool = False, max_depth: int = 3) -> List[VirtualEnv]:
    """Find all virtual environments."""
    venvs = []
    found_paths: Set[str] = set()
    
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
    
    scan_root = os.path.expanduser(scan_path) if scan_path else os.path.expanduser("~")
    
    def scan_dir(root: str, depth: int = 0):
        """Recursively scan for venvs with depth limit."""
        if depth > max_depth:
            return
        
        try:
            for entry in os.scandir(root):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                
                if entry.name.startswith('.') and entry.name not in PROJECT_VENV_NAMES:
                    continue
                
                if entry.name in ['node_modules', 'Library', 'Applications', '.git', '__pycache__']:
                    continue
                
                if is_venv(entry.path):
                    abs_path = os.path.abspath(entry.path)
                    if abs_path not in found_paths:
                        found_paths.add(abs_path)
                        venvs.append(VirtualEnv(abs_path))
                else:
                    scan_dir(entry.path, depth + 1)
        except PermissionError:
            pass
    
    scan_dir(scan_root)
    
    if use_mdfind and platform.system() == 'Darwin':
        try:
            result = subprocess.run(
                ['mdfind', 'kMDItemFSName == pyvenv.cfg'],
                capture_output=True, text=True, timeout=30
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
            if not venv.packages_loaded:
                venv.probe_packages()
            
            for pkg in venv.packages:
                name = pkg.name.lower()
                self.package_map[name].append((pkg.version, venv))
    
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
    
    def find_package(self, pattern: str) -> List[Tuple[Package, VirtualEnv]]:
        """Find packages matching a pattern across all venvs."""
        results = []
        pattern_lower = pattern.lower()
        for venv in self.venvs:
            if not venv.packages_loaded:
                venv.probe_packages()
            for pkg in venv.packages:
                if pattern_lower in pkg.name.lower():
                    results.append((pkg, venv))
        return results

# ============================================================================
# Interactive TUI - Mole-Inspired Mode System
# ============================================================================

class BroomstickTUI:
    """Interactive terminal UI with Mole-inspired modes."""
    
    def __init__(self, interpreters: List[PythonInterpreter], venvs: List[VirtualEnv]):
        self.interpreters = interpreters
        self.venvs = venvs
        self.mode = None  # Current mode: list, delete, explore, package
        self.current_view = 'mode_select'
        self.selected_venv: Optional[VirtualEnv] = None
        self.cursor = 0
        self.scroll_offset = 0
        self.selected_items: Set[int] = set()
        self.breadcrumb = []
        self.show_help = False
        self.search_mode = False
        self.search_query = ""
        self.filtered_items = []
    
    def run(self, stdscr):
        """Main TUI loop."""
        curses.curs_set(0)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)   # Selected
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)     # Warning/Delete
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Success
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Info
        curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Highlight
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Special
        
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            
            # Draw based on current view
            if self.current_view == 'mode_select':
                self._draw_mode_select(stdscr, height, width)
            else:
                # Draw header with mode indicator
                self._draw_header(stdscr, width)
                
                # Draw content based on view
                if self.current_view == 'category_select':
                    self._draw_category_select(stdscr, height, width)
                elif self.current_view == 'interpreters':
                    self._draw_interpreters(stdscr, height, width)
                elif self.current_view == 'venvs':
                    self._draw_venvs(stdscr, height, width)
                elif self.current_view == 'venv_detail':
                    self._draw_venv_detail(stdscr, height, width)
                elif self.current_view == 'analysis':
                    self._draw_analysis(stdscr, height, width)
            
            # Draw help overlay if enabled
            if self.show_help:
                self._draw_help_overlay(stdscr, height, width)
            
            stdscr.refresh()
            
            # Handle input
            key = stdscr.getch()
            if key == ord('q'):
                if len(self.breadcrumb) > 0 or self.current_view != 'mode_select':
                    self._go_back()
                else:
                    break
            elif key == curses.KEY_UP:
                self.cursor = max(0, self.cursor - 1)
                self._adjust_scroll_for_view(height)
            elif key == curses.KEY_DOWN:
                self.cursor += 1
                self._adjust_scroll_for_view(height)
            elif key == ord('\n') or key == curses.KEY_ENTER or key == 10:
                self._handle_enter()
            elif key == ord(' ') and self.mode in ['delete', 'package']:
                self._toggle_selection()
            elif key == ord('d') and self.mode == 'delete':
                self._confirm_delete(stdscr)
            elif key == ord('u') and self.mode == 'package':
                self._confirm_uninstall(stdscr)
            elif key == 27:  # ESC
                if self.search_mode:
                    self.search_mode = False
                    self.search_query = ""
                    self.filtered_items = []
                else:
                    self._go_back()
            elif key == ord('h') or key == ord('?'):
                self.show_help = not self.show_help
            elif key == ord('/') and self.current_view in ['interpreters', 'venvs', 'venv_detail']:
                self._start_search(stdscr, height)
    
    
    def _start_search(self, stdscr, height):
        """Start search mode and filter items."""
        width = stdscr.getmaxyx()[1]
        prompt = "Search: "
        
        try:
            stdscr.addstr(height - 1, 2, prompt, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass
        
        stdscr.refresh()
        curses.echo()
        
        try:
            query = stdscr.getstr(height - 1, 2 + len(prompt), width - len(prompt) - 4).decode('utf-8')
        except:
            query = ""
        finally:
            curses.noecho()
        
        if query:
            self.search_query = query.lower()
            self.search_mode = True
            self._apply_search_filter()
            self.cursor = 0
            self.scroll_offset = 0
        else:
            self.search_mode = False
            self.search_query = ""
            self.filtered_items = []
    
    def _apply_search_filter(self):
        """Apply search filter to current view items."""
        self.filtered_items = []
        
        if self.current_view == 'interpreters':
            for i, interp in enumerate(self.interpreters):
                if (self.search_query in interp.version.lower() if interp.version else False) or \
                   (self.search_query in interp.manager.lower()) or \
                   (self.search_query in interp.path.lower()):
                    self.filtered_items.append(i)
        
        elif self.current_view == 'venvs':
            for i, venv in enumerate(self.venvs):
                if (self.search_query in venv.project_name.lower()) or \
                   (self.search_query in venv.manager.lower()) or \
                   (self.search_query in venv.path.lower()):
                    self.filtered_items.append(i)
        
        elif self.current_view == 'venv_detail' and self.selected_venv:
            for i, pkg in enumerate(self.selected_venv.packages):
                if (self.search_query in pkg.name.lower()) or \
                   (self.search_query in pkg.version.lower()):
                    self.filtered_items.append(i)
    
    def _get_current_items(self):
        """Get current list of items (filtered or unfiltered)."""
        if self.search_mode and self.filtered_items:
            if self.current_view == 'interpreters':
                return [self.interpreters[i] for i in self.filtered_items]
            elif self.current_view == 'venvs':
                return [self.venvs[i] for i in self.filtered_items]
            elif self.current_view == 'venv_detail' and self.selected_venv:
                return [self.selected_venv.packages[i] for i in self.filtered_items]
        else:
            if self.current_view == 'interpreters':
                return self.interpreters
            elif self.current_view == 'venvs':
                return self.venvs
            elif self.current_view == 'venv_detail' and self.selected_venv:
                return self.selected_venv.packages
        return []
    
    
    
    def _adjust_scroll_for_view(self, screen_height):
        """Adjust scroll based on current view."""
        visible_height = screen_height - 10  # Account for headers and footers
        
        if self.current_view == 'mode_select':
            max_items = 5  # 4 modes + quit
        elif self.current_view == 'category_select':
            max_items = 3 if self.mode == 'explore' else 2
        elif self.current_view == 'interpreters':
            max_items = len(self.interpreters)
        elif self.current_view == 'venvs':
            max_items = len(self.venvs)
        elif self.current_view == 'venv_detail':
            max_items = len(self.selected_venv.packages) if self.selected_venv else 0
        else:
            max_items = 0
        
        self._adjust_scroll(max_items, visible_height)
    
    def _adjust_scroll(self, max_items=None, visible_height=None):
        """Adjust scroll offset to keep cursor visible."""
        if visible_height is None or max_items is None:
            return
        
        # Ensure cursor is within bounds
        if max_items > 0:
            self.cursor = max(0, min(self.cursor, max_items - 1))
        
        # Adjust scroll to keep cursor visible
        if self.cursor < self.scroll_offset:
            self.scroll_offset = self.cursor
        elif self.cursor >= self.scroll_offset + visible_height:
            self.scroll_offset = self.cursor - visible_height + 1
        
        # Ensure scroll offset is within bounds
        max_scroll = max(0, max_items - visible_height)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
    
    def _draw_mode_select(self, stdscr, height, width):
        """Draw the initial mode selection screen (Mole-style)."""
        # Title
        title_lines = [
            "╔════════════════════════════════════════════════════════════════╗",
            "║                                                                ║",
            "║                  🧹  BROOMSTICK  🧹                           ║",
            "║                                                                ║",
            "║           Python Environment & Package Cleaner                 ║",
            "║                                                                ║",
            "╚════════════════════════════════════════════════════════════════╝",
        ]
        
        y = max(0, (height - 25) // 2)
        for i, line in enumerate(title_lines):
            x = max(0, (width - len(line)) // 2)
            try:
                stdscr.addstr(y + i, x, line, curses.color_pair(4) | curses.A_BOLD)
            except curses.error:
                pass
        
        y += len(title_lines) + 2
        
        # Stats
        stats_y = y
        total_size = sum(v.size_bytes for v in self.venvs)
        interp_size = sum(i.size_bytes for i in self.interpreters)
        
        stats = [
            f"Found: {len(self.interpreters)} Python interpreters ({format_bytes(interp_size)})",
            f"Found: {len(self.venvs)} virtual environments ({format_bytes(total_size)})",
        ]
        
        for i, stat in enumerate(stats):
            x = (width - len(stat)) // 2
            try:
                stdscr.addstr(stats_y + i, x, stat, curses.color_pair(3))
            except curses.error:
                pass
        
        y = stats_y + len(stats) + 2
        
        # Mode selection
        mode_header = "Select Mode:"
        x = (width - len(mode_header)) // 2
        try:
            stdscr.addstr(y, x, mode_header, curses.A_BOLD)
        except curses.error:
            pass
        
        y += 2
        
        modes = [
            ("List Mode", "Browse and explore environments (read-only)"),
            ("Delete Mode", "Remove unwanted environments and packages"),
            ("Analyze Mode", "Deep analysis of packages and duplicates"),
            ("Package Manager", "Manage packages within environments"),
            ("Quit", "Exit Broomstick"),
        ]
        
        for i, (name, desc) in enumerate(modes):
            is_selected = i == self.cursor
            
            if is_selected:
                attr = curses.color_pair(1) | curses.A_BOLD
            else:
                attr = curses.A_NORMAL
            
            # Mode name
            mode_text = f"  {i + 1}. {name}"
            x = (width - 60) // 2
            try:
                stdscr.addstr(y + i * 3, x, mode_text, attr)
            except curses.error:
                pass
            
            # Description
            desc_text = f"     {desc}"
            desc_attr = curses.color_pair(4) if is_selected else curses.color_pair(4) | curses.A_DIM
            try:
                stdscr.addstr(y + i * 3 + 1, x, desc_text, desc_attr)
            except curses.error:
                pass
        
        # Help text
        help_y = height - 3
        help_text = "Use ↑/↓ to navigate, Enter to select, 'q' to quit"
        x = (width - len(help_text)) // 2
        try:
            stdscr.addstr(help_y, x, help_text, curses.color_pair(5))
        except curses.error:
            pass
    
    def _draw_header(self, stdscr, width):
        """Draw header with mode and breadcrumb."""
        if not self.mode:
            return
        
        # Mode indicator
        mode_names = {
            'list': '📋 LIST MODE',
            'delete': '🗑️  DELETE MODE',
            'explore': '🔍 ANALYZE MODE',
            'package': '📦 PACKAGE MANAGER'
        }
        
        mode_text = mode_names.get(self.mode, 'BROOMSTICK')
        try:
            stdscr.addstr(0, 2, mode_text, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass
        
        # Breadcrumb
        if self.breadcrumb:
            crumb = " > ".join(self.breadcrumb)
            if len(crumb) > width - len(mode_text) - 10:
                crumb = "..." + crumb[-(width - len(mode_text) - 13):]
            try:
                stdscr.addstr(1, 2, crumb, curses.color_pair(4))
            except curses.error:
                pass
    
    def _draw_category_select(self, stdscr, height, width):
        """Draw category selection (Interpreters vs Venvs)."""
        start_y = 4
        
        title = "What would you like to manage?"
        try:
            stdscr.addstr(start_y, (width - len(title)) // 2, title, curses.A_BOLD)
        except curses.error:
            pass
        
        start_y += 3
        
        categories = [
            ("Python Interpreters", f"{len(self.interpreters)} found"),
            ("Virtual Environments", f"{len(self.venvs)} found"),
        ]
        
        if self.mode == 'explore':
            categories.append(("Package Analysis", "Duplicates & conflicts"))
        
        for i, (name, count) in enumerate(categories):
            is_selected = i == self.cursor
            attr = curses.color_pair(1) if is_selected else curses.A_NORMAL
            
            line = f"  {i + 1}. {name:<30} ({count})"
            try:
                stdscr.addstr(start_y + i * 2, 5, line, attr)
            except curses.error:
                pass
        
        # Mode-specific help
        help_y = height - 3
        if self.mode == 'delete':
            help_text = "Space: mark | d: delete marked | Enter: select | ESC: back"
        elif self.mode == 'package':
            help_text = "Enter: view packages | Space: mark | u: uninstall | ESC: back"
        else:
            help_text = "Enter: view details | ESC: back | q: quit"
        
        try:
            stdscr.addstr(help_y, 2, help_text[:width-4], curses.color_pair(5))
        except curses.error:
            pass
    
    def _draw_interpreters(self, stdscr, height, width):
        """Draw Python interpreters list."""
        start_y = 4
        
        header = "Python Interpreters"
        if self.search_mode:
            header += f" (searching: '{self.search_query}')"
        
        try:
            stdscr.addstr(start_y, 2, header, curses.A_BOLD)
            stdscr.addstr(start_y + 1, 2, "─" * min(width - 4, 76))
        except curses.error:
            pass
        
        list_y = start_y + 3
        list_height = height - list_y - 4
        
        items = self._get_current_items()
        visible_items = items[self.scroll_offset:self.scroll_offset + list_height]
        
        for i, interp in enumerate(visible_items):
            y = list_y + i
            if y >= height - 4:
                break
            
            idx = self.scroll_offset + i
            is_selected = idx == self.cursor
            
            # For marked items, need to map back to original index
            original_idx = self.filtered_items[idx] if self.search_mode and idx < len(self.filtered_items) else idx
            is_marked = original_idx in self.selected_items
            
            # Build line
            prefix = "[X] " if is_marked and self.mode == 'delete' else "[ ] " if self.mode == 'delete' else "  "
            manager = f"[{interp.manager}]".ljust(12)
            size = format_bytes(interp.size_bytes).rjust(10)
            version = (interp.version or "unknown")[:35]
            
            line = f"{prefix}{manager} {size}  {version}"
            
            # Color coding
            if is_selected:
                attr = curses.color_pair(1)
            elif interp.is_system:
                attr = curses.color_pair(2)
            else:
                attr = curses.A_NORMAL
            
            try:
                stdscr.addstr(y, 2, line[:width-4], attr)
            except curses.error:
                pass
        
        # Footer
        self._draw_footer(stdscr, height, width)
    
    def _draw_venvs(self, stdscr, height, width):
        """Draw virtual environments list."""
        start_y = 4
        
        header = "Virtual Environments"
        if self.search_mode:
            header += f" (searching: '{self.search_query}')"
        
        try:
            stdscr.addstr(start_y, 2, header, curses.A_BOLD)
            stdscr.addstr(start_y + 1, 2, "─" * min(width - 4, 76))
        except curses.error:
            pass
        
        list_y = start_y + 3
        list_height = height - list_y - 4
        
        items = self._get_current_items()
        visible_items = items[self.scroll_offset:self.scroll_offset + list_height]
        
        for i, venv in enumerate(visible_items):
            y = list_y + i
            if y >= height - 4:
                break
            
            idx = self.scroll_offset + i
            is_selected = idx == self.cursor
            
            # For marked items, need to map back to original index
            original_idx = self.filtered_items[idx] if self.search_mode and idx < len(self.filtered_items) else idx
            is_marked = original_idx in self.selected_items
            
            # Build line
            prefix = "[X] " if is_marked and self.mode in ['delete', 'package'] else "[ ] " if self.mode in ['delete', 'package'] else "  "
            manager = f"[{venv.manager}]".ljust(10)
            size = format_bytes(venv.size_bytes).rjust(9)
            age = format_datetime(venv.last_modified).rjust(8)
            project = venv.project_name[:25]
            
            line = f"{prefix}{manager} {size} {age}  {project}"
            
            # Color coding
            if is_selected:
                attr = curses.color_pair(1)
            else:
                attr = curses.A_NORMAL
            
            try:
                stdscr.addstr(y, 2, line[:width-4], attr)
            except curses.error:
                pass
        
        # Footer
        self._draw_footer(stdscr, height, width)
    
    def _draw_venv_detail(self, stdscr, height, width):
        """Draw detailed venv view with packages."""
        if not self.selected_venv:
            self._go_back()
            return
        
        venv = self.selected_venv
        start_y = 4
        
        # Header
        try:
            stdscr.addstr(start_y, 2, f"Virtual Environment: {venv.project_name}", curses.A_BOLD)
            stdscr.addstr(start_y + 1, 2, "─" * min(width - 4, 76))
        except curses.error:
            pass
        
        # Details
        y = start_y + 3
        details = [
            f"Path: {shorten_path(venv.path, width - 12)}",
            f"Manager: {venv.manager}",
            f"Size: {format_bytes(venv.size_bytes)}",
            f"Age: {format_datetime(venv.last_modified)}",
            f"Python: {venv.python_version or 'unknown'}",
        ]
        
        for detail in details:
            try:
                stdscr.addstr(y, 4, detail[:width-6], curses.color_pair(4))
            except curses.error:
                pass
            y += 1
        
        y += 1
        
        # Load packages if needed
        if not venv.packages_loaded:
            try:
                stdscr.addstr(y, 4, "Loading packages...", curses.color_pair(5))
            except curses.error:
                pass
            stdscr.refresh()
            venv.probe_packages()
        
        # Package list
        try:
            stdscr.addstr(y, 2, f"Packages ({len(venv.packages)}):", curses.A_BOLD)
            y += 1
            stdscr.addstr(y, 2, "─" * min(width - 4, 76))
        except curses.error:
            pass
        y += 1
        
        list_height = height - y - 4
        visible_pkgs = venv.packages[self.scroll_offset:self.scroll_offset + list_height]
        
        for i, pkg in enumerate(visible_pkgs):
            pkg_y = y + i
            if pkg_y >= height - 4:
                break
            
            idx = self.scroll_offset + i
            is_selected = idx == self.cursor
            is_marked = idx in self.selected_items
            
            prefix = "[X] " if is_marked and self.mode == 'package' else "[ ] " if self.mode == 'package' else "  "
            pkg_line = f"{prefix}{pkg.name.ljust(30)} {pkg.version.ljust(15)}"
            
            attr = curses.color_pair(1) if is_selected else curses.A_NORMAL
            
            try:
                stdscr.addstr(pkg_y, 4, pkg_line[:width-6], attr)
            except curses.error:
                pass
        
        # Footer
        self._draw_footer(stdscr, height, width)
    
    def _draw_analysis(self, stdscr, height, width):
        """Draw package analysis view."""
        start_y = 4
        
        try:
            stdscr.addstr(start_y, 2, "Package Analysis", curses.A_BOLD)
            stdscr.addstr(start_y + 1, 2, "─" * min(width - 4, 76))
        except curses.error:
            pass
        
        y = start_y + 3
        
        try:
            stdscr.addstr(y, 2, "Analyzing packages across environments...", curses.color_pair(5))
        except curses.error:
            pass
        stdscr.refresh()
        
        analyzer = PackageAnalyzer(self.venvs)
        duplicates = analyzer.get_duplicates()
        conflicts = analyzer.get_version_conflicts()
        
        y += 2
        
        summary = [
            f"Total unique packages: {len(analyzer.package_map)}",
            f"Duplicated across venvs: {len(duplicates)}",
            f"Version conflicts: {len(conflicts)}",
        ]
        
        for line in summary:
            try:
                stdscr.addstr(y, 2, line, curses.color_pair(3))
            except curses.error:
                pass
            y += 1
        
        y += 2
        try:
            stdscr.addstr(y, 2, "Top Duplicates:", curses.A_BOLD)
        except curses.error:
            pass
        y += 1
        
        sorted_dups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:15]
        
        for name, installs in sorted_dups:
            if y >= height - 4:
                break
            versions = set(v for v, _ in installs)
            line = f"  {name}: {len(installs)} copies ({', '.join(list(versions)[:3])})"
            try:
                stdscr.addstr(y, 2, line[:width-4])
            except curses.error:
                pass
            y += 1
        
        # Footer
        self._draw_footer(stdscr, height, width)
    
    def _draw_footer(self, stdscr, height, width):
        """Draw mode-specific footer."""
        footer_y = height - 2
        
        if self.mode == 'list':
            text = "Enter: details | /: search | h: help | ESC/q: back"
        elif self.mode == 'delete':
            marked_count = len(self.selected_items)
            marked_size = 0
            if self.current_view == 'venvs':
                marked_size = sum(self.venvs[i].size_bytes for i in self.selected_items if i < len(self.venvs))
            text = f"Space: mark | d: delete {marked_count} items ({format_bytes(marked_size)}) | /: search | ESC: back"
        elif self.mode == 'package':
            marked_count = len(self.selected_items)
            text = f"Space: mark | u: uninstall {marked_count} pkgs | /: search | ESC: back"
        elif self.mode == 'explore':
            text = "Enter: details | /: search | h: help | ESC: back"
        else:
            text = "↑/↓: navigate | Enter: select | ESC/q: back"
        
        try:
            stdscr.addstr(footer_y, 2, text[:width-4], curses.color_pair(5))
        except curses.error:
            pass
    
    def _draw_help_overlay(self, stdscr, height, width):
        """Draw help overlay in the center of screen."""
        help_lines = [
            "╔════════════════════════════════════════════════════════════╗",
            "║                        HELP                                 ║",
            "╠════════════════════════════════════════════════════════════╣",
            "║  Navigation:                                                ║",
            "║    ↑/↓        - Move cursor up/down                         ║",
            "║    Enter      - Select item / view details                  ║",
            "║    ESC / q    - Go back / quit                              ║",
            "║                                                              ║",
            "║  Modes:                                                      ║",
            "║    List       - Browse environments (read-only)              ║",
            "║    Delete     - Remove environments and packages             ║",
            "║    Analyze    - View duplicates and conflicts                ║",
            "║    Package    - Manage packages within venvs                 ║",
            "║                                                              ║",
            "║  Delete Mode:                                                ║",
            "║    Space      - Mark/unmark items                            ║",
            "║    d          - Delete marked items                          ║",
            "║                                                              ║",
            "║  Package Mode:                                               ║",
            "║    Space      - Mark/unmark packages                         ║",
            "║    u          - Uninstall marked packages                    ║",
            "║                                                              ║",
            "║  Press 'h' or '?' to close this help                         ║",
            "╚════════════════════════════════════════════════════════════╝",
        ]
        
        box_height = len(help_lines)
        box_width = len(help_lines[0])
        
        # Center the box
        start_y = max(0, (height - box_height) // 2)
        start_x = max(0, (width - box_width) // 2)
        
        # Draw semi-transparent background
        for y in range(start_y, min(start_y + box_height, height)):
            for x in range(start_x, min(start_x + box_width, width)):
                try:
                    stdscr.addch(y, x, ' ', curses.color_pair(1))
                except curses.error:
                    pass
        
        # Draw help text
        for i, line in enumerate(help_lines):
            y = start_y + i
            if y >= height:
                break
            try:
                stdscr.addstr(y, start_x, line[:width - start_x], curses.color_pair(4) | curses.A_BOLD)
            except curses.error:
                pass
    
    def _handle_enter(self):
        """Handle Enter key press."""
        if self.current_view == 'mode_select':
            # Select mode
            modes = ['list', 'delete', 'explore', 'package', 'quit']
            if self.cursor < len(modes):
                selected = modes[self.cursor]
                if selected == 'quit':
                    sys.exit(0)
                self.mode = selected
                self.current_view = 'category_select'
                self.breadcrumb = []
                self.cursor = 0
                self.scroll_offset = 0
                self.selected_items.clear()
        
        elif self.current_view == 'category_select':
            # Select category
            if self.cursor == 0:
                self.current_view = 'interpreters'
                self.breadcrumb.append('Interpreters')
                self.cursor = 0
                self.scroll_offset = 0
            elif self.cursor == 1:
                self.current_view = 'venvs'
                self.breadcrumb.append('Virtual Environments')
                self.cursor = 0
                self.scroll_offset = 0
            elif self.cursor == 2 and self.mode == 'explore':
                self.current_view = 'analysis'
                self.breadcrumb.append('Analysis')
                self.cursor = 0
                self.scroll_offset = 0
        
        elif self.current_view == 'venvs' and self.mode in ['list', 'explore', 'package']:
            # Drill down into venv
            if self.cursor < len(self.venvs):
                self.selected_venv = self.venvs[self.cursor]
                self.current_view = 'venv_detail'
                self.breadcrumb.append(self.selected_venv.project_name)
                self.cursor = 0
                self.scroll_offset = 0
                self.selected_items.clear()
    
    def _toggle_selection(self):
        """Toggle selection of current item."""
        if self.current_view in ['interpreters', 'venvs', 'venv_detail']:
            if self.cursor in self.selected_items:
                self.selected_items.remove(self.cursor)
            else:
                self.selected_items.add(self.cursor)
    
    def _confirm_delete(self, stdscr):
        """Confirm and execute deletion."""
        if not self.selected_items:
            return
        
        height, width = stdscr.getmaxyx()
        
        # Calculate total size
        total_size = 0
        if self.current_view == 'venvs':
            total_size = sum(self.venvs[i].size_bytes for i in self.selected_items if i < len(self.venvs))
        
        # Confirmation dialog
        msg = f"Delete {len(self.selected_items)} items ({format_bytes(total_size)})? [y/N]: "
        try:
            stdscr.addstr(height - 1, 2, msg, curses.color_pair(2) | curses.A_BOLD)
        except curses.error:
            pass
        stdscr.refresh()
        
        curses.echo()
        try:
            response = stdscr.getstr(height - 1, len(msg) + 2, 3).decode('utf-8')
        except:
            response = "n"
        finally:
            curses.noecho()
        
        if response.lower() in ['y', 'yes']:
            # Delete marked items with progress
            total = len(self.selected_items)
            deleted = 0
            
            for idx in sorted(self.selected_items, reverse=True):
                if self.current_view == 'venvs' and idx < len(self.venvs):
                    venv = self.venvs[idx]
                    if not is_system_path(venv.path):
                        # Show progress
                        progress_msg = f"Deleting {deleted + 1}/{total}: {venv.project_name[:40]}..."
                        try:
                            stdscr.addstr(height - 1, 2, " " * (width - 4))
                            stdscr.addstr(height - 1, 2, progress_msg[:width-4], curses.color_pair(5))
                        except curses.error:
                            pass
                        stdscr.refresh()
                        
                        try:
                            shutil.rmtree(venv.path)
                            self.venvs.pop(idx)
                            deleted += 1
                        except Exception as e:
                            # Show error briefly
                            try:
                                stdscr.addstr(height - 1, 2, f"Error deleting: {str(e)[:width-20]}", curses.color_pair(2))
                            except curses.error:
                                pass
                            stdscr.refresh()
                            time.sleep(1)
            
            # Show completion message
            try:
                stdscr.addstr(height - 1, 2, f"Deleted {deleted}/{total} items. Press any key...", curses.color_pair(3))
            except curses.error:
                pass
            stdscr.refresh()
            stdscr.getch()
            
            self.selected_items.clear()
            self.cursor = min(self.cursor, max(0, len(self.venvs) - 1))
    
    def _confirm_uninstall(self, stdscr):
        """Confirm and execute package uninstall."""
        if not self.selected_items or not self.selected_venv:
            return
        
        height, width = stdscr.getmaxyx()
        
        msg = f"Uninstall {len(self.selected_items)} packages? [y/N]: "
        try:
            stdscr.addstr(height - 1, 2, msg, curses.color_pair(2) | curses.A_BOLD)
        except curses.error:
            pass
        stdscr.refresh()
        
        curses.echo()
        try:
            response = stdscr.getstr(height - 1, len(msg) + 2, 3).decode('utf-8')
        except:
            response = "n"
        finally:
            curses.noecho()
        
        if response.lower() in ['y', 'yes']:
            # Uninstall marked packages with progress
            total = len(self.selected_items)
            uninstalled = 0
            
            for idx in sorted(self.selected_items):
                if idx < len(self.selected_venv.packages):
                    pkg = self.selected_venv.packages[idx]
                    
                    # Show progress
                    progress_msg = f"Uninstalling {uninstalled + 1}/{total}: {pkg.name}..."
                    try:
                        stdscr.addstr(height - 1, 2, " " * (width - 4))
                        stdscr.addstr(height - 1, 2, progress_msg[:width-4], curses.color_pair(5))
                    except curses.error:
                        pass
                    stdscr.refresh()
                    
                    try:
                        self.selected_venv.uninstall_package(pkg.name)
                        uninstalled += 1
                    except Exception as e:
                        # Show error briefly
                        try:
                            stdscr.addstr(height - 1, 2, f"Error: {str(e)[:width-20]}", curses.color_pair(2))
                        except curses.error:
                            pass
                        stdscr.refresh()
                        time.sleep(1)
            
            # Show completion message
            try:
                stdscr.addstr(height - 1, 2, f"Uninstalled {uninstalled}/{total} packages. Press any key...", curses.color_pair(3))
            except curses.error:
                pass
            stdscr.refresh()
            stdscr.getch()
            
            self.selected_items.clear()
            self.selected_venv.probe_packages(force=True)
            self.cursor = min(self.cursor, max(0, len(self.selected_venv.packages) - 1))
    
    def _go_back(self):
        """Go back to previous view."""
        if self.current_view == 'venv_detail':
            self.current_view = 'venvs'
            self.selected_venv = None
            self.cursor = 0
            self.scroll_offset = 0
            self.selected_items.clear()
            if self.breadcrumb:
                self.breadcrumb.pop()
        elif self.current_view in ['interpreters', 'venvs', 'analysis']:
            self.current_view = 'category_select'
            self.cursor = 0
            self.scroll_offset = 0
            self.selected_items.clear()
            self.breadcrumb.clear()
        elif self.current_view == 'category_select':
            self.current_view = 'mode_select'
            self.mode = None
            self.cursor = 0
            self.scroll_offset = 0
            self.breadcrumb.clear()
        else:
            self.current_view = 'mode_select'
            self.mode = None
            self.cursor = 0
            self.breadcrumb.clear()

# ============================================================================
# CLI Commands
# ============================================================================

def cmd_scan(args):
    """Scan for all Python resources."""
    print("Scanning for Python interpreters...")
    interpreters = find_python_interpreters(use_mdfind=args.mdfind)
    
    print("Scanning for virtual environments...")
    venvs = find_venvs(scan_path=args.path, use_mdfind=args.mdfind)
    
    if not args.no_packages:
        print(f"Probing packages in {len(venvs)} environments...")
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
    venvs = find_venvs(scan_path=args.path, use_mdfind=args.mdfind)
    
    print(f"\nFound {len(venvs)} virtual environments:\n")
    print(f"{'Manager':<10} {'Size':<10} {'Age':<8} {'Project':<30} {'Path'}")
    print("-" * 100)
    
    for venv in sorted(venvs, key=lambda x: x.size_bytes, reverse=True):
        manager = f"[{venv.manager}]"
        size = format_bytes(venv.size_bytes)
        age = format_datetime(venv.last_modified)
        project = venv.project_name[:30]
        path = shorten_path(venv.path, 50)
        print(f"{manager:<10} {size:<10} {age:<8} {project:<30} {path}")
    
    total_size = sum(v.size_bytes for v in venvs)
    print(f"\nTotal size: {format_bytes(total_size)}")

def cmd_packages(args):
    """List or analyze packages."""
    if args.venv:
        venv_path = os.path.abspath(args.venv)
        if not is_venv(venv_path):
            print(f"Error: {venv_path} is not a virtual environment")
            return 1
        
        venv = VirtualEnv(venv_path)
        venv.probe_packages()
        
        print(f"\nPackages in {venv.project_name}:\n")
        print(f"{'Package':<30} {'Version':<15}")
        print("-" * 50)
        
        for pkg in sorted(venv.packages, key=lambda p: p.name):
            print(f"{pkg.name:<30} {pkg.version:<15}")
        
        print(f"\nTotal: {len(venv.packages)} packages")
    else:
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

def cmd_uninstall(args):
    """Uninstall a package from a venv."""
    venv_path = os.path.abspath(args.from_venv)
    if not is_venv(venv_path):
        print(f"Error: {venv_path} is not a virtual environment")
        return 1
    
    venv = VirtualEnv(venv_path)
    
    if args.dry_run:
        print(f"[DRY RUN] Would uninstall {args.package} from {venv.project_name}")
        return 0
    
    print(f"Uninstalling {args.package} from {venv.project_name}...")
    success = venv.uninstall_package(args.package, dry_run=args.dry_run)
    
    if success:
        print(f"✓ Successfully uninstalled {args.package}")
        return 0
    else:
        print(f"✗ Failed to uninstall {args.package}")
        return 1

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

def cmd_search(args):
    """Search for venvs or packages."""
    print(f"Searching for '{args.pattern}'...")
    
    venvs = find_venvs(use_mdfind=args.mdfind)
    matching_venvs = [v for v in venvs if args.pattern.lower() in v.project_name.lower() or args.pattern.lower() in v.path.lower()]
    
    if matching_venvs:
        print(f"\nFound {len(matching_venvs)} matching virtual environments:\n")
        for venv in matching_venvs:
            print(f"  [{venv.manager}] {venv.project_name} ({format_bytes(venv.size_bytes)})")
            print(f"    {venv.path}")
    
    analyzer = PackageAnalyzer(venvs)
    matching_pkgs = analyzer.find_package(args.pattern)
    
    if matching_pkgs:
        print(f"\nFound package '{args.pattern}' in {len(matching_pkgs)} environments:\n")
        for pkg, venv in matching_pkgs[:20]:
            print(f"  {pkg.name} {pkg.version} in {venv.project_name}")

def cmd_interactive(args):
    """Launch interactive TUI."""
    print("Scanning for Python resources...")
    interpreters = find_python_interpreters(use_mdfind=args.mdfind)
    venvs = find_venvs(scan_path=getattr(args, 'path', None), use_mdfind=args.mdfind)
    
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
        description='Comprehensive Python environment and package cleaner'
    )
    parser.add_argument('--mdfind', action='store_true', help='Use mdfind on macOS for faster scanning')
    
    subparsers = parser.add_subparsers(dest='command')
    
    scan_parser = subparsers.add_parser('scan', help='Scan for all Python resources')
    scan_parser.add_argument('--json', help='Save results to JSON file')
    scan_parser.add_argument('--path', help='Scan specific path')
    scan_parser.add_argument('--no-packages', action='store_true', help='Skip package probing')
    scan_parser.add_argument('--parallel', type=int, default=4, help='Parallel workers')
    
    interp_parser = subparsers.add_parser('interpreters', help='List all Python interpreters')
    
    venv_parser = subparsers.add_parser('venvs', help='List all virtual environments')
    venv_parser.add_argument('--path', help='Scan specific path for venvs')
    
    pkg_parser = subparsers.add_parser('packages', help='List or analyze packages')
    pkg_parser.add_argument('--venv', help='List packages in specific venv')
    
    uninst_parser = subparsers.add_parser('uninstall', help='Uninstall package from venv')
    uninst_parser.add_argument('package', help='Package name to uninstall')
    uninst_parser.add_argument('--from', dest='from_venv', required=True, help='Venv path')
    uninst_parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    
    clean_parser = subparsers.add_parser('clean', help='Delete environments or interpreters')
    clean_parser.add_argument('--target', help='Path to delete')
    clean_parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    clean_parser.add_argument('--yes', action='store_true', help='Skip confirmation')
    
    search_parser = subparsers.add_parser('search', help='Search for venvs or packages')
    search_parser.add_argument('pattern', help='Search pattern')
    
    interactive_parser = subparsers.add_parser('interactive', help='Launch interactive TUI')
    interactive_parser.add_argument('--path', help='Scan specific path for venvs')
    
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
    elif args.command == 'uninstall':
        return cmd_uninstall(args)
    elif args.command == 'clean':
        return cmd_clean(args)
    elif args.command == 'search':
        return cmd_search(args)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
