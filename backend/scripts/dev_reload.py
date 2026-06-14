#!/usr/bin/env python3
"""Restart a development subprocess when source files change."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_EXTENSIONS = {".ini", ".py", ".toml", ".yaml", ".yml"}
DEFAULT_WATCH_PATHS = ["app", "migrations", "main.py"]
IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "logs",
    "node_modules",
    "venv",
}

current_process: subprocess.Popen[str] | None = None
shutdown_requested = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restart a development subprocess when watched files change."
    )
    parser.add_argument(
        "--watch",
        action="append",
        default=[],
        help="Path to watch. Can be used multiple times.",
    )
    parser.add_argument(
        "--extension",
        action="append",
        default=[],
        help="File extension to watch. Defaults to Python and config files.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("DEV_RELOAD_INTERVAL", "1.0")),
        help="Polling interval in seconds.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command must be provided after --")
    return args


def iter_watch_files(watch_paths: list[Path], extensions: set[str]):
    for watch_path in watch_paths:
        if not watch_path.exists():
            continue

        candidates = [watch_path] if watch_path.is_file() else watch_path.rglob("*")
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if any(part in IGNORED_DIR_NAMES for part in candidate.parts):
                continue
            if candidate.suffix not in extensions:
                continue
            yield candidate


def build_snapshot(watch_paths: list[Path], extensions: set[str]) -> dict[Path, int]:
    snapshot: dict[Path, int] = {}
    for path in iter_watch_files(watch_paths, extensions):
        try:
            snapshot[path] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
    return snapshot


def start_process(command: list[str]) -> subprocess.Popen[str]:
    print(f"[dev-reload] Starting: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, text=True)


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def request_shutdown(signum: int, _frame) -> None:
    global shutdown_requested

    shutdown_requested = True
    print(f"[dev-reload] Received signal {signum}; stopping.", flush=True)
    stop_process(current_process)


def normalize_extensions(raw_extensions: list[str]) -> set[str]:
    if not raw_extensions:
        return DEFAULT_EXTENSIONS
    return {
        extension if extension.startswith(".") else f".{extension}"
        for extension in raw_extensions
    }


def run() -> int:
    global current_process

    args = parse_args()
    watch_paths = [Path(path) for path in (args.watch or DEFAULT_WATCH_PATHS)]
    extensions = normalize_extensions(args.extension)

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    previous_snapshot = build_snapshot(watch_paths, extensions)
    current_process = start_process(args.command)

    while not shutdown_requested:
        time.sleep(args.interval)

        exit_code = current_process.poll()
        latest_snapshot = build_snapshot(watch_paths, extensions)
        changed = latest_snapshot != previous_snapshot

        if exit_code is None and not changed:
            continue

        if changed:
            print("[dev-reload] Source change detected; restarting.", flush=True)
            previous_snapshot = latest_snapshot
        elif exit_code is not None:
            print(
                f"[dev-reload] Process exited with code {exit_code}; restarting.",
                flush=True,
            )

        stop_process(current_process)
        if not shutdown_requested:
            current_process = start_process(args.command)

    return 0


if __name__ == "__main__":
    sys.exit(run())
