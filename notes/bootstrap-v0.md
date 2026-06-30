# SkySail Bootstrap Notes: Day 0

This note records the Day 0 bootstrap process of SkySail: a single-file, self-bootstrapping agent runtime.

SkySail started as a small `agent.py` with four basic tools:

* `ls`
* `read`
* `write`
* `sh`

The first goal was not to build a complete agent framework. The goal was to make the core mechanics of a tool-using agent visible in one readable file.

By the end of Day 0, SkySail could already inspect itself, modify itself, run checks, and explain its own changes.

That does not mean it is ready to autonomously evolve itself.

But it does mean the first bootstrap loop is real.

## 1. The First Working Loop

The initial loop was simple:

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

The important part was not the number of tools.

The important part was getting the runtime loop right:

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

This gave SkySail a minimal but complete agent runtime.

## 2. Why the Model Layer Needed an Interface

A key early design decision was to keep the agent runtime provider-neutral.

The runtime should not directly depend on any provider-specific response format. Instead, it talks to a small internal interface:

```python
class Model(Protocol):
    def respond(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> ModelResponse:
        ...
```

The runtime only understands:

* `ChatMessage`
* `ToolSpec`
* `ToolCall`
* `ToolResult`
* `ModelResponse`

This keeps the core loop independent of any model provider's native tool-calling format.

Provider-specific behavior belongs inside model adapters.

## 3. Text-Frame Protocol

The first model adapter does not use native tool calling.

Instead, it uses a fallback text-frame protocol:

```text
normal visible assistant text

§AGENT {"tool_calls":[{"name":"read","input":{"path":"agent.py"}}]}
```

Or, when complete:

```text
final visible assistant answer

§AGENT {"final":true}
```

This design came from an important observation:

A tool call should be an attachment to a message, not the whole message itself.

A pure JSON response makes the model feel like a protocol machine. It also makes normal communication awkward.

The text-frame protocol keeps natural language and machine control separated.

## 4. Why Tag Parsing Failed

An early version used XML-like tags such as:

```text
<action>...</action>
<final>...</final>
```

That design failed quickly.

The problem was that the agent needed to read and modify its own source code. Once the source code contained those tags, a parser that scanned the whole response body could misinterpret ordinary code as a tool action or final answer.

The fix was to parse only the final non-empty line.

That line must start with:

```text
§AGENT 
```

This made the parser much more stable.

## 5. Why JSON-Only Was Not Enough

A stricter version required the entire model response to be JSON.

That solved some parsing problems, but it created a different problem: it forced all visible communication into JSON fields.

That made the model less natural and made debugging harder.

The better compromise was:

```text
visible text body
+
final machine-readable control frame
```

This is closer to how native tool-calling APIs separate assistant text from tool calls.

## 6. Trace Logging Became Necessary

Once the agent started running multiple steps, normal terminal output was not enough.

When the model failed to emit a valid control frame, the runtime could report an error, but without the raw model output it was difficult to understand what actually happened.

This led to the addition of verbose JSONL trace logging.

With `VERBOSE=1`, SkySail records events such as:

* `run_start`
* `step_start`
* `model_raw`
* `model_parsed`
* `tool_call`
* `tool_result`
* `runtime_error`
* `run_final`

This made the runtime much easier to debug.

Trace logging is not a nice-to-have feature. For agent development, it is part of the core runtime.

## 7. Raw Message History Improved Stability

Another important improvement was preserving the raw assistant message in conversation history.

Initially, the runtime only stored the visible assistant text:

```text
Let me inspect the repository first.
```

But it discarded the control frame:

```text
§AGENT {"tool_calls":[...]}
```

That made later model responses less stable, because the model could no longer see its own successful protocol examples.

The fix was to store the raw assistant message in history.

This helps the model continue following the same response format across steps.

## 8. Tool Design Shapes Model Behavior

The first `read` tool only accepted:

