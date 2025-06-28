"""CLI interface for The Claude file recovery tool."""

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from collections import Counter

from .models import FileRecord, ProjectSummary
from .scanner import LogScanner
from .recovery import FileRecovery

app = typer.Typer(
    name="theclaude",
    help="🦾 The Claude - Claude Code File Recovery Tool",
    add_completion=False
)
console = Console()


@app.command()
def projects(
    claude_dir: Optional[Path] = typer.Option(
        None, 
        "--claude-dir", 
        help="Path to .claude directory (default: ~/.claude)"
    )
) -> None:
    """List all Claude Code projects and their recoverable files."""
    scanner = LogScanner(claude_dir or Path.home() / ".claude")
    
    console.print(Panel.fit("🦾 The Claude - Claude Code Projects", style="bold blue"))
    
    project_paths = scanner.find_projects()
    if not project_paths:
        console.print("❌ No Claude Code projects found!")
        console.print(f"   Looked in: {scanner.projects_dir}")
        return
    
    table = Table(title="📁 Available Projects")
    table.add_column("Project", style="cyan", no_wrap=True)
    table.add_column("Conversations", justify="right", style="magenta")
    table.add_column("Files", justify="right", style="green")
    table.add_column("Types", style="dim", no_wrap=True)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Last Activity", style="blue")
    
    for project_path in project_paths:
        summary = scanner.get_project_summary(project_path)
        
        last_activity = "Never" if summary.latest_activity is None else summary.latest_activity.strftime("%Y-%m-%d")
        
        table.add_row(
            summary.name,
            str(summary.conversation_count),
            str(summary.file_count),
            summary.file_breakdown,
            summary.size_human,
            last_activity
        )
    
    console.print(table)
    console.print()
    console.print("💡 Use 'theclaude scan <project>' to see recoverable files")
    console.print("💡 Use 'theclaude recover <project>' to recover files")


@app.command()
def scan(
    project: str = typer.Argument(help="Project name to scan"),
    claude_dir: Optional[Path] = typer.Option(
        None, 
        "--claude-dir", 
        help="Path to .claude directory (default: ~/.claude)"
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max files to show"),
    preview: bool = typer.Option(
        False,
        "--preview",
        "-p", 
        help="Show file content preview"
    ),
    file_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by file type (Python, JavaScript, etc.)"
    )
) -> None:
    """Scan a specific project for recoverable files."""
    scanner = LogScanner(claude_dir or Path.home() / ".claude")
    
    # Find matching project
    project_path = _find_project(scanner, project)
    if not project_path:
        return
    
    console.print(Panel.fit(f"🔍 Scanning {project} for recoverable files", style="bold green"))
    
    files = scanner.scan_project_for_files(project_path)
    
    # Apply filters
    if file_type:
        files = [f for f in files if f.file_type.lower() == file_type.lower()]
    
    if not files:
        if file_type:
            console.print(f"❌ No {file_type} files found in this project!")
        else:
            console.print("❌ No recoverable files found in this project!")
        return
    
    # Show enhanced summary with file type breakdown
    total_size = sum(f.size_bytes for f in files)
    if total_size < 1024:
        size_str = f"{total_size}B"
    elif total_size < 1024 * 1024:
        size_str = f"{total_size / 1024:.1f}KB"
    else:
        size_str = f"{total_size / (1024 * 1024):.1f}MB"
    
    # Count file types
    type_counts = Counter(f.file_type for f in files)
    type_breakdown = ", ".join([f"{count} {ftype}" for ftype, count in type_counts.most_common(3)])
    
    # Count versions
    version_files = [f for f in files if hasattr(f, '_version_count')]
    
    console.print(f"📊 Found {len(files)} recoverable files ({size_str} total)")
    if type_breakdown:
        console.print(f"📁 File types: {type_breakdown}")
    if version_files:
        console.print(f"🔄 {len(version_files)} files have multiple versions")
    console.print()
    
    # Show files table
    table = Table(title="💾 Recoverable Files")
    table.add_column("#", width=3, justify="right", style="dim")
    table.add_column("File", style="cyan", min_width=25, max_width=50)
    table.add_column("Type", style="green", no_wrap=True, width=15)
    table.add_column("Operation", justify="center", style="magenta", width=10)
    table.add_column("Size", justify="right", width=8)
    if preview:
        table.add_column("Preview", style="dim", max_width=40)
    table.add_column("Date", style="blue")
    table.add_column("Conversation", style="dim", no_wrap=True)
    
    for i, file_record in enumerate(files[:limit], 1):
        # Use project-relative path for cleaner display
        display_path = file_record.relative_path
        
        # Fallback truncation if relative path is still too long
        if len(display_path) > 60:
            filename = Path(display_path).name
            parent_path = str(Path(display_path).parent)
            if len(parent_path) > 40:
                display_path = f"...{parent_path[-30:]}/{filename}"
            else:
                display_path = f"{parent_path}/{filename}"
        
        # Color code operation types
        op_style = {
            "Write": "green",
            "Read": "blue", 
            "Edit": "yellow",
            "MultiEdit": "orange1"
        }.get(file_record.operation_type, "white")
        
        operation = Text(file_record.operation_type, style=op_style)
        
        # Add version indicator if file has multiple versions with highlighting
        file_type_display = file_record.file_type
        if hasattr(file_record, '_version_count'):
            version_text = f" ({file_record._version_count}v)"
            file_type_display = Text(file_record.file_type)
            file_type_display.append(version_text, style="bold yellow")
        else:
            file_type_display = file_record.file_type
        
        # Create colored size text
        size_text = Text(file_record.size_human, style=file_record.size_color)
        
        row_data = [
            str(i),
            display_path,
            file_type_display,
            operation,
            size_text,
        ]
        
        if preview:
            # Show first line of content as preview
            preview_text = ""
            if file_record.preview_lines:
                preview_text = file_record.preview_lines[0][:37]
                if len(file_record.preview_lines[0]) > 37:
                    preview_text += "..."
            row_data.append(preview_text)
        
        row_data.extend([
            file_record.timestamp_human,
            file_record.conversation_id[:8] + "..."
        ])
        
        table.add_row(*row_data)
    
    console.print(table)
    
    if len(files) > limit:
        console.print(f"... and {len(files) - limit} more files")
    
    console.print()
    console.print("💡 Use 'theclaude recover <project>' to recover files")
    console.print("💡 Use 'theclaude recover <project> --interactive' to choose specific files")
    if file_type:
        console.print(f"💡 Use 'theclaude scan <project>' without --type to see all files")
    if not preview:
        console.print("💡 Use 'theclaude scan <project> --preview' to see file content previews")


