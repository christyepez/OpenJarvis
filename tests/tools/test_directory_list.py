from __future__ import annotations

from openjarvis.tools.directory_list import ListDirectoryTool


def test_list_directory_lists_immediate_entries(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / ".secret").write_text("hidden", encoding="utf-8")

    result = ListDirectoryTool().execute(path=str(tmp_path))

    assert result.success is True
    assert "[DIR] src" in result.content
    assert "[FILE] README.md" in result.content
    assert ".secret" not in result.content
    assert result.metadata["path"] == str(tmp_path.resolve())


def test_list_directory_can_include_hidden_entries(tmp_path) -> None:
    (tmp_path / ".github").mkdir()

    result = ListDirectoryTool().execute(
        path=str(tmp_path),
        include_hidden=True,
    )

    assert result.success is True
    assert "[DIR] .github" in result.content


def test_list_directory_rejects_missing_directory(tmp_path) -> None:
    result = ListDirectoryTool().execute(path=str(tmp_path / "missing"))

    assert result.success is False
    assert "Directory not found" in result.content