```json
{"path":"agent.py"}
```

But when the model saw that `agent.py` was truncated, it naturally tried:

```json
{"path":"agent.py","offset":420}
```

That failed because `offset` was not supported yet.

This was an important lesson:

Models infer tool affordances from context. If a file read is truncated, the model expects some way to continue reading.

There are two possible responses:

1. Explicitly say the tool does not support pagination.
2. Add pagination support.

SkySail chose to support `offset` and `limit` in the `read` tool.

This kept the tool small while making it much more useful for self-inspection.

## 9. The First Self-Iteration

After adding trace logging, raw message history, and paginated reads, SkySail was able to attempt a self-iteration.

It inspected:

* repository structure
* `README.md`
* `agent.py`
* `LICENSE`

Then it proposed and implemented a larger v0.2-style update, including:

* additional tools
* safer file handling
* better parse-error recovery
* README updates
* syntax checks

The generated change was not automatically committed.

That is intentional.

Self-bootstrapping should not mean blind self-modification. A better loop is:

```text
agent proposes change
   ↓
agent applies change
   ↓
agent runs checks
   ↓
human reviews diff
   ↓
human decides whether to commit
```

This is the right control boundary for now.

## 10. Human-in-the-Loop Is Not Just Permission Control

One of the most important Day 0 reflections is that human-in-the-loop should not only mean low-level tool permission.

There are at least two different layers of human confirmation.

### 10.1 Intent-Level Confirmation

Before the agent starts doing real work, it should be able to discuss the task with the user.

It should be able to ask questions such as:

* What is the real goal?
* What constraints should I follow?
* Should I optimize for safety, speed, readability, or completeness?
* Do you want a small change or a larger refactor?
* Should I propose options before editing files?

This is not just a safety feature. It is part of the product experience.

The agent should not always jump straight into execution. In many cases, it should first propose a plan, discuss alternatives, and let the user confirm the direction.

For example:

```text
I see three possible directions:

A. Minimal fix
B. Small runtime improvement
C. Larger workflow redesign

Which one do you want me to pursue?
```

This matters because an agent is not only a tool executor. It is also a collaborator.

### 10.2 Micro-Level Tool Confirmation

There is another layer of confirmation around concrete tool execution.

For example:

* before writing a file
* before running a risky shell command
* before deleting or overwriting anything
* before making a large multi-file change
* before committing or pushing code

This layer is closer to a permission system.

It is important, but it does not have to be the immediate next milestone.

At the current stage, the more urgent problem is not a full permission framework. The more urgent problem is making the agent capable of discussing intent and confirming direction before it starts acting.

The agent should first become a better collaborator.

A detailed permission system can come later.

## 11. The Agent Should Propose Before Acting

A key workflow principle for SkySail should be:

```text
understand
   ↓
propose
   ↓
confirm
   ↓
act
   ↓
verify
   ↓
report
```

This is different from a pure coding agent loop:

```text
receive task
   ↓
act immediately
   ↓
return result
```

The immediate-action loop is useful for small tasks, but it is not enough for a general agent.

For non-trivial tasks, SkySail should first produce a proposal.

A proposal may include:

* its understanding of the task
* assumptions
* risks
* options
* recommended next step
* what files or tools it expects to use

Then the user can respond.

This creates a more useful human-agent collaboration pattern.

The user remains in control, but the agent does more than wait for exact instructions.

## 12. Final Confirmation Also Matters

Human-in-the-loop should also happen at the end.

After the agent completes a task, it should not only say “done”.

It should provide:

* what it changed
* what it verified
* what remains uncertain
* whether the user should review anything
* whether follow-up work is recommended

For code changes, that might be:

```text
I changed these files:

- agent.py
- README.md

I ran:

- python -m py_compile agent.py
- git diff

The syntax check passed. The diff is ready for human review.
```

The final confirmation step is important because the user needs to decide whether to accept, revise, commit, or discard the work.