@app.command()
def recover(
    project: str = typer.Argument(help="Project name to recover files from"),
    target_dir: Optional[Path] = typer.Option(
        Path("./recovered-files"), 
        "--target", 
        "-t", 
        help="Target directory (default: ./recovered-files)"
    ),
    claude_dir: Optional[Path] = typer.Option(
        None, 
        "--claude-dir", 
        help="Path to .claude directory (default: ~/.claude)"
    ),
    interactive: bool = typer.Option(
        False, 
        "--interactive", 
        "-i", 
        help="Choose which files to recover"
    ),
    force: bool = typer.Option(
        False, 
        "--force", 
        "-f", 
        help="Overwrite existing files without asking"
    ),
    no_backups: bool = typer.Option(
        False, 
        "--no-backups", 
        help="Don't create backup files"
    ),
    preserve_structure: bool = typer.Option(
        True, 
        "--preserve-structure/--flat",
        help="Preserve directory structure"
    ),
    preview: bool = typer.Option(
        False, 
        "--preview", 
        "-p", 
        help="Preview what would be recovered without doing it"
    )
) -> None:
    """Recover files from a Claude Code project."""
    scanner = LogScanner(claude_dir or Path.home() / ".claude")
    recovery = FileRecovery(create_backups=not no_backups)
    
    # Find matching project
    project_path = _find_project(scanner, project)
    if not project_path:
        return
    
    console.print(Panel.fit(f"🦾 Recovering files from {project}", style="bold green"))
    
    files = scanner.scan_project_for_files(project_path)
    
    if not files:
        console.print("❌ No recoverable files found in this project!")
        return
    
    # Interactive file selection
    if interactive:
        files = _interactive_file_selection(files)
        if not files:
            console.print("❌ No files selected for recovery!")
            return
    
    # Preview mode
    if preview:
        recovery.preview_recovery(files, target_dir, preserve_structure)
        return
    
    # Confirm recovery
    if not force and not interactive:
        total_size = sum(f.size_bytes for f in files)
        if total_size < 1024:
            size_str = f"{total_size}B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f}KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.1f}MB"
        
        if not Confirm.ask(f"Recover {len(files)} files ({size_str}) to {target_dir}?"):
            console.print("❌ Recovery cancelled!")
            return
    
    # Perform recovery
    console.print("🚀 Starting recovery...")
    results = recovery.recover_files(files, target_dir, preserve_structure, force)
    
    # Show detailed recovery report
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    backed_up = [r for r in successful if r.backup_created]
    
    console.print()
    console.print(Panel.fit(
        f"🎉 Recovery Complete: {len(successful)} succeeded, {len(failed)} failed",
        style="bold green" if len(failed) == 0 else "bold yellow"
    ))
    
    # Recovery statistics
    if successful:
        total_recovered_size = sum(r.file_record.size_bytes for r in successful)
        if total_recovered_size < 1024:
            size_str = f"{total_recovered_size}B"
        elif total_recovered_size < 1024 * 1024:
            size_str = f"{total_recovered_size / 1024:.1f}KB"
        else:
            size_str = f"{total_recovered_size / (1024 * 1024):.1f}MB"
        
        type_counts = Counter(r.file_record.file_type for r in successful)
        top_types = type_counts.most_common(3)
        
        console.print(f"📊 Recovered {size_str} across {len(type_counts)} file types")
        if top_types:
            type_list = ", ".join([f"{count} {ftype}" for ftype, count in top_types])
            console.print(f"📁 Types: {type_list}")
        
        if backed_up:
            console.print(f"💾 Created {len(backed_up)} backup files")
    
    if failed:
        console.print("❌ Failed recoveries:")
        for result in failed:
            console.print(f"   {result.file_record.file_name}: {result.error_message}")


