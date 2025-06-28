"""Data models for file recovery operations."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Dict, List
from collections import Counter


@dataclass
class FileRecord:
    """Represents a recoverable file found in conversation logs."""
    
    file_path: str
    content: str
    operation_type: Literal["Write", "Read", "Edit", "MultiEdit"]
    timestamp: datetime
    conversation_id: str
    project_name: str
    size_bytes: int
    
    @property
    def file_name(self) -> str:
        """Get just the filename from the full path."""
        return Path(self.file_path).name
    
    @property
    def relative_path(self) -> str:
        """Get path relative to project root if possible."""
        path = Path(self.file_path)
        
        # Try to make it relative to common project structures
        parts = path.parts
        
        # Look for common project root indicators
        project_indicators = [
            'src', 'lib', 'app', 'components', 'pages', 'api', 'utils', 'tests', 'docs'
        ]
        
        for i, part in enumerate(parts):
            if part in project_indicators and i > 0:
                # Take everything from the indicator onwards
                return str(Path(*parts[i:]))
        
        # If no project structure found, try to get last 2-3 meaningful parts
        if len(parts) > 3:
            return str(Path(*parts[-3:]))
        elif len(parts) > 1:
            return str(Path(*parts[-2:]))
        
        return path.name
    
    @property
    def size_human(self) -> str:
        """Human readable file size."""
        if self.size_bytes < 1024:
            return f"{self.size_bytes}B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f}KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f}MB"
    
    @property
    def size_color(self) -> str:
        """Color for file size based on size thresholds."""
        if self.size_bytes > 100 * 1024:  # > 100KB
            return "red"
        elif self.size_bytes > 10 * 1024:  # > 10KB
            return "yellow"
        else:
            return "green"
    
    @property
    def timestamp_human(self) -> str:
        """Human readable timestamp."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    @property
    def file_extension(self) -> str:
        """Get file extension for categorization."""
        return Path(self.file_path).suffix.lower()
    
    @property
    def file_type(self) -> str:
        """Get human-readable file type."""
        ext = self.file_extension
        type_map = {
            '.py': 'Python',
            '.js': 'JavaScript', 
            '.ts': 'TypeScript',
            '.jsx': 'React',
            '.tsx': 'React TS',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.toml': 'TOML',
            '.md': 'Markdown',
            '.txt': 'Text',
            '.sql': 'SQL',
            '.sh': 'Shell',
            '.dockerfile': 'Docker',
            '.rs': 'Rust',
            '.go': 'Go',
            '.java': 'Java',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.c': 'C',
            '.cpp': 'C++',
            '.h': 'Header',
        }
        return type_map.get(ext, 'Other')
    
    @property
    def preview_lines(self) -> List[str]:
        """Get first 5 lines of content for preview."""
        lines = self.content.split('\n')
        return lines[:5]
    
    @property
    def line_count(self) -> int:
        """Get total number of lines."""
        return len(self.content.split('\n'))


@dataclass 
class ProjectSummary:
    """Summary of a Claude Code project and its recoverable files."""
    
    name: str
    path: Path
    conversation_count: int
    file_count: int
    total_size_bytes: int
    latest_activity: Optional[datetime] = None
    file_types: Optional[Counter] = None
    
    @property
    def size_human(self) -> str:
        """Human readable total size."""
        if self.total_size_bytes < 1024:
            return f"{self.total_size_bytes}B"
        elif self.total_size_bytes < 1024 * 1024:
            return f"{self.total_size_bytes / 1024:.1f}KB"
        else:
            return f"{self.total_size_bytes / (1024 * 1024):.1f}MB"
    
    @property
    def file_breakdown(self) -> str:
        """Human readable file type breakdown."""
        if not self.file_types:
            return ""
        
        # Show top 3 file types
        top_types = self.file_types.most_common(3)
        parts = [f"{count} {file_type}" for file_type, count in top_types]
        
        if len(self.file_types) > 3:
            others = sum(count for _, count in self.file_types.most_common()[3:])
            if others > 0:
                parts.append(f"{others} other")
        
        return ", ".join(parts)


@dataclass
class RecoveryResult:
    """Result of a file recovery operation."""
    
    file_record: FileRecord
    success: bool
    target_path: Path
    error_message: Optional[str] = None
    was_existing: bool = False
    backup_created: bool = False