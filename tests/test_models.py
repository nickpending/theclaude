"""Tests for data models."""

from datetime import datetime
from pathlib import Path

from theclaude.models import FileRecord, ProjectSummary


def test_file_record_properties():
    """Test FileRecord property methods."""
    file_record = FileRecord(
        file_path="/Users/rudy/development/projects/myproject/src/main.py",
        content="print('hello world')",
        operation_type="Write",
        timestamp=datetime.now(),
        conversation_id="abc123",
        project_name="myproject",
        size_bytes=1024
    )
    
    assert file_record.file_name == "main.py"
    assert file_record.size_human == "1.0KB"
    assert "main.py" in file_record.relative_path


def test_project_summary_properties():
    """Test ProjectSummary property methods."""
    summary = ProjectSummary(
        name="myproject",
        path=Path("/some/path"),
        conversation_count=5,
        file_count=10,
        total_size_bytes=2048,
        latest_activity=datetime.now()
    )
    
    assert summary.size_human == "2.0KB"