#!/usr/bin/env python3
"""
SkySail - a self-bootstrapping agent runtime in one readable Python file.

Usage:
  export API_KEY="your-api-key"
  export BASE_URL="https://your-provider.example/v1"
  export MODEL="your-model"
  python agent.py "inspect this repository and explain how it works"

Optional:
  MAX_STEPS=20 python agent.py "read agent.py and make one small improvement"
  MAX_TOOL_CALLS=5 python agent.py "inspect this repo"
  MAX_OUTPUT_CHARS=20000 python agent.py "summarize the main files"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import request
from urllib.error import HTTPError, URLError


# =============================================================================
# Types
# =============================================================================
#
# This section defines the small internal protocol used by the agent runtime.
#
# The agent loop does not talk directly in any provider's native format.
# Instead, every model adapter converts provider-specific output into these
# simple internal types:
#
#   ChatMessage
#     A plain message in the conversation history.
#
#   ToolSpec / ParamSpec
#     The tools exposed to the model.
#
#   ToolCall
#     A tool call requested by the model.
#
#   ToolResult
#     The runtime result after executing one ToolCall.
#
#   ModelResponse
#     The normalized output from one model response:
#       - visible text
#       - ordered tool calls
#
# The core loop only depends on these types:
#
#   messages + tools
#        ↓
#   model.respond(...)
#        ↓
#   ModelResponse(text, tool_calls)
#        ↓
#   execute ToolCall(s)
#        ↓
#   append ToolResult(s) back into messages
#
# Provider-specific details should stay inside model adapters unless the core
# runtime truly needs them.


@dataclass
class ChatMessage:
    """
    A plain normalized message in the agent conversation history.

    For v1, keep this deliberately simple:
    - role: system / user / assistant
    - content: message text

    Tool call identity is represented by ToolCall and ToolResult below,
    not by ChatMessage.
    """

    role: str
    content: str


@dataclass
class ParamSpec:
    """
    A lightweight parameter description for a tool.

    This is not full JSON Schema.
    It is a simple, ordered, human-readable parameter list.
    """

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolSpec:
    """
    Public description of a tool exposed to the model.

    params is a list rather than a dict, so the intended parameter order
    is readable and stable.
    """

    name: str
    description: str
    params: list[ParamSpec] = field(default_factory=list)


@dataclass
class Tool:
    """
    Runtime representation of a tool.

    spec:
      What the model sees.

    run:
      The Python function the runtime executes.
    """

    spec: ToolSpec
    run: Callable[..., str]


@dataclass
class ToolCall:
    """
    A normalized tool call requested by the model.

    id:
      Runtime-assigned stable id, used to match ToolResult.

    index:
      The order of this tool call inside the current ModelResponse.

    name:
      Tool name, such as ls/read/write/sh.

    input:
      Named input object for the tool call.
    """

    id: str
    index: int
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """
    Result of executing one ToolCall.

    id and index mirror the original ToolCall, so the model and trace logs
    can map every result back to the corresponding call.
    """

    id: str
    index: int
    name: str
    ok: bool
    output: str


@dataclass
class ModelResponse:
    """
    Normalized output from one model response.

    text:
      Human-visible assistant text.

    tool_calls:
      Ordered list of tool calls requested by the model.

    raw:
      Original provider message content before parsing.
      Useful for debugging and trace replay.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: str = ""


class Model(Protocol):
    """
    Interface implemented by all model adapters.

    The agent runtime should only call this interface.
    """

    def respond(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> ModelResponse:
        ...

# =============================================================================
# Errors
# =============================================================================

class ModelParseError(ValueError):
    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw

# =============================================================================
# Config
# =============================================================================

WORKDIR = Path.cwd().resolve()

MODEL_NAME = os.getenv("MODEL", "")
API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "")

MAX_STEPS = int(os.getenv("MAX_STEPS", "15"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "5"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "20000"))

CONTROL_PREFIX = "§AGENT "

VERBOSE = os.getenv("VERBOSE", "0").lower() in {"1", "true", "yes", "on"}
TRACE_DIR = Path(os.getenv("TRACE_DIR", ".skysail/runs"))
TRACE_FILE = os.getenv("TRACE_FILE", "")

# =============================================================================
# Utilities
# =============================================================================

def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated]"


