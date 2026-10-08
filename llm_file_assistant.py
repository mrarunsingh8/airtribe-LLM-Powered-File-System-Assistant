"""
llm_file_assistant.py — Natural-language file assistant powered by LLM tool use.

The LLM decides which fs_tools to call; this module runs the agentic loop:

    user query -> LLM -> (tool calls -> execute -> results back to LLM)* -> answer

Providers:
    * OpenRouter (default) — set OPENROUTER_API_KEY (OpenAI-compatible API, any model)
    * Anthropic            — set ANTHROPIC_API_KEY and use --provider anthropic
    * OpenAI               — set OPENAI_API_KEY and use --provider openai

Usage:
    python llm_file_assistant.py "Find resumes mentioning Python experience"
    python llm_file_assistant.py            # interactive mode
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Callable, Optional

from fs_tools import TOOL_SCHEMAS, execute_tool

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

SYSTEM_PROMPT = """You are a helpful file assistant for a recruiting team.
You can read, list, search and write files using the provided tools.
Resumes live in the 'resumes' folder unless the user says otherwise.

Guidelines:
- Use list_files first when you need to know which files exist.
- To find resumes mentioning a skill, call search_in_file on each resume, then report
  which ones matched with a short quote of the context.
- When asked to create a summary, read the resume, then write a concise markdown summary
  (name, contact, experience, key skills, education) with write_file. Unless told
  otherwise, save it to 'summaries/<resume_name_without_extension>_summary.md'.
- If a tool returns an error, explain it plainly and try a sensible alternative.
- Keep final answers short and concrete."""

MAX_TOOL_ROUNDS = 15
DEFAULT_MODELS = {
    "openrouter": "anthropic/claude-sonnet-4.5",
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RESULT_CHARS = 20_000  # protect the context window from huge files


def _serialise(result) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + '… [truncated]"'
    return text


def _log_call(name: str, args: dict, verbose: bool) -> None:
    if verbose:
        shown = {k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v)
                 for k, v in args.items()}
        print(f"  🔧 {name}({shown})", file=sys.stderr)


class FileAssistant:
    """Runs a multi-turn, tool-using conversation with an LLM."""

    def __init__(self, provider: str = "openrouter", model: Optional[str] = None,
                 verbose: bool = True,
                 tool_executor: Callable[[str, dict], object] = execute_tool):
        self.provider = provider.lower()
        if self.provider not in DEFAULT_MODELS:
            raise ValueError(f"Unsupported provider: {provider}")
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS[self.provider]
        self.verbose = verbose
        self.execute = tool_executor
        self.history: list = []

        if self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic()
            self.tools = [
                {"name": t["name"], "description": t["description"],
                 "input_schema": t["parameters"]}
                for t in TOOL_SCHEMAS
            ]
        else:
            import openai
            if self.provider == "openrouter":
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    raise RuntimeError("OPENROUTER_API_KEY is not set")
                self.client = openai.OpenAI(
                    base_url=OPENROUTER_BASE_URL, api_key=api_key,
                    default_headers={"X-Title": "LLM File Assistant"},
                )
            else:
                self.client = openai.OpenAI()
            self.tools = [{"type": "function", "function": t} for t in TOOL_SCHEMAS]
            self.history.append({"role": "system", "content": SYSTEM_PROMPT})

    # ------------------------------------------------------------------ #
    def ask(self, query: str) -> str:
        """Send a user query, run tools until the model is done, return its answer."""
        self.history.append({"role": "user", "content": query})
        runner = self._ask_anthropic if self.provider == "anthropic" else self._ask_openai
        return runner()

    # ------------------------------------------------------------------ #
    def _ask_anthropic(self) -> str:
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model, max_tokens=4096, system=SYSTEM_PROMPT,
                tools=self.tools, messages=self.history,
            )
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text").strip()

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                _log_call(block.name, block.input, self.verbose)
                output = self.execute(block.name, block.input)
                is_error = isinstance(output, dict) and output.get("success") is False
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": _serialise(output), "is_error": is_error})
            self.history.append({"role": "user", "content": results})
        return "Stopped: too many tool calls in one turn."

    # ------------------------------------------------------------------ #
    def _ask_openai(self) -> str:
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.chat.completions.create(
                model=self.model, messages=self.history, tools=self.tools,
            )
            msg = response.choices[0].message
            self.history.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                return (msg.content or "").strip()

            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                _log_call(call.function.name, args, self.verbose)
                output = self.execute(call.function.name, args)
                self.history.append({"role": "tool", "tool_call_id": call.id,
                                     "content": _serialise(output)})
        return "Stopped: too many tool calls in one turn."


# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-powered file assistant")
    parser.add_argument("query", nargs="*", help="Query to run (omit for interactive mode)")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "openrouter"),
                        choices=["openrouter", "anthropic", "openai"])
    parser.add_argument("--model", default=None, help="Override the model name")
    parser.add_argument("--quiet", action="store_true", help="Hide tool-call logs")
    args = parser.parse_args()

    try:
        assistant = FileAssistant(args.provider, args.model, verbose=not args.quiet)
    except Exception as exc:
        sys.exit(f"Could not start assistant: {exc}")

    if args.query:
        print(assistant.ask(" ".join(args.query)))
        return

    print(f"File assistant ({assistant.provider}:{assistant.model}). Type 'exit' to quit.")
    while True:
        try:
            query = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in {"exit", "quit"}:
            break
        if query:
            try:
                print(f"\nAssistant: {assistant.ask(query)}")
            except Exception as exc:
                print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
