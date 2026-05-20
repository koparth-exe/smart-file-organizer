#!/usr/bin/env python3
"""
Smart File Organizer
Author: Parth Korgaonkar
GitHub: koparth-exe
"""

import os
import sys
import json
import shutil
import hashlib
import logging
import argparse
import time
from pathlib import Path

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.rule import Rule
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ── Pyfiglet ──────────────────────────────────────────────────────────────────
try:
    import pyfiglet
    PYFIGLET_AVAILABLE = True
except ImportError:
    PYFIGLET_AVAILABLE = False

# ── Watchdog ──────────────────────────────────────────────────────────────────
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False
    class FileSystemEventHandler:
        pass
    Observer = None

# ── Global console ────────────────────────────────────────────────────────────
console = Console() if RICH_AVAILABLE else None

VERSION = "1.0.0"
AUTHOR  = "Parth Korgaonkar"
GITHUB  = "github.com/koparth-exe"

# ── Default config ────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "categories": {
        "Images":      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
        "Videos":      [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "Audio":       [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
        "Documents":   [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".txt", ".rtf"],
        "Code":        [".py", ".js", ".ts", ".html", ".css", ".c", ".cpp", ".h", ".java", ".go", ".rs", ".sh", ".json", ".xml", ".yaml", ".yml", ".md"],
        "Archives":    [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz"],
        "Data":        [".csv", ".tsv", ".sql", ".db", ".sqlite"],
        "Executables": [".exe", ".msi", ".apk", ".deb", ".rpm", ".dmg"],
        "Misc":        []
    },
    "ignore":      [".DS_Store", "Thumbs.db", "desktop.ini"],
    "misc_folder": "Misc",
    "log_file":    "organizer.log"
}

SESSION_MARKER = "=== SESSION START ==="


# ── Banner ────────────────────────────────────────────────────────────────────

def print_banner():
    if not RICH_AVAILABLE:
        print("Smart File Organizer")
        print(f"By {AUTHOR} | v{VERSION}")
        return

    if PYFIGLET_AVAILABLE:
        art = pyfiglet.figlet_format("SFOrganizer", font="small")
    else:
        art = (
            " ____  _____  ___\n"
            "/ ___||  ___|/ _ \\\n"
            "\\___ \\| |_  | | | |\n"
            " ___) |  _| | |_| |\n"
            "|____/|_|    \\___/\n"
        )

    content = Text()
    content.append(art, style="bold green")
    content.append(f"\n  Smart File Organizer  ", style="bold white")
    content.append(f"v{VERSION}\n", style="dim")
    content.append(f"  By {AUTHOR}  ", style="bold cyan")
    content.append(f"| {GITHUB}", style="dim cyan")

    console.print(Panel(
        content,
        box=box.DOUBLE_EDGE,
        border_style="green",
        padding=(0, 2)
    ))
    console.print()


def print_commands():
    if not RICH_AVAILABLE:
        return

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
    t.add_column("Command",     style="cyan",  no_wrap=True)
    t.add_column("Description", style="white")
    t.add_column("Example",     style="dim")

    t.add_row("(no flag)",      "Sort folder once",               "python organizer.py ~/Downloads")
    t.add_row("--watch / -w",   "Watch & auto-sort in real-time", "python organizer.py ~/Downloads --watch")
    t.add_row("--undo",         "Reverse last sort session",      "python organizer.py ~/Downloads --undo")
    t.add_row("--stats",        "Show file count per category",   "python organizer.py ~/Downloads --stats")
    t.add_row("--duplicates",   "Find files with same content",   "python organizer.py ~/Downloads --duplicates")
    t.add_row("--generate-config", "Create default config.json",  "python organizer.py --generate-config")
    t.add_row("--config / -c",  "Use custom config file",         "python organizer.py ~/Downloads -c my.json")

    console.print(Panel(t, title="[bold green]Available Commands[/bold green]",
                        border_style="green", box=box.ROUNDED))
    console.print()


# ── Logging (file only) ───────────────────────────────────────────────────────

def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("FileOrganizer")
    if logger.handlers:
        logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def write_session_marker(log_path: Path) -> None:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{SESSION_MARKER}\n")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(user_config)
        return merged
    return DEFAULT_CONFIG.copy()


# ── Core ──────────────────────────────────────────────────────────────────────

def get_category(file_path: Path, config: dict) -> str:
    ext = file_path.suffix.lower()
    for category, extensions in config["categories"].items():
        if ext in extensions:
            return category
    return config.get("misc_folder", "Misc")


def move_file(file_path: Path, target_root: Path, config: dict, logger: logging.Logger) -> bool:
    filename = file_path.name
    if filename in config.get("ignore", []):
        return False
    if file_path.is_dir():
        return False
    if filename == config.get("log_file", "organizer.log"):
        return False

    category = get_category(file_path, config)
    dest_dir = target_root / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    if dest_path.exists():
        stem, suffix = file_path.stem, file_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(file_path), str(dest_path))

    # File log (for undo)
    logger.info(f"Moved: {filename}  ->  {category}/{dest_path.name}")

    # Console output
    if RICH_AVAILABLE:
        console.print(f"  [green]>[/green] [white]{filename}[/white]  [dim]->[/dim]  [cyan]{category}/{dest_path.name}[/cyan]")
    else:
        print(f"  > {filename}  ->  {category}/{dest_path.name}")

    return True


