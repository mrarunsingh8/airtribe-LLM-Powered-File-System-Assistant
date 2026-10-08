"""Unit tests for fs_tools (no API key needed). Run: pytest -q"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from fs_tools import (execute_tool, list_files, read_file,  # noqa: E402
                      search_in_file, write_file)

RESUMES = Path(__file__).resolve().parent.parent / "resumes"


@pytest.mark.parametrize("name", ["resume_john_doe.pdf", "resume_maria_garcia.docx",
                                  "resume_aisha_khan.txt"])
def test_read_each_format(name):
    r = read_file(str(RESUMES / name))
    assert r["success"], r
    assert r["metadata"]["word_count"] > 20
    assert "EXPERIENCE" in r["content"].upper()


def test_read_errors(tmp_path):
    assert not read_file(str(tmp_path / "missing.pdf"))["success"]
    bad = tmp_path / "x.xyz"
    bad.write_text("hi")
    assert "Unsupported" in read_file(str(bad))["error"]
    corrupt = tmp_path / "c.pdf"
    corrupt.write_text("not a pdf")
    assert not read_file(str(corrupt))["success"]


def test_list_files_filter():
    all_files = list_files(str(RESUMES))
    pdfs = list_files(str(RESUMES), "PDF")
    assert len(all_files) >= 5
    assert pdfs and all(f["extension"] == ".pdf" for f in pdfs)
    assert {"name", "size_bytes", "modified"} <= pdfs[0].keys()
    assert list_files("/no/such/dir")[0]["success"] is False


def test_write_creates_dirs(tmp_path):
    target = tmp_path / "a" / "b" / "out.md"
    r = write_file(str(target), "hello")
    assert r["success"] and r["created"] and target.read_text() == "hello"


def test_search_case_insensitive():
    r = search_in_file(str(RESUMES / "resume_john_doe.pdf"), "PYTHON")
    assert r["success"] and r["match_count"] >= 2
    assert "python" in r["matches"][0]["context"].lower()
    assert search_in_file(str(RESUMES / "resume_lucas_martin.docx"), "python")["match_count"] == 0
    assert not search_in_file(str(RESUMES / "resume_john_doe.pdf"), "  ")["success"]


def test_execute_tool_dispatch():
    assert execute_tool("nope", {})["success"] is False
    assert execute_tool("read_file", {"wrong": 1})["success"] is False