def _find_project(scanner: LogScanner, project: str) -> Optional[Path]:
    """Find a project by name or partial match."""
    project_paths = scanner.find_projects()
    
    # Exact match first
    for path in project_paths:
        if scanner._extract_project_name(path.name) == project:
            return path
    
    # Partial match
    matches = []
    for path in project_paths:
        project_name = scanner._extract_project_name(path.name)
        if project.lower() in project_name.lower():
            matches.append((path, project_name))
    
    if not matches:
        console.print(f"❌ No project found matching '{project}'")
        console.print("💡 Use 'theclaude projects' to see available projects")
        return None
    
    if len(matches) == 1:
        return matches[0][0]
    
    # Multiple matches - let user choose
    console.print(f"Multiple projects match '{project}':")
    for i, (path, name) in enumerate(matches, 1):
        console.print(f"  {i}. {name}")
    
    try:
        choice = int(Prompt.ask("Select project", choices=[str(i) for i in range(1, len(matches) + 1)]))
        return matches[choice - 1][0]
    except (ValueError, IndexError):
        console.print("❌ Invalid selection!")
        return None


def _interactive_file_selection(files: List[FileRecord]) -> List[FileRecord]:
    """Let user interactively select which files to recover."""
    console.print("📁 Select files to recover:")
    console.print("   (Enter numbers separated by commas, 'all' for all files, or 'q' to quit)")
    console.print()
    
    # Show numbered list
    for i, file_record in enumerate(files, 1):
        display_path = file_record.file_path
        if len(display_path) > 80:
            display_path = "..." + display_path[-77:]
        
        console.print(f"  {i:2d}. {display_path} ({file_record.size_human}, {file_record.operation_type})")
    
    console.print()
    
    while True:
        selection = Prompt.ask("Select files")
        
        # Handle exit commands
        if selection.lower() in ['q', 'quit', 'exit', 'cancel', '']:
            console.print("❌ Selection cancelled")
            return []
        
        if selection.lower() == 'all':
            return files
        
        try:
            indices = []
            for part in selection.split(','):
                part = part.strip()
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    indices.extend(range(start, end + 1))
                else:
                    indices.append(int(part))
            
            selected_files = []
            for idx in indices:
                if 1 <= idx <= len(files):
                    selected_files.append(files[idx - 1])
                else:
                    console.print(f"❌ Invalid file number: {idx}")
                    break
            else:
                return selected_files
                
        except ValueError:
            console.print("❌ Invalid selection format! Use numbers separated by commas, 'all', or 'q' to quit")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()