# ── Sort ──────────────────────────────────────────────────────────────────────

def sort_folder(target: Path, config: dict, logger: logging.Logger) -> dict:
    files = [f for f in target.iterdir() if f.is_file()]
    if not files:
        if RICH_AVAILABLE:
            console.print("[yellow]  No files to organize.[/yellow]")
        else:
            print("  No files to organize.")
        return {}

    if RICH_AVAILABLE:
        console.print(Rule("[green]Sorting[/green]", style="green"))
        console.print()

    moved, skipped, stats = 0, 0, {}
    for f in files:
        cat = get_category(f, config)
        result = move_file(f, target, config, logger)
        if result:
            moved += 1
            stats[cat] = stats.get(cat, 0) + 1
        else:
            skipped += 1

    # Summary
    if RICH_AVAILABLE:
        console.print()
        console.print(Rule("[green]Done[/green]", style="green"))
        console.print()

        t = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
        t.add_column("Category", style="cyan")
        t.add_column("Files",    style="white", justify="right")

        for cat, count in sorted(stats.items()):
            t.add_row(cat, str(count))

        t.add_section()
        t.add_row("[bold]Total moved[/bold]", f"[bold green]{moved}[/bold green]")
        t.add_row("[dim]Skipped[/dim]",       f"[dim]{skipped}[/dim]")

        console.print(Panel(t, title="[bold green]Sort Summary[/bold green]",
                            border_style="green", box=box.ROUNDED))
    else:
        print(f"\nDone — {moved} moved, {skipped} skipped.")

    logger.info(f"Done — {moved} file(s) moved, {skipped} skipped.")
    if stats:
        logger.info("Stats: " + ", ".join(f"{k}: {v}" for k, v in sorted(stats.items())))

    return stats


# ── Stats ─────────────────────────────────────────────────────────────────────

def show_stats(target: Path) -> None:
    rows, total = [], 0

    for item in sorted(target.iterdir()):
        if item.is_dir():
            count = len([f for f in item.iterdir() if f.is_file()])
            if count > 0:
                rows.append((item.name, count))
                total += count

    if RICH_AVAILABLE:
        if not rows:
            console.print(Panel("[yellow]No organized subfolders found.[/yellow]",
                                title="Stats", border_style="yellow"))
            return

        max_count = max(r[1] for r in rows)
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
        t.add_column("Category", style="cyan")
        t.add_column("Bar",      style="green", no_wrap=True)
        t.add_column("Files",    style="white", justify="right")

        for name, count in rows:
            bar = "█" * int((count / max_count) * 25)
            t.add_row(name, bar, str(count))

        t.add_section()
        t.add_row("[bold]Total[/bold]", "", f"[bold green]{total}[/bold green]")

        console.print(Panel(t,
            title=f"[bold green]Stats — {target}[/bold green]",
            border_style="green", box=box.ROUNDED))
    else:
        print(f"\nStats for: {target}\n")
        for name, count in rows:
            print(f"  {name:<15} {count}")
        print(f"\n  Total: {total}")


# ── Undo ──────────────────────────────────────────────────────────────────────