def safe_path(path: str) -> Path:
    target = (WORKDIR / path).resolve()
    try:
        target.relative_to(WORKDIR)
    except ValueError:
        raise ValueError(f"path escapes workspace: {path}")
    return target


def one_line(text: str, limit: int = 160) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    first = stripped.splitlines()[0]
    if len(first) > limit:
        return first[:limit] + "..."
    return first

class TraceLogger:
    def __init__(self, enabled: bool, trace_file: str = "") -> None:
        self.enabled = enabled
        self.path: Path | None = None

        if not enabled and not trace_file:
            return

        if trace_file:
            self.path = Path(trace_file)
        else:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self.path = TRACE_DIR / f"{timestamp}.jsonl"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[trace] writing {self.path}", file=sys.stderr)

    def event(self, event_type: str, **data: Any) -> None:
        if self.path is None:
            return

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **data,
        }

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

# =============================================================================
# Tools
# =============================================================================

def tool_ls(path: str = ".", max_depth: int = 2) -> str:
    root = safe_path(path)
    max_depth = int(max_depth)

    if not root.exists():
        return f"Path not found: {path}"

    if root.is_file():
        return str(root.relative_to(WORKDIR))

    ignored = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }

    lines: list[str] = []

    for item in sorted(root.rglob("*")):
        rel_to_root = item.relative_to(root)
        parts = rel_to_root.parts

        if any(part in ignored for part in parts):
            continue

        if len(parts) > max_depth:
            continue

        rel = item.relative_to(WORKDIR)
        suffix = "/" if item.is_dir() else ""
        lines.append(f"{rel}{suffix}")

        if len(lines) >= 500:
            lines.append("[truncated]")
            break

    return "\n".join(lines) or "(empty)"


def tool_read(path: str, offset: int = 0, limit: int = MAX_OUTPUT_CHARS) -> str:
    target = safe_path(path)

    if not target.exists():
        return f"File not found: {path}"

    if not target.is_file():
        return f"Not a file: {path}"

    text = target.read_text(errors="replace")
    offset = max(0, int(offset))
    limit = max(1, int(limit))

    chunk = text[offset:offset + limit]
    end = offset + len(chunk)

    suffix = ""
    if end < len(text):
        suffix = f"\n\n[truncated: showing chars {offset}-{end} of {len(text)}]"

    return chunk + suffix


def tool_write(path: str, content: str) -> str:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {path} ({len(content)} bytes)"


def tool_sh(cmd: str) -> str:
    lowered = cmd.lower()

    banned = [
        "rm -rf",
        "sudo ",
        "shutdown",
        "reboot",
        "mkfs",
        ":(){",
        "dd if=",
        "> /dev/",
        "chmod -r 777",
        "chown -r",
    ]

    if any(pattern in lowered for pattern in banned):
        return f"Blocked unsafe command: {cmd}"

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=WORKDIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        output = proc.stdout or ""
        return truncate(f"exit_code={proc.returncode}\n{output}")
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"