## 13. Workflow Should Exist, But Not Become Too Rigid

SkySail needs workflows, but it should not become a rigid workflow engine.

The goal is not to hard-code every possible process.

The agent should have a few basic collaboration patterns:

* clarify
* propose
* execute
* verify
* summarize
* resume

But these should be flexible.

The agent should be able to work differently depending on the user’s intent.

Sometimes the user wants direct execution.

Sometimes the user wants discussion.

Sometimes the user wants brainstorming.

Sometimes the user wants a careful plan before any action.

A general agent should support all of these modes.

## 14. SkySail Should Not Be Only a Coding Agent

Another important reflection is that SkySail should not be designed only as a coding worker.

Even though the first tools are coding-oriented, the project goal is broader.

SkySail should be a general agent runtime.

That means it may eventually support:

* coding tasks
* writing tasks
* research tasks
* planning tasks
* operational tasks
* pure conversation
* long-running personal workflows

This matters for the architecture.

If SkySail is designed only as a coding agent, it may overfit to:

* file editing
* shell commands
* git diffs
* patches
* commits

Those are useful, but they are not the whole agent experience.

A general agent also needs:

* conversation
* memory
* session continuity
* user preference awareness
* task planning
* interruption and resume
* reflective summaries

The runtime should leave room for these.

## 15. Conversation Is Also a Valid Mode

An agent does not always need to use tools.

Sometimes the right response is a conversation.

For example:

* helping the user clarify an idea
* discussing trade-offs
* producing a design proposal
* thinking through product direction
* explaining a concept
* refining a plan

This means the runtime should not assume that every turn must lead to tool execution.

The model should be allowed to answer, ask questions, or propose options.

The text-frame protocol already supports this:

```text
I think there are two possible directions. I recommend we start with the lighter one.

§AGENT {"final":true}
```

But product-wise, SkySail may need a more explicit distinction between:

* final answer
* clarification question
* proposal awaiting confirmation
* tool execution request

This may become an important part of the next design iteration.

## 16. Memory May Become a Core Capability

If SkySail is a general agent, memory becomes important.

Not all memory needs to be implemented immediately.

But the runtime should eventually distinguish between:

* session memory
* project memory
* user preferences
* long-term facts
* task-specific notes
* generated summaries

For example, SkySail may need to remember:

* the user prefers single-file architecture
* the user wants readable code before powerful code
* the project should remain provider-neutral
* self-modification should be reviewed before commit
* the agent should propose before acting

These memories shape future behavior.

Memory is not just storage. It is part of the context engine.

## 17. Session Resume Is a Major Design Problem

A single run of `agent.py` is currently one session.

But if SkySail becomes useful, sessions need to be resumable.

A session may be interrupted because:

* the process exits
* the user stops the run
* the model hits a step limit
* the context becomes too long
* the user wants to continue tomorrow
* the agent needs human confirmation before proceeding

This suggests that session state should eventually be persistable.

A resumable session may need to store:

* task
* messages
* tool calls
* tool results
* raw model outputs
* current step
* trace file path
* pending proposal
* pending user confirmation
* summary of completed work
* open questions

Trace logs already move in this direction, but trace logs alone are not enough.

A trace is mostly for debugging and replay.

A session state is for continuing work.

These may become separate concepts.

## 18. Recoverability Is Part of Reliability

Reliability is not only about avoiding bugs.

It is also about recovering from interruption, failure, and uncertainty.

For SkySail, recoverability may include:

* parse-error recovery
* tool-error recovery
* interrupted run recovery
* context compaction
* session resume
* diff-based verification
* checkpointing before risky writes

This is different from adding more tools.

It is about making the runtime trustworthy.

Before SkySail becomes more powerful, it should become easier to pause, inspect, resume, and rollback.

## 19. Write Reliability Matters

The current `write` tool replaces a whole file.

That is simple and understandable, but risky.