def undo_last_session(target: Path, config: dict) -> None:
    log_path = target / config.get("log_file", "organizer.log")
    if not log_path.exists():
        if RICH_AVAILABLE:
            console.print(Panel("[red]No log file found. Nothing to undo.[/red]",
                                border_style="red"))
        else:
            print("[ERROR] No log file found.")
        sys.exit(1)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    last_marker_idx = -1
    for i, line in enumerate(lines):
        if SESSION_MARKER in line:
            last_marker_idx = i

    if last_marker_idx == -1:
        if RICH_AVAILABLE:
            console.print(Panel("[red]No session found. Run the organizer at least once first.[/red]",
                                border_style="red"))
        sys.exit(1)

    moves = []
    for line in lines[last_marker_idx + 1:]:
        if "INFO" in line and "Moved:" in line and "->" in line:
            try:
                part = line.split("Moved:")[1].strip()
                original_name, dest_rel = [x.strip() for x in part.split("->")]
                moves.append((original_name, dest_rel))
            except Exception:
                continue

    if not moves:
        if RICH_AVAILABLE:
            console.print("[yellow]Nothing to undo in the last session.[/yellow]")
        return

    if RICH_AVAILABLE:
        console.print(Rule("[cyan]Undoing[/cyan]", style="cyan"))
        console.print()

    restored, failed = 0, 0
    for original_name, dest_rel in reversed(moves):
        src = target / dest_rel
        dst = target / original_name

        if not src.exists():
            if RICH_AVAILABLE:
                console.print(f"  [yellow]SKIP[/yellow] Not found: {dest_rel}")
            failed += 1
            continue

        if dst.exists():
            stem, suffix = Path(original_name).stem, Path(original_name).suffix
            counter = 1
            while dst.exists():
                dst = target / f"{stem}_restored_{counter}{suffix}"
                counter += 1

        shutil.move(str(src), str(dst))
        if RICH_AVAILABLE:
            console.print(f"  [cyan]<[/cyan] [white]{dest_rel}[/white]  [dim]->[/dim]  [green]{dst.name}[/green]")
        restored += 1

    for item in target.iterdir():
        if item.is_dir():
            try:
                item.rmdir()
            except OSError:
                pass

    new_lines = lines[:last_marker_idx]
    log_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(
            f"[green]Restored:[/green] {restored} file(s)\n[yellow]Skipped:[/yellow]  {failed} file(s)",
            title="[bold cyan]Undo Complete[/bold cyan]",
            border_style="cyan", box=box.ROUNDED
        ))


# ── Duplicates ────────────────────────────────────────────────────────────────