def tool_question(
    title: str,
    question: str,
    options: list[str] | None = None,
    allow_free_text: bool = True,
) -> str:
    """
    Ask the user for clarification, preference, or a decision.

    This is an intent-level human-in-the-loop tool.

    It is different from permission approval:
    - question: the model asks the user to clarify intent or choose a direction
    - permission: the runtime decides whether a concrete tool call is allowed

    The result is returned as a JSON string so the model can parse it reliably.
    """

    title = str(title).strip() or "Question"
    question = str(question).strip()

    if not question:
        return json.dumps(
            {
                "ok": False,
                "error": "question must not be empty",
            },
            ensure_ascii=False,
        )

    normalized_options: list[str] = []

    if options is None:
        normalized_options = []
    elif isinstance(options, list):
        normalized_options = [
            str(option).strip()
            for option in options
            if str(option).strip()
        ]
    else:
        text = str(options).strip()
        if text:
            normalized_options = [text]

    if isinstance(allow_free_text, str):
        allow_free_text = allow_free_text.lower() in {"1", "true", "yes", "on"}
    else:
        allow_free_text = bool(allow_free_text)

    print("", file=sys.stderr)
    print(f"? {title}", file=sys.stderr)
    print(question, file=sys.stderr)

    if normalized_options:
        print("", file=sys.stderr)
        for index, option in enumerate(normalized_options, start=1):
            print(f"{index}. {option}", file=sys.stderr)

    if normalized_options and allow_free_text:
        prompt = "> choose a number or type your answer: "
    elif normalized_options:
        prompt = f"> choose 1-{len(normalized_options)}: "
    else:
        prompt = "> "

    while True:
        print(prompt, end="", file=sys.stderr, flush=True)

        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            raise

        if line == "":
            return json.dumps(
                {
                    "ok": False,
                    "error": "user input unavailable: EOF",
                },
                ensure_ascii=False,
            )

        answer = line.strip()

        if not answer:
            print("Please enter a response.", file=sys.stderr)
            continue

        if normalized_options:
            if answer.isdigit():
                selected_number = int(answer)
                if 1 <= selected_number <= len(normalized_options):
                    selected_index = selected_number - 1
                    return json.dumps(
                        {
                            "ok": True,
                            "answer": normalized_options[selected_index],
                            "selected_index": selected_index,
                            "free_text": False,
                        },
                        ensure_ascii=False,
                    )

            if answer in normalized_options:
                return json.dumps(
                    {
                        "ok": True,
                        "answer": answer,
                        "selected_index": normalized_options.index(answer),
                        "free_text": False,
                    },
                    ensure_ascii=False,
                )

            if not allow_free_text:
                print("Please choose one of the listed options.", file=sys.stderr)
                continue

        return json.dumps(
            {
                "ok": True,
                "answer": answer,
                "selected_index": None,
                "free_text": True,
            },
            ensure_ascii=False,
        )

def build_tools() -> dict[str, Tool]:
    tools = [
        Tool(
            spec=ToolSpec(
                name="ls",
                description="List files under a workspace-relative path.",
                params=[
                    ParamSpec("path", "string", "Workspace-relative path to list.", default="."),
                    ParamSpec("max_depth", "integer", "Maximum directory depth to include.", default=2),
                ],
            ),
            run=tool_ls,
        ),
        Tool(
            spec=ToolSpec(
                name="read",
                description="Read a UTF-8 text file from the workspace. Supports optional character offset and limit.",
                params=[
                    ParamSpec("path", "string", "Workspace-relative file path to read."),
                    ParamSpec("offset", "integer", "Character offset to start reading from.", required=False, default=0),
                    ParamSpec("limit", "integer", "Maximum characters to return.", required=False, default=MAX_OUTPUT_CHARS),
                ],
            ),
            run=tool_read,
        ),
        Tool(
            spec=ToolSpec(
                name="question",
                description=(
                    "Ask the user for clarification, preferences, or a decision "
                    "before continuing. Use this before non-trivial work when "
                    "the user's intent is unclear, when there are multiple "
                    "reasonable options, or before starting a larger change. "
                    "The question tool must be the only tool call in the response."
                ),
                params=[
                    ParamSpec(
                        "title",
                        "string",
                        "Short title for the question.",
                    ),
                    ParamSpec(
                        "question",
                        "string",
                        "The question to ask the user.",
                    ),
                    ParamSpec(
                        "options",
                        "array[string]",
                        "Optional list of choices for the user.",
                        required=False,
                        default=[],
                    ),
                    ParamSpec(
                        "allow_free_text",
                        "boolean",
                        "Whether the user can type a custom answer.",
                        required=False,
                        default=True,
                    ),
                ],
            ),
            run=tool_question,
        ),
        Tool(
            spec=ToolSpec(
                name="write",
                description="Write full content to a workspace-relative file.",
                params=[
                    ParamSpec("path", "string", "Workspace-relative file path to write."),
                    ParamSpec("content", "string", "Full file content to write."),
                ],
            ),
            run=tool_write,
        ),
        Tool(
            spec=ToolSpec(
                name="sh",
                description="Run a shell command in the workspace.",
                params=[
                    ParamSpec("cmd", "string", "Shell command to run."),
                ],
            ),
            run=tool_sh,
        ),
    ]

    return {tool.spec.name: tool for tool in tools}


