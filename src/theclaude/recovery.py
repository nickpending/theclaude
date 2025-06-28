"""File recovery engine for restoring files from conversation logs."""

import shutil
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Confirm

from .models import FileRecord, RecoveryResult

console = Console()


class FileRecovery:
    """Handles recovery of files from conversation logs to disk."""
    
    def __init__(self, create_backups: bool = True):
        self.create_backups = create_backups
    
    def recover_file(
        self, 
        file_record: FileRecord, 
        target_path: Optional[Path] = None,
        force: bool = False
    ) -> RecoveryResult:
        """Recover a single file to disk.
        
        Args:
            file_record: The file record to recover
            target_path: Custom target path (defaults to original path)
            force: If True, overwrite existing files without prompting
            
        Returns:
            RecoveryResult with success status and details
        """
        # Determine target path
        if target_path is None:
            target_path = Path(file_record.file_path)
        
        # Check if file already exists
        was_existing = target_path.exists()
        backup_created = False
        
        if was_existing and not force:
            if not Confirm.ask(
                f"File {target_path} already exists. Overwrite?",
                default=False
            ):
                return RecoveryResult(
                    file_record=file_record,
                    success=False,
                    target_path=target_path,
                    error_message="User cancelled overwrite",
                    was_existing=True
                )
        
        try:
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup if file exists and backups are enabled
            if was_existing and self.create_backups:
                backup_path = target_path.with_suffix(target_path.suffix + '.backup')
                shutil.copy2(target_path, backup_path)
                backup_created = True
                console.print(f"💾 Created backup: {backup_path}")
            
            # Write the recovered content
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(file_record.content)
            
            console.print(f"✅ Recovered: {target_path}")
            
            return RecoveryResult(
                file_record=file_record,
                success=True,
                target_path=target_path,
                was_existing=was_existing,
                backup_created=backup_created
            )
            
        except Exception as e:
            return RecoveryResult(
                file_record=file_record,
                success=False,
                target_path=target_path,
                error_message=str(e),
                was_existing=was_existing,
                backup_created=backup_created
            )
    
    def recover_files(
        self, 
        file_records: List[FileRecord],
        target_dir: Optional[Path] = None,
        preserve_structure: bool = True,
        force: bool = False
    ) -> List[RecoveryResult]:
        """Recover multiple files.
        
        Args:
            file_records: List of file records to recover
            target_dir: Directory to recover files to (defaults to original paths)
            preserve_structure: If True, maintain directory structure
            force: If True, overwrite existing files without prompting
            
        Returns:
            List of RecoveryResult objects
        """
        results = []
        
        for file_record in file_records:
            if target_dir is not None:
                if preserve_structure:
                    # Try to preserve the relative path structure
                    rel_path = self._make_relative_path(file_record.file_path)
                    target_path = target_dir / rel_path
                else:
                    # Just put all files in the target directory
                    target_path = target_dir / Path(file_record.file_path).name
            else:
                target_path = None
            
            result = self.recover_file(file_record, target_path, force)
            results.append(result)
            
            if not result.success:
                console.print(f"❌ Failed to recover {file_record.file_path}: {result.error_message}")
        
        return results
    
    def _make_relative_path(self, file_path: str) -> Path:
        """Convert absolute path to relative path for recovery."""
        path = Path(file_path)
        
        # Try to make it relative to common project structures
        parts = path.parts
        
        # Look for common project root indicators
        project_indicators = [
            'src', 'lib', 'app', '.claude', 'tests', 'docs'
        ]
        
        for i, part in enumerate(parts):
            if part in project_indicators and i > 0:
                # Take everything from the parent of the indicator
                return Path(*parts[i-1:])
        
        # If no project structure found, just take the filename
        return Path(path.name)
    
    def preview_recovery(
        self, 
        file_records: List[FileRecord],
        target_dir: Optional[Path] = None,
        preserve_structure: bool = True
    ) -> None:
        """Preview what would be recovered without actually doing it."""
        console.print("🔍 Recovery Preview:")
        console.print()
        
        for file_record in file_records:
            if target_dir is not None:
                if preserve_structure:
                    rel_path = self._make_relative_path(file_record.file_path)
                    target_path = target_dir / rel_path
                else:
                    target_path = target_dir / Path(file_record.file_path).name
            else:
                target_path = Path(file_record.file_path)
            
            status = "📝 NEW" if not target_path.exists() else "⚠️  OVERWRITE"
            console.print(f"{status} {target_path} ({file_record.size_human})")
        
        console.print()
        console.print(f"Total files: {len(file_records)}")
        total_size = sum(f.size_bytes for f in file_records)
        if total_size < 1024:
            size_str = f"{total_size}B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f}KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.1f}MB"
        console.print(f"Total size: {size_str}")