For small files, full-file writes are acceptable.

For larger files, full-file writes can cause problems:

* accidental deletion of unchanged content
* formatting drift
* unnecessary large diffs
* hard-to-review changes
* higher chance of model mistakes

Eventually, SkySail will need more reliable editing patterns.

Possible directions:

* patch tool
* search-and-replace tool
* structured edit tool
* write-to-temp then diff
* require diff review after write
* require check after code modification

This does not need to be solved before the interaction model.

But write reliability is one of the core engineering problems.

## 20. Safety Matters, But It Is Not the Only Next Step

There are obvious safety issues:

* sensitive files such as `.env`
* shell command risk
* hidden trace logs
* file overwrite risk
* accidental leakage into logs
* broad workspace access

These are important.

However, Day 0 also showed that safety should not dominate the entire next-step roadmap.

The more foundational product question is:

How should the agent collaborate with the user before, during, and after action?

Permission control is one part of that.

But intent confirmation, proposal, discussion, and final review may be even more important for the next iteration.

## 21. Key Lessons So Far

### Agent loop is small

The core loop is not complicated. It is mostly:

```text
model → tool calls → tool results → model
```

### Runtime reliability comes from boring details

The hard parts are:

* parser discipline
* tool schemas
* trace logs
* recovery messages
* context history
* safe file access
* command guardrails
* resumable state

### Tools are product design

A tool is not just a function.

Its name, parameters, description, output shape, and failure messages all influence model behavior.

### Interaction design shapes the agent

The prompt, protocol, and available tools shape whether the agent behaves like:

* a command executor
* a coding assistant
* a collaborator
* a bot
* a general-purpose agent

SkySail should move toward the collaborator model.

### Self-bootstrapping requires checkpoints

An agent that can modify itself must be paired with:

* trace logs
* syntax checks
* diff review
* git checkpoints
* human approval

### Single-file does not mean no architecture

SkySail is physically one file, but logically it already has layers:

```text
Types
Config
Utilities
Tools
Model Adapter
Agent Runtime
CLI
```

This keeps the project readable while preserving the single-file distribution model.

## 22. Current Status

SkySail has reached the first meaningful bootstrap milestone:

```text
It can inspect itself.
It can modify itself.
It can run checks.
It can explain its own changes.
```

This is not yet a production agent.

But it is no longer just a script.

It is now a small, inspectable agent runtime that can participate in its own evolution.

## 23. Next Direction

The next step should not be to immediately build a heavy workflow engine.

It should be to improve the collaboration loop.

A possible next milestone:

```text
clarify / propose / confirm / act / verify / report
```

Concretely, SkySail should learn to:

1. Ask clarification questions when the task is ambiguous.
2. Propose a plan before making non-trivial changes.
3. Offer options when there are multiple reasonable paths.
4. Wait for user confirmation before executing larger changes.
5. Summarize what it did and what should be reviewed.
6. Keep enough session state to resume interrupted work later.

This would make SkySail feel less like a script that runs tools and more like a real agent.

## 24. Open Questions

The most important open questions after Day 0 are:

1. How should SkySail represent a proposal that is waiting for user confirmation?
2. Should there be a separate control frame for `ask_user` or `await_confirmation`?
3. How should the runtime distinguish between final answer, clarification question, and executable plan?
4. What is the smallest useful session state that can support resume?
5. How should memory be introduced without making the runtime too complex?
6. How can write reliability improve without prematurely adding a large patch framework?
7. How should tool permissions work later without turning SkySail into a rigid workflow engine?
8. How can SkySail remain a general agent instead of becoming only a coding agent?

## 25. Day 0 Conclusion

Day 0 proved that the basic self-bootstrapping loop works.

But it also revealed that the next frontier is not just more tools.

The next frontier is collaboration.

A useful general agent should not only execute.

It should be able to discuss, propose, confirm, act, verify, and resume.

SkySail should grow in that direction.