# =============================================================================
# Text-frame model adapter
# =============================================================================
#
# This model adapter uses a chat-completions-compatible HTTP endpoint.
#
# It does not rely on native tool-calling. Instead, the model writes normal
# visible text and may append one machine-readable control frame as the final
# non-empty line when it wants to call tools:
#
#   I will inspect the repository first.
#
#   §AGENT {"tool_calls":[{"name":"ls","input":{"path":".","max_depth":2}}]}
#
# If the model does not append a control frame, the response is treated as a
# normal assistant reply. The runtime then yields control back to the user.
#
# This fallback protocol simulates the same separation used by native
# tool-calling APIs: human-visible text is separate from machine-readable tool
# calls. The parser only looks at the final non-empty line, never scans the
# whole message body.


class TextFrameModel:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._next_call_id = 1

    def respond(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> ModelResponse:
        raw = self._chat(messages, tools)
        try:
            return self._parse(raw)
        except Exception as e:
            raise ModelParseError(str(e), raw) from e

    def _chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> str:
        if not self.api_key:
            die("API_KEY is not set")

        if not self.base_url:
            die("BASE_URL is not set")

        if not self.model:
            die("MODEL is not set")

        provider_messages = [
            {
                "role": "system",
                "content": self._system_prompt(tools),
            }
        ]

        for msg in messages:
            provider_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        payload = {
            "model": self.model,
            "messages": provider_messages,
            "temperature": 0,
        }

        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"model call failed: HTTP {e.code}: {body}") from e
        except URLError as e:
            raise RuntimeError(f"model call failed: {e}") from e
        except KeyError as e:
            raise RuntimeError(f"unexpected model response shape: missing {e}") from e

    def _system_prompt(self, tools: list[ToolSpec]) -> str:
        return f"""You are SkySail, a small tool-using agent running inside a local workspace.

You can communicate with the user in natural language. Keep visible messages brief and useful:
- say what you are doing
- summarize observations
- explain changes
- mention verification results
- ask questions when you need the user's decision
Do not expose hidden chain-of-thought.

SkySail has one machine-readable control frame: tool_calls.

Use a control frame only when you want the runtime to execute tools.
Append exactly one control frame as the final non-empty line:

{CONTROL_PREFIX}{{"tool_calls":[{{"name":"tool_name","input":{{"key":"value"}}}}]}}

If you do not need to call tools, reply in normal natural language without a control frame.
A normal reply returns control to the user and ends the current automatic loop.

Rules:
- Use a control frame only when requesting tool execution.
- If you are asking the user a question, proposing options, reporting results, or waiting for feedback, do not use a control frame.
- Do not claim that you will use tools unless you include a valid tool_calls control frame.
- The control frame, when used, must be the final non-empty line.
- Do not put the control frame in Markdown or code fences.
- Do not put extra text after the control frame.
- tool_calls is an ordered list.
- The runtime executes tool_calls from left to right.
- You may batch independent tool calls.
- Do not batch calls where a later call depends on an earlier result.
- Use the question tool only for short structured questions with explicit options.
- The question tool must be the only tool call in that response.
- Do not batch question with file writes, shell commands, or other tools.
- After receiving a question result, continue based on the user's answer.
- Prefer reading files before writing files.
- Use write only when you are confident.
- After modifying files, run a relevant check with sh if possible.
- Do not use destructive commands.

Examples:

Tool call:

I will inspect the repository first.

{CONTROL_PREFIX}{{"tool_calls":[{{"name":"ls","input":{{"path":".","max_depth":2}}}}]}}

Normal reply:

I found three possible directions:

1. Add session resume
2. Improve CLI display
3. Add safer editing

I recommend starting with session resume because longer tasks are already hitting step limits.

Which direction do you want me to take?

Available tools:

{self._format_tools(tools)}
"""

    def _format_tools(self, tools: list[ToolSpec]) -> str:
        blocks: list[str] = []

        for tool in tools:
            lines = [f"- {tool.name}: {tool.description}"]

            if tool.params:
                lines.append("  params:")
                for param in tool.params:
                    required = "required" if param.required else "optional"
                    default = "" if param.default is None else f", default={param.default!r}"
                    lines.append(
                        f"    - {param.name}: {param.type}, {required}{default}. "
                        f"{param.description}"
                    )

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def _parse(self, raw: str) -> ModelResponse:
        text = raw.rstrip()

        if not text:
            raise ValueError("empty model response")

        lines = text.splitlines()
        last = lines[-1].strip()

        if not last.startswith(CONTROL_PREFIX):
            return ModelResponse(text=text, raw=raw)

        visible = "\n".join(lines[:-1]).strip()
        frame_text = last[len(CONTROL_PREFIX):].strip()

        try:
            frame = json.loads(frame_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid control frame JSON: {e}") from e

        if not isinstance(frame, dict):
            raise ValueError("control frame must be a JSON object")

        if set(frame.keys()) != {"tool_calls"}:
            raise ValueError("control frame must contain only tool_calls")

        raw_calls = frame["tool_calls"]

        if not isinstance(raw_calls, list):
            raise ValueError("tool_calls must be a list")

        if not raw_calls:
            raise ValueError("tool_calls must not be empty")

        if len(raw_calls) > MAX_TOOL_CALLS:
            raise ValueError(f"too many tool calls; max is {MAX_TOOL_CALLS}")

        calls: list[ToolCall] = []

        for index, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, dict):
                raise ValueError(f"tool call at index {index} must be an object")

            name = raw_call.get("name")
            input_obj = raw_call.get("input", {})

            if not isinstance(name, str) or not name:
                raise ValueError(f"tool call at index {index} has invalid name")

            if not isinstance(input_obj, dict):
                raise ValueError(f"tool call at index {index} input must be an object")

            call_id = f"call_{self._next_call_id}"
            self._next_call_id += 1

            calls.append(
                ToolCall(
                    id=call_id,
                    index=index,
                    name=name,
                    input=input_obj,
                )
            )

        return ModelResponse(text=visible, tool_calls=calls, raw=raw)


