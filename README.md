# LLM File Assistant

A resume-handling assistant where an LLM (via **OpenRouter** by default; Anthropic or OpenAI direct also supported) calls Python file-system tools to answer natural-language requests.

## Project structure

```
fs_tools.py                 # Part A: read_file, list_files, write_file, search_in_file + JSON schemas
llm_file_assistant.py       # Part B: agentic tool-use loop (OpenRouter / Anthropic / OpenAI)
generate_sample_resumes.py  # Regenerates the sample data
resumes/                    # 8 dummy resumes (3 PDF, 3 DOCX, 2 TXT)
tests/test_fs_tools.py      # pytest suite (no API key needed)
requirements.txt
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (or export the variables):

```
OPENROUTER_API_KEY=sk-or-v1-...
# optional: any tool-capable model listed on https://openrouter.ai/models
LLM_MODEL=anthropic/claude-sonnet-4.5
```

Get a key at https://openrouter.ai/keys. Pick a model that supports tool calling (e.g. `openai/gpt-4o-mini`, `google/gemini-2.5-flash`, `anthropic/claude-sonnet-4.5`).

To call providers directly instead, set `LLM_PROVIDER=anthropic` (with `ANTHROPIC_API_KEY`) or `LLM_PROVIDER=openai` (with `OPENAI_API_KEY`).

## Usage

```bash
# One-shot queries
python llm_file_assistant.py "Read all resumes in the resumes folder"
python llm_file_assistant.py "Find resumes mentioning Python experience"
python llm_file_assistant.py "Create a summary file for resume_john_doe.pdf"

# Interactive chat (keeps context between questions)
python llm_file_assistant.py

# Options
python llm_file_assistant.py --model openai/gpt-4o-mini "..."
python llm_file_assistant.py --quiet "..."      # hide tool-call logs
```

Tool calls are logged to stderr, e.g. `🔧 search_in_file({'filepath': 'resumes/resume_john_doe.pdf', 'keyword': 'Python'})`. Summaries are saved to `summaries/<name>_summary.md`.

### Using the tools directly

```python
from fs_tools import read_file, list_files, write_file, search_in_file

list_files("resumes", ".pdf")
read_file("resumes/resume_john_doe.pdf")["content"]
search_in_file("resumes/resume_chen_wei.docx", "python")["matches"]
write_file("out/notes.md", "# Notes")
```

## Tool reference

| Tool | Returns | Notes |
|---|---|---|
| `read_file(filepath)` | `{success, filename, extension, content, metadata}` | PDF (pypdf), DOCX incl. tables, TXT/MD; 10 MB cap |
| `list_files(directory, extension=None)` | `[{name, path, extension, size_bytes, modified}]` | Extension filter accepts `.pdf`, `pdf`, `PDF` |
| `write_file(filepath, content)` | `{success, filepath, bytes_written, created}` | Creates parent dirs, UTF-8 |
| `search_in_file(filepath, keyword)` | `{success, match_count, matches:[{line, position, match, context}]}` | Case-insensitive, ±60 chars context |

**Error handling:** tools never raise; failures come back as `{"success": false, "error": "..."}` so the LLM can read them and recover (missing file, unsupported type, corrupt PDF, permission denied, bad arguments).

## How the LLM integration works

1. Tool schemas are defined once in `fs_tools.TOOL_SCHEMAS` (JSON Schema) and adapted to each provider's format.
2. The user query goes to the model with the tool list.
3. If the model requests tools, `execute_tool` dispatches them and results go back as tool messages.
4. This repeats (max 15 rounds) until the model returns a final text answer.

## Tests

```bash
pytest -q
```

Covers all three formats, extension filtering, directory creation, case-insensitive search with context, and error cases.

## Regenerating sample data

```bash
python generate_sample_resumes.py
```
