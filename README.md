# SkySail

A self-bootstrapping agent runtime in one readable Python file.

SkySail starts as a small `agent.py`: it can inspect files, write files, run shell commands, communicate with a model, and gradually improve itself.

The goal is not to build another large agent framework.
The goal is to make the core mechanics of a tool-using agent visible, portable, and easy to modify.

## Why SkySail

Most agent projects quickly grow into complex frameworks:

* many directories
* many dependencies
* hidden runtime behavior
* provider-specific abstractions
* hard-to-follow control flow

SkySail takes the opposite path:

* one readable Python file
* minimal dependencies
* explicit agent loop
* small internal protocol
* provider-neutral runtime design
* simple tool system
* easy to copy, inspect, and change

SkySail is designed to be a small agent kernel that can grow through self-bootstrapping.

## Current Status

SkySail is early.

The first version focuses on the minimum useful agent loop:

```text
user task
   ↓
model response
   ↓
visible text + tool calls
   ↓
tool execution
   ↓
tool results
   ↓
next model response
   ↓
repeat until final
```

## Features

Current version:

* single-file `agent.py`
* minimal tool set
* model interface abstraction
* text-frame tool-call protocol
* ordered tool calls
* workspace path safety
* shell command guardrails
* basic output truncation
* verbose JSONL trace logging
* raw model message preservation in conversation history
* no framework dependency

Initial tools:

| Tool    | Purpose                                              |
| ------- | ---------------------------------------------------- |
| `ls`    | List files in the workspace                          |
| `read`  | Read a text file, with optional `offset` and `limit` |
| `write` | Write a full file                                    |
| `sh`    | Run a shell command                                  |

Advanced editing tools such as patching, diff review, search, session replay, and context compaction are intentionally left for later versions.

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-name>/SkySail.git
cd SkySail
```

SkySail currently uses only the Python standard library.

Python 3.10+ is recommended.

## Configuration

SkySail expects a chat-completions-compatible endpoint.

Set the following environment variables:

```bash
export API_KEY="your-api-key"
export BASE_URL="https://your-provider.example/v1"
export MODEL="your-model"
```

Optional settings:

```bash
export MAX_STEPS=15
export MAX_TOOL_CALLS=5
export MAX_OUTPUT_CHARS=20000
```

Verbose trace logging:

```bash
export VERBOSE=1
export TRACE_DIR=".skysail/runs"
```

You can also write a single trace file explicitly:

```bash
export TRACE_FILE=".skysail/runs/debug.jsonl"
```

## Usage

Run a basic inspection task:

```bash
python agent.py "inspect this repository and explain how it works"
```

Run with verbose trace logging:

```bash
VERBOSE=1 python agent.py "inspect this repository and explain how it works"
```

Run a self-bootstrapping task:

```bash
python agent.py "read agent.py and suggest one small improvement. If it is safe, implement it and run a syntax check."
```

Ask it to make a small repository change:

```bash
python agent.py "add a short project summary to README.md"
```

If you use a `.env` file:

```bash
set -a; source .env; set +a; python agent.py "inspect this repo"
```

With verbose logs:

```bash
set -a; source .env; set +a; VERBOSE=1 python agent.py "inspect this repo"
```

## Trace Logs

When `VERBOSE=1` is enabled, SkySail writes JSONL trace logs under `.skysail/runs/` by default.

A trace records runtime events such as:

* `run_start`
* `step_start`
* `model_raw`
* `model_parsed`
* `tool_call`
* `tool_result`
* `runtime_error`
* `run_final`

Example:

```json
{"type":"model_raw","step":1,"raw":"Let me inspect the repository.\n\n§AGENT {\"tool_calls\":[{\"name\":\"ls\",\"input\":{\"path\":\".\",\"max_depth\":2}}]}"}
```

This is useful for debugging model protocol issues, parser errors, tool call mistakes, and self-bootstrapping behavior.

## Design

SkySail is organized as logical sections inside one file:

```text
agent.py
├── Types
├── Config
├── Utilities
├── Tools
├── Text-frame model adapter
├── Agent runtime
└── CLI
```

The internal runtime is intentionally provider-neutral.

The core types are:

| Type            | Meaning                                           |
| --------------- | ------------------------------------------------- |
| `ChatMessage`   | A plain message in the conversation history       |
| `ParamSpec`     | A lightweight description of one tool parameter   |
| `ToolSpec`      | Public description of a tool exposed to the model |
| `Tool`          | Runtime representation of an executable tool      |
| `ToolCall`      | A tool call requested by the model                |
| `ToolResult`    | The result of executing one tool call             |
| `ModelResponse` | Normalized model output                           |
| `Model`         | Interface implemented by model adapters           |

The agent runtime only depends on this normalized protocol:

```text
messages + tools
     ↓
