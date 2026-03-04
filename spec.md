# Minimal Coding Agent — Specification

## Overview

A minimal command-line coding agent that accepts a task from the user, reasons about it using an OpenAI-compatible chat completions API, and executes tool calls in a loop until the task is complete or the agent decides to stop.

---

## Goals

- Simple, readable implementation — the code itself is a reference for how an agent loop works.
- No framework dependencies; use only the OpenAI client library and standard library tools.
- Portable: works with OpenAI, Anthropic (via compatibility shim), Ollama, vLLM, or any other OpenAI-compatible endpoint.

---

## Invocation

```
agent [OPTIONS] "<task>"
```

| Flag | Default | Description |
|---|---|---|
| `--model` | `gpt-4o` | Model name to pass to the API |
| `--base-url` | `https://api.openai.com/v1` | Base URL of the OpenAI-compatible endpoint |
| `--api-key` | `$OPENAI_API_KEY` | API key (falls back to env var) |
| `--max-turns` | `20` | Maximum agentic turns before aborting |
| `--cwd` | `.` | Working directory for file and shell tools |

The task may also be supplied via stdin if no positional argument is given.

---

## Agent Loop

```
1. Build initial message list:
     system prompt  +  user task

2. LOOP (up to --max-turns):
   a. Call chat completions API with current messages and tool definitions.
   b. Append the assistant message to the conversation.
   c. If finish_reason == "stop" (no tool calls) → print final response and exit 0.
   d. For each tool_call in the response:
        i.  Execute the tool locally.
        ii. Append a tool result message.
   e. Continue loop.

3. If max-turns reached → print warning and exit 1.
```

All messages (assistant turns and tool results) are accumulated in memory for the lifetime of the run; there is no persistence between invocations.

---

## System Prompt

```
You are a coding agent running on the user's machine.
You have access to tools to read and write files, run shell commands,
and search the codebase. Use them to complete the user's task.
Work incrementally: read before you write, run tests after changes.
When the task is done, summarise what you did.
```

---

## Tools

The agent exposes the following tools to the model via the `tools` parameter of the chat completions request.

### `read_file`

Read the contents of a file.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path relative to `--cwd` |
| `start_line` | integer | no | First line to return (1-based, default 1) |
| `end_line` | integer | no | Last line to return (inclusive, default EOF) |

Returns the file contents as a string. Errors (file not found, permission denied) are returned as a string beginning with `ERROR:` so the model can reason about them.

---

### `write_file`

Write or overwrite a file.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path relative to `--cwd` |
| `content` | string | yes | Full new content of the file |

Creates parent directories if they do not exist. Returns `"OK"` or an `ERROR:` string.

---

### `run_shell`

Run a shell command and capture output.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `command` | string | yes | Shell command to execute (`bash -c`) |
| `timeout` | integer | no | Max seconds to wait (default 30) |

Returns a JSON object: `{"stdout": "...", "stderr": "...", "exit_code": 0}`.

stdout and stderr are each capped at 10 000 characters; excess is replaced with a truncation notice.

---

### `list_files`

List files matching a glob pattern.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | string | yes | Glob pattern relative to `--cwd` (e.g. `**/*.py`) |

Returns a newline-separated list of matching paths, or an `ERROR:` string.

---

### `search_text`

Search file contents with a regular expression.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | string | yes | Regular expression |
| `glob` | string | no | Restrict search to files matching this glob |

Returns matching lines in `path:line_number: content` format, capped at 200 results.

---

## Output

- Tool calls and results are printed to **stderr** as structured log lines so the user can follow progress:
  ```
  [tool] run_shell: pytest tests/
  [result] exit_code=0, 42 passed
  ```
- The final assistant message (after `finish_reason == "stop"`) is printed to **stdout**.
- The agent exits `0` on success, `1` on max-turns exceeded or unrecoverable error.

---

## Error Handling

- API errors (non-2xx, rate limits, timeouts): retry up to 3 times with exponential back-off (1 s, 2 s, 4 s), then abort.
- Tool execution errors are returned to the model as tool result messages so it can decide how to proceed; they do not abort the loop.
- Malformed tool calls (missing required parameters, unknown tool name): return an `ERROR:` tool result without executing anything.

---

## Security Considerations

- `run_shell` executes arbitrary commands with the permissions of the user running the agent. No sandboxing is applied — this is intentional for a minimal implementation. Users should be aware of the risk.
- API keys are never logged.
- File paths are resolved relative to `--cwd`; no restriction on traversal (`../`) is enforced in the minimal implementation.

---

## Non-Goals

- Persistent memory or conversation history across invocations.
- Multi-agent orchestration.
- Streaming output of assistant tokens.
- Token budget management / context window truncation.
- IDE integration or LSP support.
