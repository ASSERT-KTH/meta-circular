#!/usr/bin/env python3
"""Minimal coding agent backed by any OpenAI-compatible chat completions API.
Implemented from spec.md
"""

import argparse
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
import time

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a coding agent running on the user's machine.\n"
    "You have access to tools to read and write files, run shell commands,\n"
    "and search the codebase. Use them to complete the user's task.\n"
    "Work incrementally: read before you write, run tests after changes.\n"
    "When the task is done, summarise what you did."
)

# ---------------------------------------------------------------------------
# Tool definitions (sent to the API)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "start_line": {"type": "integer", "description": "First line to return (1-based, default 1)."},
                    "end_line": {"type": "integer", "description": "Last line to return inclusive (default EOF)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "content": {"type": "string", "description": "Full new content of the file."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command via bash and capture stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                    "timeout": {"type": "integer", "description": "Max seconds to wait (default 30)."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern relative to the working directory (e.g. **/*.py)."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Search file contents with a regular expression. Returns matching lines as path:line_number: content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression to search for."},
                    "glob": {"type": "string", "description": "Restrict search to files matching this glob pattern."},
                },
                "required": ["pattern"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

OUTPUT_CAP = 10_000


def _cap(text: str) -> str:
    if len(text) <= OUTPUT_CAP:
        return text
    return text[:OUTPUT_CAP] + f"\n... [truncated, {len(text) - OUTPUT_CAP} chars omitted]"


def tool_read_file(cwd: str, path: str, start_line: int = None, end_line: int = None) -> str:
    full = os.path.join(cwd, path)
    try:
        with open(full, "r", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return f"ERROR: {e}"

    start = max(0, start_line - 1) if start_line is not None else 0
    end = end_line if end_line is not None else len(lines)
    selected = lines[start:end]
    return _cap("".join(selected))


def tool_write_file(cwd: str, path: str, content: str) -> str:
    full = os.path.join(cwd, path)
    try:
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        return "OK"
    except OSError as e:
        return f"ERROR: {e}"


def tool_run_shell(cwd: str, command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return json.dumps({
            "stdout": _cap(result.stdout),
            "stderr": _cap(result.stderr),
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"stdout": "", "stderr": "ERROR: command timed out", "exit_code": -1})
    except OSError as e:
        return json.dumps({"stdout": "", "stderr": f"ERROR: {e}", "exit_code": -1})


def tool_list_files(cwd: str, pattern: str) -> str:
    try:
        matches = glob.glob(pattern, root_dir=cwd, recursive=True)
        if not matches:
            return "(no files matched)"
        return "\n".join(sorted(matches))
    except Exception as e:
        return f"ERROR: {e}"


def tool_search_text(cwd: str, pattern: str, glob_pattern: str = None) -> str:
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"ERROR: invalid regex: {e}"

    if glob_pattern:
        candidates = glob.glob(glob_pattern, root_dir=cwd, recursive=True)
    else:
        candidates = glob.glob("**/*", root_dir=cwd, recursive=True)

    results = []
    for rel_path in sorted(candidates):
        full = os.path.join(cwd, rel_path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if regex.search(line):
                        results.append(f"{rel_path}:{lineno}: {line.rstrip()}")
                        if len(results) >= 200:
                            results.append("... [result limit reached]")
                            return "\n".join(results)
        except OSError:
            continue

    return "\n".join(results) if results else "(no matches)"


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def dispatch_tool(cwd: str, name: str, args: dict) -> str:
    if name == "read_file":
        if "path" not in args:
            return "ERROR: missing required parameter 'path'"
        return tool_read_file(cwd, args["path"], args.get("start_line"), args.get("end_line"))

    if name == "write_file":
        for p in ("path", "content"):
            if p not in args:
                return f"ERROR: missing required parameter '{p}'"
        return tool_write_file(cwd, args["path"], args["content"])

    if name == "run_shell":
        if "command" not in args:
            return "ERROR: missing required parameter 'command'"
        return tool_run_shell(cwd, args["command"], args.get("timeout", 30))

    if name == "list_files":
        if "pattern" not in args:
            return "ERROR: missing required parameter 'pattern'"
        return tool_list_files(cwd, args["pattern"])

    if name == "search_text":
        if "pattern" not in args:
            return "ERROR: missing required parameter 'pattern'"
        return tool_search_text(cwd, args["pattern"], args.get("glob"))

    return f"ERROR: unknown tool '{name}'"


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def log_tool_call(name: str, args: dict) -> None:
    args_preview = json.dumps(args, ensure_ascii=False)
    if len(args_preview) > 200:
        args_preview = args_preview[:200] + "..."
    log(f"[tool]   {name}: {args_preview}")


def log_result(result: str) -> None:
    preview = result.replace("\n", " ")
    if len(preview) > 200:
        preview = preview[:200] + "..."
    log(f"[result] {preview}")


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------

def chat_with_retry(client: OpenAI, **kwargs) -> object:
    retryable = (APIError, APITimeoutError, RateLimitError)
    for attempt in range(4):
        try:
            return client.chat.completions.create(**kwargs)
        except retryable as e:
            if attempt == 3:
                raise
            wait = 2 ** attempt  # 1 s, 2 s, then fail
            log(f"[warn]   API error ({e}), retrying in {wait}s...")
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_agent(client: OpenAI, model: str, cwd: str, task: str, max_turns: int) -> int:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for turn in range(max_turns):
        log(f"[turn]   {turn + 1}/{max_turns}")

        response = chat_with_retry(
            client,
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        # Accumulate the assistant turn
        messages.append(assistant_msg.model_dump(exclude_none=True))

        if choice.finish_reason == "stop" or not assistant_msg.tool_calls:
            print(assistant_msg.content or "")
            return 0

        # Execute each tool call
        for tc in assistant_msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                args = {}
                log(f"[warn]   could not parse tool arguments: {e}")

            log_tool_call(name, args)
            result = dispatch_tool(cwd, name, args)
            log_result(result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    log(f"[warn]   max turns ({max_turns}) reached without a final answer")
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal coding agent.")
    parser.add_argument("task", nargs="?", help="Task to perform (or supply via stdin).")
    parser.add_argument("--model", default="gpt-4o", help="Model name (default: gpt-4o).")
    parser.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible endpoint base URL.")
    parser.add_argument("--api-key", default=None, help="API key (default: $OPENAI_API_KEY).")
    parser.add_argument("--max-turns", type=int, default=100, help="Maximum agentic turns.")
    parser.add_argument("--cwd", default=".", help="Working directory for tools (default: current dir).")
    args = parser.parse_args()

    task = args.task
    if not task:
        if sys.stdin.isatty():
            parser.error("provide a task as a positional argument or via stdin")
        task = sys.stdin.read().strip()
    if not task:
        parser.error("task must not be empty")

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY", "no-key")
    
    cwd = os.path.abspath(args.cwd)

    client = OpenAI(api_key=api_key, base_url=args.base_url)

    sys.exit(run_agent(client, args.model, cwd, task, args.max_turns))


if __name__ == "__main__":
    main()