model.respond(...)
     ↓
ModelResponse(text, tool_calls, is_final)
     ↓
execute ToolCall(s)
     ↓
append ToolResult(s)
     ↓
repeat
```

Provider-specific details should stay inside model adapters.

## Text-frame Protocol

The first model adapter does not rely on native tool calling.

Instead, the model writes normal visible text, then appends one machine-readable control frame as the final non-empty line.

Example tool call:

```text
I will inspect the repository first.

§AGENT {"tool_calls":[{"name":"ls","input":{"path":".","max_depth":2}}]}
```

Example final response:

```text
The repository contains a single-file agent runtime with a minimal tool system and a provider-neutral model interface.

§AGENT {"final":true}
```

This design keeps natural language separate from machine-readable tool calls without forcing the entire assistant response into JSON.

The parser only reads the final non-empty line. It does not scan the full message body for tags.

SkySail also preserves the raw model message in conversation history. This helps the model see its previous control frames and makes the text-frame protocol more stable across steps.

## Tool Notes

### `read`

The `read` tool supports optional character-based pagination:

```json
{"path":"agent.py","offset":0,"limit":20000}
```

This allows the model to inspect large files without relying on full-file reads.

### `sh`

The `sh` tool runs shell commands in the workspace and includes a small blocklist for obviously destructive commands.

It is a guardrail, not a sandbox.

## Philosophy

SkySail is based on a few constraints:

### 1. Single-file first

The project should remain usable as one readable Python file for as long as possible.

### 2. Readable before powerful

The code should be easy to inspect, explain, and modify.

### 3. Runtime before framework

SkySail should expose the essential agent loop before adding framework-level abstractions.

### 4. Provider-neutral core

The runtime should not be tied to one model provider's tool-calling format.

### 5. Natural language plus tool calls

A model response should be able to contain useful visible communication and structured tool calls.

### 6. Self-bootstrapping

SkySail should be able to inspect and improve its own source code, with verification after changes.

## Changelog

### Unreleased

#### Added

* Added verbose JSONL trace logging with `VERBOSE`, `TRACE_DIR`, and `TRACE_FILE`.
* Added trace events for model raw output, parsed responses, tool calls, tool results, runtime errors, and final output.
* Added raw model message preservation in conversation history to make the text-frame protocol more stable.
* Added optional `offset` and `limit` support to the `read` tool for inspecting large files.

#### Changed

* Updated runtime history handling to store the raw assistant message instead of only visible text.
* Updated documentation to include trace logging and paginated file reads.

## Roadmap

### v0.1

* single-file runtime
* minimal tool set: `ls`, `read`, `write`, `sh`
* model interface
* text-frame model adapter
* basic agent loop
* verbose trace logging
* raw message history
* `read` offset/limit support

### v0.2

* safer write flow
* basic self-test command
* better parse-error recovery
* cleaner handling of ignored and secret files

### v0.3

* patch/edit tool
* git diff review
* improved shell permissions
* resume previous run

### v0.4

* native tool-calling adapters
* provider-specific message conversion
* better tool schema generation

### v0.5

* context compaction
* trace replay
* small evaluation runner
* permission policy

## Safety Notes

SkySail can read files, write files, and run shell commands in the current workspace.

The first version includes basic guardrails, but it is not a sandbox.

Use it in a disposable repository or a clean working tree when testing self-modification.

Recommended:

```bash
git status
git add .
git commit -m "checkpoint before SkySail run"
```

Then run SkySail.

Do not commit secrets. A typical `.gitignore` should include:

```gitignore
.env
.env.*
!.env.example
.skysail/runs/
```

## License

MIT