def hash_file(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(target: Path) -> None:
    if RICH_AVAILABLE:
        console.print(Rule("[yellow]Scanning for Duplicates[/yellow]", style="yellow"))
        console.print()

    hash_map = {}
    scanned = 0

    for file in target.rglob("*"):
        if file.is_file() and file.name != "organizer.log":
            try:
                h = hash_file(file)
                hash_map.setdefault(h, []).append(file)
                scanned += 1
            except (PermissionError, OSError):
                continue

    duplicates = {h: p for h, p in hash_map.items() if len(p) > 1}

    if not duplicates:
        if RICH_AVAILABLE:
            console.print(Panel(
                f"[green]No duplicates found.[/green]\n[dim]{scanned} files scanned.[/dim]",
                border_style="green", box=box.ROUNDED
            ))
        else:
            print(f"No duplicates found. ({scanned} scanned)")
        return

    total_dupes = sum(len(p) - 1 for p in duplicates.values())

    if RICH_AVAILABLE:
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold yellow")
        t.add_column("Status", style="bold",  no_wrap=True)
        t.add_column("File",   style="white")
        t.add_column("Size",   style="dim", justify="right")

        for i, (h, paths) in enumerate(duplicates.items(), 1):
            t.add_section()
            for j, p in enumerate(paths):
                rel   = p.relative_to(target)
                size  = f"{p.stat().st_size/1024:.1f} KB"
                label = "[green]KEEP[/green]" if j == 0 else "[red]DUPE[/red]"
                t.add_row(label, str(rel), size)

        console.print(Panel(t,
            title=f"[bold yellow]Duplicates — {len(duplicates)} group(s), {total_dupes} redundant file(s)[/bold yellow]",
            border_style="yellow", box=box.ROUNDED
        ))
        console.print("[dim]  Tip: Delete [red]DUPE[/red] files manually to free space.[/dim]")
    else:
        print(f"Found {len(duplicates)} group(s), {total_dupes} redundant files.")


# ── Watch ─────────────────────────────────────────────────────────────────────

class FolderEventHandler(FileSystemEventHandler):
    def __init__(self, target, config, logger):
        super().__init__()
        self.target = target
        self.config = config
        self.logger = logger

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        time.sleep(0.5)
        if file_path.exists():
            move_file(file_path, self.target, self.config, self.logger)


def watch_folder(target: Path, config: dict, logger: logging.Logger) -> None:
    if not WATCHDOG_AVAILABLE:
        if RICH_AVAILABLE:
            console.print(Panel("[red]watchdog not installed. Run: pip install watchdog[/red]",
                                border_style="red"))
        sys.exit(1)

    if RICH_AVAILABLE:
        console.print(Panel(
            f"[green]Watching:[/green] {target}\n[dim]Press Ctrl+C to stop.[/dim]",
            title="[bold green]Watch Mode[/bold green]",
            border_style="green", box=box.ROUNDED
        ))

    handler  = FolderEventHandler(target, config, logger)
    observer = Observer()
    observer.schedule(handler, str(target), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if RICH_AVAILABLE:
            console.print("\n[yellow]Watch mode stopped.[/yellow]")
        observer.stop()
    observer.join()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Smart File Organizer by Parth Korgaonkar — Sort, undo, find duplicates, view stats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python organizer.py ~/Downloads
  python organizer.py ~/Downloads --watch
  python organizer.py ~/Downloads --undo
  python organizer.py ~/Downloads --stats
  python organizer.py ~/Downloads --duplicates
  python organizer.py --generate-config
        """
    )
    parser.add_argument("folder",             nargs="?", default=".",
                        help="Target folder (default: current directory)")
    parser.add_argument("--watch",   "-w",    action="store_true",
                        help="Watch and auto-sort new files in real-time")
    parser.add_argument("--undo",             action="store_true",
                        help="Reverse the last sort session")
    parser.add_argument("--stats",            action="store_true",
                        help="Show file count per category")
    parser.add_argument("--duplicates",       action="store_true",
                        help="Find files with identical content")
    parser.add_argument("--config",  "-c",    default="config.json",
                        help="Path to config JSON (default: config.json)")
    parser.add_argument("--generate-config",  action="store_true",
                        help="Generate default config.json and exit")
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.generate_config:
        out = Path("config.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"config.json written to {out.resolve()}")
        sys.exit(0)

    # Validate target
    target = Path(args.folder).resolve()
    if not target.exists():
        if RICH_AVAILABLE:
            console.print(f"[red][ERROR] Folder not found: {target}[/red]")
        else:
            print(f"[ERROR] Folder not found: {target}")
        sys.exit(1)
    if not target.is_dir():
        if RICH_AVAILABLE:
            console.print(f"[red][ERROR] Not a directory: {target}[/red]")
        else:
            print(f"[ERROR] Not a directory: {target}")
        sys.exit(1)

    # Safeguard
    script_dir = Path(__file__).resolve().parent
    if target == script_dir:
        if RICH_AVAILABLE:
            console.print(Panel(
                "[red]You are trying to organize the folder that contains organizer.py itself.[/red]\n"
                "[dim]Run it on a different folder:\n  python organizer.py ~/Downloads[/dim]",
                title="[bold red]Error[/bold red]", border_style="red", box=box.ROUNDED
            ))
        else:
            print("[ERROR] Cannot sort the script's own directory.")
        sys.exit(1)

    # Print banner for all modes
    print_banner()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)

    if args.stats:
        show_stats(target)
        return

    if args.duplicates:
        find_duplicates(target)
        return

    if args.undo:
        undo_last_session(target, config)
        return

    # Sort / Watch
    log_path = target / config.get("log_file", "organizer.log")
    write_session_marker(log_path)
    logger = setup_logger(log_path)

    if RICH_AVAILABLE:
        console.print(f"  [dim]Target:[/dim] [white]{target}[/white]")
        console.print(f"  [dim]Config:[/dim] [white]{config_path if config_path.exists() else 'defaults'}[/white]")
        console.print()

    if args.watch:
        sort_folder(target, config, logger)
        watch_folder(target, config, logger)
    else:
        sort_folder(target, config, logger)

    # Show commands hint at end
    if RICH_AVAILABLE:
        console.print()
        print_commands()


if __name__ == "__main__":
    main()
