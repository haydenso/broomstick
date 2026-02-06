#!/usr/bin/env python3
"""
pyenvhunter.py - Lightweight Python environment scanner & safe cleaner (prototype)

Usage:
  python pyenvhunter.py scan [--paths PATH ...] [--mdfind] [--json OUTFILE] [--parallel N]

This is a small stdlib-only prototype. It discovers virtual-environment-like
directories by looking for common markers (pyvenv.cfg, bin/activate, Scripts/activate)
and known manager locations. It can probe package lists by invoking the env's
python with `-m pip list --format=json` (when available).

Design goals in this file:
- readable, importable functions for testing
- safe operations: `clean` defaults to dry-run and requires --yes to actually delete
- JSON output for automation

Limitations: this is a prototype. It intentionally avoids aggressive filesystem
scans (no recursive scan of /) and doesn't rely on external packages.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

# Known places to probe by default. Keep this conservative to avoid scanning
# the whole filesystem.
DEFAULT_PATHS = [
    os.path.expanduser("~"),
    os.path.expanduser("~/.pyenv/versions"),
    os.path.expanduser("~/.asdf/installs/python"),
    os.path.expanduser("~/.local"),
    os.path.expanduser("~/.local/pipx/venvs"),
    os.path.expanduser("~/.cache/pypoetry/virtualenvs"),
    os.path.expanduser("~/miniconda3/envs"),
    os.path.expanduser("~/anaconda3/envs"),
    "/opt/homebrew",
    "/usr/local",
    "/opt",
    "/Applications",
    "/Users/Shared",
]


# Manager-specific directory names we will probe explicitly. Each entry maps
# a short manager id to a path or list-of-paths (expanded relative to $HOME).
MANAGER_PATHS = {
    "pyenv": [os.path.expanduser("~/.pyenv/versions")],
    "asdf": [os.path.expanduser("~/.asdf/installs/python")],
    "pipx": [os.path.expanduser("~/.local/pipx/venvs")],
    "poetry": [os.path.expanduser("~/.cache/pypoetry/virtualenvs")],
    "conda": [os.path.expanduser("~/miniconda3/envs"), os.path.expanduser("~/anaconda3/envs")],
}


def is_venv_dir(path: str) -> bool:
    """Return True if the path looks like a virtualenv/venv directory."""
    if not os.path.isdir(path):
        return False
    # marker files
    markers = ["pyvenv.cfg", os.path.join("bin", "activate"), os.path.join("Scripts", "activate")]
    for m in markers:
        if os.path.exists(os.path.join(path, m)):
            return True
    return False


def find_envs(paths: List[str]) -> List[str]:
    """Find candidate environment directories under the provided paths.

    This function is conservative: it checks only a few levels deep and known
    manager directories to remain fast and safe on large trees.
    """
    found = set()
    # First, probe manager-specific known locations to be efficient and
    # deterministic. This avoids expensive wide recursion.
    for mgr, mgr_paths in MANAGER_PATHS.items():
        for mp in mgr_paths:
            if not mp:
                continue
            mp = os.path.expanduser(mp)
            if not os.path.exists(mp):
                continue
            try:
                with os.scandir(mp) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            # Some manager dirs contain many nested bits; treat direct
                            # children as candidate env roots.
                            found.add(os.path.abspath(os.path.join(mp, entry.name)))
            except PermissionError:
                pass
    for base in paths:
        if not base:
            continue
        base = os.path.expanduser(base)
        if os.path.isfile(base):
            # if a file was passed, consider its parent
            base = os.path.dirname(base)
        if not os.path.exists(base):
            continue
        # quick check: if base itself is a venv
        if is_venv_dir(base):
            found.add(os.path.abspath(base))
            continue

        # check a few manager-style children quickly
        try:
            with os.scandir(base) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        cand = os.path.join(base, entry.name)
                        # direct venv markers
                        if is_venv_dir(cand):
                            found.add(os.path.abspath(cand))
                            continue
                        # common manager paths (pyenv versions often have many children)
                        # avoid diving recursively everywhere: only one level by default
                        # but allow directory named 'envs' or 'versions' to be scanned one deeper
                        if entry.name.lower() in ("versions", "envs", "venvs", "virtualenvs"):
                            try:
                                with os.scandir(cand) as child_it:
                                    for child in child_it:
                                        child_path = os.path.join(cand, child.name)
                                        if child.is_dir(follow_symlinks=False) and is_venv_dir(child_path):
                                            found.add(os.path.abspath(child_path))
                                        # sometimes manager dirs directly represent env roots
                                        if child.is_dir(follow_symlinks=False) and child.name.endswith(".venv"):
                                            found.add(os.path.abspath(child_path))
                            except PermissionError:
                                pass
                    except PermissionError:
                        continue
        except PermissionError:
            continue
    return sorted(found)


def get_python_executable(env_path: str) -> Optional[str]:
    """Return a plausible python executable path inside an env, or None."""
    candidates = [os.path.join(env_path, "bin", "python"), os.path.join(env_path, "bin", "python3"), os.path.join(env_path, "Scripts", "python.exe")]
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


def probe_packages(python_exec: str, timeout: int = 10) -> Optional[List[Dict[str, str]]]:
    """Run `python -m pip list --format=json` and return parsed list or None on error."""
    try:
        res = subprocess.run([python_exec, "-m", "pip", "list", "--format=json"], capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            return None
        return json.loads(res.stdout)
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
        return None


def du_size_bytes(path: str) -> int:
    """Compute total size of files under path (in bytes)."""
    total = 0
    for root, dirs, files in os.walk(path, topdown=True):
        for f in files:
            try:
                fp = os.path.join(root, f)
                total += os.path.getsize(fp)
            except (OSError, PermissionError):
                continue
    return total


def probe_env(path: str, probe_pkgs: bool = True) -> Dict:
    """Gather metadata about an environment path."""
    info: Dict = {"path": os.path.abspath(path), "id": os.path.abspath(path), "type": "venv", "packages": None}
    info["last_modified"] = None
    try:
        info["last_modified"] = os.path.getmtime(path)
    except OSError:
        info["last_modified"] = None
    info["size_bytes"] = du_size_bytes(path)

    py = get_python_executable(path)
    info["python_executable"] = py
    info["python_version"] = None
    if py:
        try:
            ver = subprocess.run([py, "-c", "import sys, json; print(sys.version)"] , capture_output=True, text=True, timeout=5)
            if ver.returncode == 0:
                info["python_version"] = ver.stdout.strip()
        except subprocess.SubprocessError:
            info["python_version"] = None

    if probe_pkgs and py:
        pkgs = probe_packages(py)
        info["packages"] = pkgs

    return info


def scan(paths: Optional[List[str]] = None, parallel: int = 4, probe_pkgs: bool = True) -> List[Dict]:
    """Discover envs and probe them. Returns list of env info dicts."""
    paths = paths or DEFAULT_PATHS
    env_paths = find_envs(paths)
    results: List[Dict] = []
    if not env_paths:
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(probe_env, p, probe_pkgs): p for p in env_paths}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                # keep going on probe failures
                continue
    return results


def print_envs(envs: List[Dict]):
    for e in envs:
        print(f"- path: {e.get('path')}")
        print(f"  type: {e.get('type')} size: {e.get('size_bytes')} bytes")
        if e.get("python_version"):
            print(f"  python: {e.get('python_version')}")
        pk = e.get("packages")
        if isinstance(pk, list):
            print(f"  packages: {len(pk)} installed")
        else:
            print(f"  packages: unknown")


def confirm(prompt: str) -> bool:
    try:
        ans = input(prompt + " [y/N]: ")
    except EOFError:
        return False
    return ans.strip().lower() in ("y", "yes")


def remove_path(path: str, dry_run: bool = True) -> bool:
    """Remove a path. Returns True if removed or would be removed in dry-run."""
    if dry_run:
        print(f"[dry-run] would remove: {path}")
        return True
    try:
        # be conservative: only remove directories
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"removed: {path}")
            return True
        else:
            print(f"skipping non-dir: {path}")
            return False
    except Exception as e:
        print(f"failed to remove {path}: {e}")
        return False


def cmd_scan(args: argparse.Namespace):
    paths = args.paths or DEFAULT_PATHS
    if args.paths:
        # allow comma-separated single arg convenience
        expanded = []
        for p in args.paths:
            expanded.extend([x for x in p.split(",") if x])
        paths = expanded
    envs = scan(paths=paths, parallel=args.parallel or 4, probe_pkgs=not args.no_packages)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(envs, f, indent=2, ensure_ascii=False)
        print(f"wrote {len(envs)} env(s) to {args.json}")
    else:
        print_envs(envs)


def cmd_list(args: argparse.Namespace):
    # run scan on demand
    envs = scan(paths=args.paths or DEFAULT_PATHS, parallel=args.parallel or 4, probe_pkgs=False)
    if args.json:
        print(json.dumps(envs, indent=2))
    else:
        print_envs(envs)


def cmd_packages(args: argparse.Namespace):
    env = args.env
    if not env:
        print("--env is required")
        return
    info = probe_env(env, probe_pkgs=True)
    pk = info.get("packages")
    if args.json:
        print(json.dumps(pk, indent=2))
        return
    if not pk:
        print("no packages discovered or pip unavailable")
        return
    for p in pk:
        print(f"{p.get('name')}=={p.get('version')}")


def cmd_clean(args: argparse.Namespace):
    target = args.target
    if not target:
        print("please specify --target PATH to remove (or run scan/list to find candidates)")
        return
    if not os.path.exists(target):
        print(f"target does not exist: {target}")
        return
    # safety check: avoid obvious system paths
    sys_paths = ["/usr", "/usr/bin", "/System", "/bin"]
    abs_target = os.path.abspath(target)
    for sp in sys_paths:
        if abs_target == sp or abs_target.startswith(sp + os.sep):
            print(f"refusing to delete system path: {abs_target}")
            return

    if args.dry_run:
        print("dry-run mode: no changes will be made")
    proceed = args.yes or confirm(f"Delete {abs_target}? This is irreversible.")
    if not proceed:
        print("aborted")
        return
    removed = remove_path(abs_target, dry_run=args.dry_run)
    if removed:
        print("done")


def cmd_status(args: argparse.Namespace):
    envs = scan(paths=args.paths or DEFAULT_PATHS, parallel=4, probe_pkgs=False)
    print(f"found {len(envs)} environment(s)")
    if envs:
        largest = sorted(envs, key=lambda e: e.get("size_bytes", 0), reverse=True)[:5]
        print("largest:")
        for e in largest:
            print(f" - {e.get('path')} ({e.get('size_bytes')} bytes)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pyenvhunter", description="Discover Python envs and safely clean them (prototype)")
    p.add_argument("--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    s_scan = sub.add_parser("scan")
    s_scan.add_argument("--paths", nargs="*", help="paths to search (comma ok)")
    s_scan.add_argument("--mdfind", action="store_true", help="(not implemented) use mdfind on macOS")
    s_scan.add_argument("--parallel", type=int, default=4)
    s_scan.add_argument("--json", help="write JSON to file")
    s_scan.add_argument("--no-packages", dest="no_packages", action="store_true", help="skip probing packages")
    s_scan.set_defaults(func=cmd_scan)

    s_list = sub.add_parser("list")
    s_list.add_argument("--paths", nargs="*", help="paths to search")
    s_list.add_argument("--parallel", type=int, default=2)
    s_list.add_argument("--json", action="store_true")
    s_list.set_defaults(func=cmd_list)

    s_pk = sub.add_parser("packages")
    s_pk.add_argument("--env", required=True, help="path to environment")
    s_pk.add_argument("--json", action="store_true")
    s_pk.set_defaults(func=cmd_packages)

    s_clean = sub.add_parser("clean")
    s_clean.add_argument("--target", required=True, help="path to remove")
    s_clean.add_argument("--dry-run", action="store_true", default=True, help="don't actually delete (default)")
    s_clean.add_argument("--yes", action="store_true", help="skip confirmation")
    s_clean.set_defaults(func=cmd_clean)

    s_stat = sub.add_parser("status")
    s_stat.add_argument("--paths", nargs="*", help="paths to search")
    s_stat.set_defaults(func=cmd_status)

    return p


def main(argv: Optional[List[str]] = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
