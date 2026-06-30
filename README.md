# SkySail

A self-bootstrapping agent runtime in one readable Python file.

SkySail starts as a small `agent.py`: it can inspect files, write files, run shell commands, communicate with a model, ask the user for direction, and gradually improve itself.

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
* multi-turn session loop
* human-in-the-loop collaboration
* easy to copy, inspect, and change

SkySail is designed to be a small agent kernel that can grow through self-bootstrapping.

## Current Status

SkySail is early.

The current version focuses on a minimal but useful multi-turn agent runtime:

```text
user input
   ↓
agent session
   ↓
model response
   ↓
tool calls or normal assistant reply
   ↓
execute tools or yield to user
   ↓
repeat
```

The agent can now inspect code, call tools, ask structured questions, yield to the user, receive another user message, and continue with the same conversation history.

## Features

Current version:

* single-file `agent.py`
* minimal tool set
* model interface abstraction
* text-frame fallback model adapter
* ordered tool calls
* multi-turn session loop
* `Agent` owns conversation history
* structured `question` tool for human-in-the-loop choices
* normal assistant replies yield control back to the user
* workspace path safety
* shell command guardrails
* basic output truncation
* verbose JSONL trace logging
* raw model message preservation in conversation history
* no framework dependency

Initial tools:

| Tool       | Purpose                                              |
| ---------- | ---------------------------------------------------- |
| `ls`       | List files in the workspace                          |
| `read`     | Read a text file, with optional `offset` and `limit` |
| `question` | Ask the user a structured question                   |
| `write`    | Write a full file                                    |
| `sh`       | Run a shell command                                  |

Advanced editing tools such as patching, diff review, session replay, context compaction, native tool-calling adapters, and permission policy are intentionally left for later versions.

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-name>/SkySail.git
cd SkySail
```

SkySail currently uses only the Python standard library.

Python 3.10+ is recommended.

## Configuration

SkySail currently expects a chat-completions-compatible endpoint.

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

Ask it to discuss a larger change before acting:

```bash
python agent.py "help me redesign this agent, but confirm the plan with me first"
```

SkySail now keeps a multi-turn CLI session.

After the assistant yields control, continue typing:

```text
> I prefer the smaller version. Keep it single-file.
```

Exit with:

```text
Ctrl+C
```

or:

```text
exit
quit
:q
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
* `user_input`
* `run_yield`
* `runtime_error`

Example:

```json
{"type":"model_raw","step":1,"raw":"Let me inspect the repository.\n\n§AGENT {\"tool_calls\":[{\"name\":\"ls\",\"input\":{\"path\":\".\",\"max_depth\":2}}]}"}
```

This is useful for debugging model protocol issues, parser errors, tool call mistakes, conversation pauses, and self-bootstrapping behavior.

## Design

SkySail is organized as logical sections inside one file:

```text
agent.py
├── Types
├── Errors
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
Agent session messages
     ↓
model.respond(...)
     ↓
ModelResponse(text, tool_calls, raw)
     ↓
if tool_calls: execute tools and continue
     ↓
if no tool_calls: yield to user
```

Provider-specific details should stay inside model adapters.

## Agent Session Model

SkySail now treats `Agent` as a session object.

The `Agent` owns the conversation history.

Conceptually:

```text
Agent.start(task)
  add first user message
  run until the model stops asking for tools

Agent.send(user_input)
  add next user message
  run until the model stops asking for tools

Agent.run_until_yield()
  execute the automatic tool loop
  yield when there are no more tool calls
```

The CLI does not own the message history.

The CLI only reads user input, sends it to the agent, prints the assistant response, and repeats.

This design prepares the runtime for future session persistence and resume.

## Runtime Rule

SkySail’s runtime rule is deliberately small:

```text
tool calls present  → execute tools and continue
tool calls absent   → yield control to the user
```

There is no separate `final` protocol state.

There is no separate `await_user` protocol state.

A normal assistant reply may mean:

```text
The task is complete.
```

or:

```text
I need your decision before continuing.
```

The runtime does not need to distinguish those meanings.

The user can always continue the conversation.

## Text-frame Adapter

The current model adapter is `TextFrameModel`.

It does not rely on native tool calling.

Instead, the model writes normal visible text, then appends one machine-readable tool-call frame as the final non-empty line.

Example:

```text
I will inspect the repository first.

§AGENT {"tool_calls":[{"name":"ls","input":{"path":".","max_depth":2}}]}
```

If the model does not need tools, it simply replies in normal natural language without a control frame:

```text
I found three possible directions:

1. Add session resume
2. Improve CLI display
3. Add safer editing

I recommend starting with session resume because longer tasks are already hitting step limits.

Which direction do you want me to take?
```

A normal reply means:

```text
no tool calls
→ yield control to the user
```

The parser only reads the final non-empty line when a tool-call control frame is present. It does not scan the full message body for tags.

SkySail also preserves the raw model message in conversation history. This helps the model see its previous control frames and makes the text-frame fallback more stable across steps.