# =============================================================================
# Agent runtime
# =============================================================================

class Agent:
    """
    A stateful agent session.

    The Agent owns the conversation history. The CLI only feeds user input into
    the Agent and prints the assistant's yielded replies.

    The inner runtime loop runs until the model stops requesting tools. At that
    point, control is yielded back to the user. The same Agent instance can then
    continue from the same message history when the user sends another message.
    """

    def __init__(
        self,
        model: Model,
        tools: dict[str, Tool],
        max_steps: int,
        logger: TraceLogger,
    ) -> None:
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        self.logger = logger
        self.messages: list[ChatMessage] = []
        self.turn = 0

    def start(self, task: str) -> str:
        """Start a new session with the first user task."""
        self.messages = []
        self.turn = 0

        self.logger.event(
            "session_start",
            task=task,
            workdir=str(WORKDIR),
            model=getattr(self.model, "model", ""),
            max_steps=self.max_steps,
            tools=list(self.tools.keys()),
        )

        return self.send(task)

    def send(self, user_input: str) -> str:
        """Append a user message and run the agent until it yields."""
        user_input = user_input.strip()

        if not user_input:
            return ""

        self.turn += 1
        self.messages.append(ChatMessage(role="user", content=user_input))

        self.logger.event(
            "user_input",
            turn=self.turn,
            input=user_input,
        )

        return self.run_until_yield()

    def run_until_yield(self) -> str:
        """
        Run the automatic tool loop until the model stops requesting tools.

        A normal assistant reply without tool calls yields control back to the
        user. Tool calls continue the loop after their results are appended to
        the conversation.
        """

        tool_specs = [tool.spec for tool in self.tools.values()]

        for step in range(1, self.max_steps + 1):
            self.logger.event(
                "step_start",
                turn=self.turn,
                step=step,
            )
            print(f"\n--- turn {self.turn} step {step}/{self.max_steps} ---", file=sys.stderr)

            try:
                response = self.model.respond(self.messages, tool_specs)
                self.logger.event(
                    "model_raw",
                    turn=self.turn,
                    step=step,
                    raw=response.raw,
                )
                self.logger.event(
                    "model_parsed",
                    turn=self.turn,
                    step=step,
                    text=response.text,
                    tool_calls=[
                        {
                            "id": call.id,
                            "index": call.index,
                            "name": call.name,
                            "input": call.input,
                        }
                        for call in response.tool_calls
                    ],
                )

            except Exception as e:
                raw = getattr(e, "raw", "")
                if raw:
                    self.logger.event(
                        "model_raw",
                        turn=self.turn,
                        step=step,
                        raw=raw,
                    )

                self.logger.event(
                    "runtime_error",
                    turn=self.turn,
                    step=step,
                    error=str(e),
                )

                error_message = (
                    "The previous model response could not be parsed or executed by the runtime.\n"
                    f"Runtime error: {e}\n\n"
                    "Respond again. If you need tools, use normal visible text and then put exactly one valid "
                    f"{CONTROL_PREFIX.strip()} tool_calls control frame as the final non-empty line. "
                    "If you do not need tools, reply normally without a control frame."
                )
                print(f"[runtime error] {e}", file=sys.stderr)
                self.messages.append(ChatMessage(role="user", content=error_message))
                continue

            if response.text:
                print(response.text, file=sys.stderr)

            self.messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.raw or response.text or "(assistant requested tool calls)",
                )
            )

            if not response.tool_calls:
                self.logger.event(
                    "run_yield",
                    turn=self.turn,
                    step=step,
                    output=response.text or "Done.",
                )
                return response.text or "Done."

            for call in response.tool_calls:
                self.logger.event(
                    "tool_call",
                    turn=self.turn,
                    step=step,
                    id=call.id,
                    index=call.index,
                    name=call.name,
                    input=call.input,
                )

            has_question = any(call.name == "question" for call in response.tool_calls)

            if has_question and len(response.tool_calls) != 1:
                results = [
                    ToolResult(
                        id=call.id,
                        index=call.index,
                        name=call.name,
                        ok=False,
                        output=(
                            "Invalid tool batch: question must be the only tool call "
                            "in a response. Ask the question first, wait for the user's "
                            "answer, then continue in the next step."
                        ),
                    )
                    for call in response.tool_calls
                ]
            else:
                results = [self._execute_tool_call(call) for call in response.tool_calls]

            for result in results:
                self.logger.event(
                    "tool_result",
                    turn=self.turn,
                    step=step,
                    id=result.id,
                    index=result.index,
                    name=result.name,
                    ok=result.ok,
                    output=result.output,
                )

            for result in results:
                status = "ok" if result.ok else "error"
                print(
                    f"[{status}] {result.name}#{result.index}: {one_line(result.output)}",
                    file=sys.stderr,
                )

            observation = {
                "tool_results": [
                    {
                        "id": result.id,
                        "index": result.index,
                        "name": result.name,
                        "ok": result.ok,
                        "output": result.output,
                    }
                    for result in results
                ]
            }

            self.messages.append(
                ChatMessage(
                    role="user",
                    content=json.dumps(observation, ensure_ascii=False, indent=2),
                )
            )

        message = f"Stopped after {self.max_steps} steps without yielding a normal reply."
        self.logger.event(
            "run_stopped",
            turn=self.turn,
            reason="max_steps",
            output=message,
        )
        return message

    def _execute_tool_call(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)

        if tool is None:
            return ToolResult(
                id=call.id,
                index=call.index,
                name=call.name,
                ok=False,
                output=f"Unknown tool: {call.name}",
            )

        try:
            output = tool.run(**call.input)
            return ToolResult(
                id=call.id,
                index=call.index,
                name=call.name,
                ok=True,
                output=output,
            )
        except TypeError as e:
            return ToolResult(
                id=call.id,
                index=call.index,
                name=call.name,
                ok=False,
                output=f"Bad tool input: {e}",
            )
        except Exception as e:
            return ToolResult(
                id=call.id,
                index=call.index,
                name=call.name,
                ok=False,
                output=f"Tool failed: {e}",
            )


# =============================================================================
# CLI
# =============================================================================

def read_prompt(prompt: str) -> str | None:
    try:
        return input(prompt).strip()
    except EOFError:
        return None


def main() -> None:
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:]).strip()
    else:
        task = read_prompt("Task: ")

    if task is None or not task:
        die("empty task")

    tools = build_tools()

    model = TextFrameModel(
        model=MODEL_NAME,
        api_key=API_KEY,
        base_url=BASE_URL,
    )

    logger = TraceLogger(
        enabled=VERBOSE,
        trace_file=TRACE_FILE,
    )

    agent = Agent(
        model=model,
        tools=tools,
        max_steps=MAX_STEPS,
        logger=logger,
    )

    try:
        result = agent.start(task)

        while True:
            print("\n=== assistant ===")
            print(result)

            user_input = read_prompt("\n> ")

            if user_input is None:
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", ":q"}:
                break

            result = agent.send(user_input)

    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
