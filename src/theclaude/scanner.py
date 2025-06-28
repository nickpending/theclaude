"""Scanner for Claude Code conversation logs to find recoverable files."""

import json
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

from rich.console import Console
from rich.progress import Progress, TaskID

from .models import FileRecord, ProjectSummary
from collections import Counter, defaultdict

console = Console()


class LogScanner:
    """Scans Claude Code conversation logs for recoverable files."""
    
    def __init__(self, claude_dir: Path = Path.home() / ".claude"):
        self.claude_dir = claude_dir
        self.projects_dir = claude_dir / "projects"
    
    def find_projects(self) -> List[Path]:
        """Find all Claude Code project directories."""
        if not self.projects_dir.exists():
            console.print(f"❌ Claude projects directory not found: {self.projects_dir}")
            return []
        
        projects = []
        for item in self.projects_dir.iterdir():
            if item.is_dir() and any(item.glob("*.jsonl")):
                projects.append(item)
        
        return sorted(projects)
    
    def get_project_summary(self, project_path: Path) -> ProjectSummary:
        """Get summary information for a project."""
        conversation_files = list(project_path.glob("*.jsonl"))
        
        # Quick scan to count files and get latest activity
        file_count = 0
        total_size = 0
        latest_activity = None
        file_types = Counter()
        
        for conv_file in conversation_files:
            try:
                files = list(self._scan_conversation_for_files(conv_file))
                file_count += len(files)
                
                for file_record in files:
                    total_size += file_record.size_bytes
                    file_types[file_record.file_type] += 1
                    if latest_activity is None or file_record.timestamp > latest_activity:
                        latest_activity = file_record.timestamp
                        
            except Exception as e:
                console.print(f"⚠️  Error scanning {conv_file.name}: {e}")
                continue
        
        return ProjectSummary(
            name=self._extract_project_name(project_path.name),
            path=project_path,
            conversation_count=len(conversation_files),
            file_count=file_count,
            total_size_bytes=total_size,
            latest_activity=latest_activity,
            file_types=file_types
        )
    
    def scan_project_for_files(self, project_path: Path) -> List[FileRecord]:
        """Scan all conversations in a project for recoverable files."""
        conversation_files = list(project_path.glob("*.jsonl"))
        all_files = []
        
        with Progress() as progress:
            task = progress.add_task(
                f"Scanning {self._extract_project_name(project_path.name)}...", 
                total=len(conversation_files)
            )
            
            for conv_file in conversation_files:
                try:
                    files = list(self._scan_conversation_for_files(conv_file))
                    all_files.extend(files)
                except Exception as e:
                    console.print(f"⚠️  Error scanning {conv_file.name}: {e}")
                finally:
                    progress.advance(task)
        
        # Group by file path to detect versions, keeping the most recent as primary
        file_versions = defaultdict(list)
        for file_record in all_files:
            file_versions[file_record.file_path].append(file_record)
        
        # For each file, sort versions by timestamp and keep the latest
        final_files = []
        for file_path, versions in file_versions.items():
            versions.sort(key=lambda f: f.timestamp, reverse=True)
            latest = versions[0]
            
            # Add version info to the latest record
            if len(versions) > 1:
                # Monkey patch version count (could make this a proper field later)
                latest._version_count = len(versions)
            
            final_files.append(latest)
        
        return sorted(final_files, key=lambda f: f.timestamp, reverse=True)
    
    def _scan_conversation_for_files(self, jsonl_file: Path) -> Iterator[FileRecord]:
        """Scan a single conversation log file for file operations."""
        project_name = self._extract_project_name(jsonl_file.parent.name)
        conversation_id = jsonl_file.stem
        
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    
                    # Look for file operations in tool use
                    if entry.get('type') == 'assistant' and 'message' in entry:
                        message = entry['message']
                        
                        if 'content' in message and isinstance(message['content'], list):
                            timestamp = self._parse_timestamp(entry.get('timestamp', ''))
                            
                            for content_item in message['content']:
                                if content_item.get('type') == 'tool_use':
                                    file_record = self._extract_file_from_tool_use(
                                        content_item, timestamp, conversation_id, project_name
                                    )
                                    if file_record:
                                        yield file_record
                    
                    # Look for file content in tool results  
                    if entry.get('type') == 'user' and 'toolUseResult' in entry:
                        result = entry['toolUseResult']
                        if isinstance(result, dict) and result.get('type') == 'text':
                            file_info = result.get('file', {})
                            if 'filePath' in file_info and 'content' in file_info:
                                timestamp = self._parse_timestamp(entry.get('timestamp', ''))
                                yield FileRecord(
                                    file_path=file_info['filePath'],
                                    content=file_info['content'], 
                                    operation_type="Read",
                                    timestamp=timestamp,
                                    conversation_id=conversation_id,
                                    project_name=project_name,
                                    size_bytes=len(file_info['content'].encode('utf-8'))
                                )
                                
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # Skip malformed entries
                    continue
    
    def _extract_file_from_tool_use(
        self, 
        tool_use: dict, 
        timestamp: datetime, 
        conversation_id: str, 
        project_name: str
    ) -> Optional[FileRecord]:
        """Extract file information from a tool use entry."""
        tool_name = tool_use.get('name', '')
        tool_input = tool_use.get('input', {})
        
        if tool_name == 'Write' and 'file_path' in tool_input and 'content' in tool_input:
            return FileRecord(
                file_path=tool_input['file_path'],
                content=tool_input['content'],
                operation_type="Write", 
                timestamp=timestamp,
                conversation_id=conversation_id,
                project_name=project_name,
                size_bytes=len(tool_input['content'].encode('utf-8'))
            )
        
        elif tool_name == 'Edit' and 'file_path' in tool_input:
            # For edits, we'd need to reconstruct the file, which is complex
            # For now, skip Edit operations as they're harder to recover
            return None
            
        elif tool_name == 'MultiEdit' and 'file_path' in tool_input:
            # Similar to Edit, MultiEdit is complex to reconstruct
            return None
            
        return None
    
    def _extract_project_name(self, directory_name: str) -> str:
        """Extract a human-readable project name from directory name."""
        # Claude Code creates directories like "-Users-rudy-development-projects-myproject"
        if directory_name.startswith('-'):
            parts = directory_name.split('-')
            if len(parts) > 1:
                return parts[-1]  # Take the last part as project name
        return directory_name
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse ISO timestamp string into datetime."""
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return datetime.now()  # Fallback to current time