## Native Tool Calling Direction

The text-frame adapter is useful for bootstrapping, but it should not be the long-term default.

Most modern model APIs support native tool use.

A future version should add an OpenAI-style native tool-calling adapter and make it the default model path.

The intended direction:

```text
OpenAI-style native tool calling
  default adapter

TextFrameModel
  temporary fallback or removed later

Anthropic tool-use adapter
  added later if needed
```

The internal runtime should remain the same.

Only the model adapter should change.

The adapter’s job is to normalize provider-specific output into:

```text
ModelResponse(text, tool_calls, raw)
```

This keeps the core runtime provider-neutral while avoiding fragile text parsing when native tool calls are available.

## Tool Notes

### `read`

The `read` tool supports optional character-based pagination:

```json
{"path":"agent.py","offset":0,"limit":20000}
```

This allows the model to inspect large files without relying on full-file reads.

### `question`

The `question` tool lets the model ask the user a short structured question.

Example:

```json
{
  "title": "Choose scope",
  "question": "How large should this change be?",
  "options": ["minimal", "moderate", "large"],
  "allow_free_text": true
}
```

The `question` tool is useful for explicit choices.

For longer design proposals or open-ended discussion, the model should use a normal assistant reply without tool calls.

### `sh`

The `sh` tool runs shell commands in the workspace and includes a small blocklist for obviously destructive commands.

It is a guardrail, not a sandbox.

## Known Limitations

SkySail currently keeps session state in memory.

If the process exits, the session is lost.

For larger tasks, the agent may stop before completing all work if it reaches `MAX_STEPS`.

You can raise the step limit:

```bash
MAX_STEPS=30 python agent.py "continue the previous task"
```

But this is only a temporary workaround.

A future version should support session persistence and resume so that long-running work can be paused, inspected, and continued safely.

The CLI output is also still rough. It is useful for debugging, but tool calls and long-running steps need a clearer display.

Long sessions may also become slower because every model call receives the growing conversation history. Future versions should consider provider cache support, context compaction, and better long-session memory management.

## Philosophy

SkySail is based on a few constraints.

### 1. Single-file first

The project should remain usable as one readable Python file for as long as possible.

### 2. Readable before powerful

The code should be easy to inspect, explain, and modify.

### 3. Runtime before framework

SkySail should expose the essential agent loop before adding framework-level abstractions.

### 4. Provider-neutral core

The runtime should not be tied to one model provider's tool-calling format.

### 5. Tool calls, not protocol states

The runtime should stay centered on one question:

```text
Did the model request tools?
```

If yes, execute tools.

If no, yield control to the user.

### 6. Human-in-the-loop collaboration

The agent should be able to ask questions, propose plans, wait for feedback, and continue based on the user's answer.

### 7. Self-bootstrapping

SkySail should be able to inspect and improve its own source code, with verification after changes.

## Changelog

### Unreleased

#### Added

* Added verbose JSONL trace logging with `VERBOSE`, `TRACE_DIR`, and `TRACE_FILE`.
* Added trace events for model raw output, parsed responses, tool calls, tool results, runtime errors, user input, and yield points.
* Added raw model message preservation in conversation history.
* Added optional `offset` and `limit` support to the `read` tool for inspecting large files.
* Added `question` tool for short structured human-in-the-loop choices.
* Added multi-turn CLI session loop.
* Added `Agent.start(...)`, `Agent.send(...)`, and `Agent.run_until_yield(...)`.
* Moved conversation history ownership into `Agent`.

#### Changed

* Simplified runtime semantics around tool calls.
* Removed `final` as a first-class protocol state.
* Removed `await_user` as a first-class protocol state.
* Treat model responses without tool calls as normal assistant replies that yield control to the user.
* Updated the system prompt to describe only tool-call control frames and normal replies.
* Updated documentation to include the session model, multi-turn behavior, long-session concerns, and native tool-calling direction.

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

### Day 1 / v1

* structured `question` tool
* conversation through normal assistant replies
* multi-turn session loop
* `Agent` owns message history
* simplified runtime semantics around tool calls
* no `final` / `await_user` protocol states
* normal replies yield control back to the user

### v1.1

* better CLI display
* visible progress / process peek
* improved tool call formatting
* compact and verbose output modes
* clearer step-limit summaries

### v1.2

* session persistence
* resume previous session
* trace-to-session linkage
* unfinished work summary
* fault recovery for long-running tasks

### v1.3

* OpenAI-style native tool-calling adapter as the default path
* convert `ToolSpec` to provider-native tool schema
* normalize provider-native tool calls into `ToolCall`
* reduce reliance on text-frame parsing

### v1.4

* context compaction
* provider cache support
* long-session performance improvements
* repeated-read avoidance

### v1.5

* safer write flow
* patch/edit tool
* git diff review
* basic self-test command

### Later

* Anthropic tool-use adapter
* trace replay
* small evaluation runner
* permission policy
* MCP-style tool integration

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
