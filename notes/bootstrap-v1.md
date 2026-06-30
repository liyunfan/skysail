# SkySail Bootstrap Notes: Day 1

Day 0 proved that SkySail could run a minimal tool-using loop.

Day 1 was about something different.

The question was no longer only:

```text
Can the agent call tools?
```

The question became:

```text
Can the agent collaborate with the user?
```

This note records the Day 1 design path: from structured questions, to conversation mode, to a simpler multi-turn session model.

## 1. Starting Point

At the end of Day 0, SkySail had a working single-file agent runtime.

It could:

* inspect files
* read large files with offset / limit
* write files
* run shell commands
* preserve raw model messages
* write JSONL trace logs
* modify itself under human review

The core loop was:

```text
model response
   ↓
tool calls
   ↓
tool execution
   ↓
tool results
   ↓
next model response
```

This worked.

But it still felt like a tool runner.

For a more useful agent, especially one that may modify its own code, the model should not always jump straight into execution.

It should be able to talk first.

## 2. The First Collaboration Problem

The first Day 1 goal was human-in-the-loop collaboration.

The initial idea was:

```text
Before doing non-trivial work, the agent should confirm direction with the user.
```

There are two kinds of confirmation:

### Intent-level confirmation

The agent asks questions such as:

* What is the real goal?
* Should this be a minimal change or a larger refactor?
* Which option do you prefer?
* Should I propose a plan before editing files?

### Micro-level tool approval

The runtime asks before concrete actions such as:

* writing a file
* running a risky shell command
* deleting files
* committing code
* pushing changes

Day 1 focused on the first kind: intent-level collaboration.

The permission system can come later.

## 3. Introducing the `question` Tool

The first implementation idea was to add a `question` tool.

The tool lets the model ask the user a structured question:

```json
{
  "title": "Choose direction",
  "question": "Which direction should SkySail take next?",
  "options": [
    "collaboration workflow",
    "session resume",
    "tool system upgrade"
  ],
  "allow_free_text": true
}
```

This worked well for short, structured choices.

The runtime can display the question, read the user’s answer, and return it as a tool result.

This gave SkySail a first version of human-in-the-loop behavior:

```text
agent investigates
   ↓
agent asks a structured question
   ↓
user chooses
   ↓
agent continues
```

This was a real improvement.

But it also exposed a limitation.

## 4. `question` Was Not Enough

A longer self-improvement task showed that the model did not always want to ask a short structured question.

Sometimes it wanted to produce a full proposal:

```text
I inspected the project.

Here are the current components.

Here are four possible directions.

I recommend option D because it combines collaboration workflow and session persistence.

Which direction do you prefer?
```

This is not a small structured question.

It is a proposal.

Forcing this into a `question` tool would make the design awkward. The model would have to stuff a long design note into a JSON argument.

That would bring back the same problem that SkySail had already avoided with JSON-only responses: natural language would become trapped inside protocol fields.

So the design needed another concept.

## 5. Conversation Mode

The next idea was conversation mode.

The rule was:

```text
If the model replies without a control frame, treat it as a normal assistant message and wait for the user.
```

This made the runtime more natural.

The model could write:

```text
I found three possible directions:

1. Add session resume
2. Improve CLI display
3. Add safer editing

I recommend starting with session resume because long tasks are already hitting step limits.

Which direction do you want me to take?
```

No control frame was required.

The runtime would print the message and wait for the user’s next input.

This was an important step.

It meant that normal assistant conversation became a valid runtime behavior, not a protocol error.

## 6. The `final` Problem

Once conversation mode existed, the earlier `final=true` control frame started to feel wrong.

Previously, SkySail used:

```text
§AGENT {"final":true}
```

to mark that the task was complete.

But in a real conversation, a “final answer” is not truly final.

The user can always continue:

* challenge the result
* ask a follow-up question
* request a revision
* ask the agent to continue
* change direction

So `final` was not really a runtime primitive.

It was just a normal assistant reply with no more tool calls.

This led to a simplification:

```text
Remove final as a first-class protocol state.
```

## 7. The `await_user` Problem

For a short time, the design also considered `await_user`.

The idea was:

```text
§AGENT {"await_user":true}
```

But this also became unnecessary.

If the model asks a question in natural language and does not request tools, then it is already waiting for the user.

No extra protocol state is needed.

So `await_user` was also removed.

The design became smaller:

```text
tool calls present  → continue automatic execution
tool calls absent   → yield to the user
```

## 8. The Simplified Runtime Boundary

The Day 1 breakthrough was this rule:

```text
Only tool calls drive the automatic loop.
Everything else is an assistant reply.
```

This means SkySail no longer needs separate runtime states for:

* final
* await_user
* conversation
* propose
* await_confirm

Those are natural-language meanings.

They are not core runtime states.

The runtime only needs to know:

```text
Did the model ask for tools?
```

If yes, execute tools and continue.

If no, yield control to the user.

This is the simplest useful boundary.

## 9. Agent Owns the Session

After removing `final` and `await_user`, another design issue became obvious.

If a normal assistant reply yields to the user, the CLI should not immediately exit.

The agent should be able to continue the same conversation.

That means there are two loops:

### Automatic tool loop

```text
model response
   ↓
if tool_calls: execute tools
   ↓
append tool results
   ↓
continue
```

### Human conversation loop

```text
assistant yields
   ↓
user replies
   ↓
agent continues with same messages
```

The important design decision:

```text
Agent should own the message history.
```

The CLI should not manage messages.

The CLI should only:

* read user input
* send it to the agent
* print assistant output
* repeat

The `Agent` should own:

* messages
* tool results
* raw model responses
* trace events
* future session state

This prepares SkySail for future session persistence and resume.

## 10. Multi-Turn Session Loop

Day 1 introduced a multi-turn session loop.

The conceptual API became:

```text
Agent.start(task)
Agent.send(user_input)
Agent.run_until_yield()
```

The behavior:

```text
start(task):
  add the first user message
  run automatic tool loop until the model stops asking for tools

send(user_input):
  add the next user message
  continue the same session
  run automatic tool loop again

run_until_yield():
  execute tool calls until there are no more tool calls
  return the assistant reply to the user
```

This is a much better model.

SkySail is no longer:

```text
one command → one answer → process exits
```

It is now:

```text
one session → many user turns → many tool loops
```

## 11. The First Impressive Multi-Turn Run

The multi-turn version felt qualitatively different.

The agent could:

1. inspect the repository
2. read its own code
3. read the bootstrap notes
4. produce a design proposal
5. ask the user to choose a direction
6. receive the user’s answer
7. refine the plan
8. continue implementation
9. run checks
10. report progress

This felt much closer to a modern agent.

The agent was no longer only “doing work”.

It was investigating, discussing, proposing, asking, and continuing.

The working loop became:

```text
research
   ↓
propose
   ↓
discuss
   ↓
choose
   ↓
execute
   ↓
verify
   ↓
continue
```

This is the first time SkySail started to feel like a real collaborative runtime.

## 12. Text-Frame Started to Feel Like a Fallback

Day 1 also made the text-frame protocol feel more temporary.

The current model adapter asks the model to write a final-line control frame:

```text
§AGENT {"tool_calls":[...]}
```

This works, but it is tricky.

It depends on prompt obedience and parsing text.

Modern model APIs increasingly support native tool use. The application can pass tool definitions, the model can return structured tool calls, and the runtime can execute them directly.

That suggests a future direction:

```text
Native tool calling should become the default model path.
Text-frame should be fallback or eventually removed.
```

The important point is that SkySail’s internal types remain useful:

```text
ToolSpec
ToolCall
ToolResult
ModelResponse
```

Those are the runtime abstraction.

Only the adapter should change.

A native OpenAI-style model adapter can convert provider-native tool calls into SkySail `ToolCall` objects.

The runtime loop does not need to care where the tool call came from.

## 13. Long Runs Exposed Step Limits

The first longer self-modification runs also started hitting limits.

One run reached:

```text
Stopped after 15 steps without a final answer.
```

Another run hit the maximum tool-call limit.

This was useful feedback.

It showed that once SkySail becomes collaborative, tasks become longer:

* inspect code
* read notes
* propose options
* wait for user
* refine plan
* edit files
* verify
* update documentation
* summarize

This can easily exceed a small fixed step budget.

Increasing `MAX_STEPS` helps temporarily, but it is not the real solution.

The real need is:

```text
session persistence
resume
fault recovery
progress summary
```

## 14. Resume Becomes a Core Concern

Once an agent supports multi-turn collaboration, resume becomes important.

The session may be interrupted because:

* the user presses Ctrl+C
* the process exits
* the model hits the step limit
* the context becomes too long
* a tool fails
* the user wants to continue later
* the run needs manual review before proceeding

The current trace logs show what happened.

But trace is not enough.

A trace is for debugging.

A session state is for continuing.

Future SkySail should persist:

* messages
* tool results
* current step
* trace path
* model config
* current workspace
* unfinished work summary
* maybe a compacted context summary

This should allow:

```bash
python agent.py --resume <session-id>
```

Resume is no longer just a nice-to-have feature.

It is part of making long-running agent work reliable.

## 15. Context Compaction Becomes Necessary

Longer sessions also create context pressure.

A multi-turn agent accumulates:

* user messages
* assistant messages
* raw model outputs
* tool results
* file contents
* traces
* plans
* verification output

Eventually the context will become too long or too expensive.

This means compaction will become necessary.

But compaction is not just summarization.

It must preserve:

* the task goal
* user decisions
* current plan
* changed files
* failed attempts
* verification status
* open questions
* tool protocol examples if still needed

For a self-bootstrapping agent, bad compaction can break continuity.

So compaction is part of the reliability system.

## 16. Cache and Performance

Day 1 also exposed a performance issue.

As the session grows, each model call becomes slower because the model receives the full conversation again.

There is no cache reuse yet.

For long multi-turn sessions, performance will matter.

Future work should consider:

* provider prompt caching
* context caching
* reusable prefix state
* trace-to-context reconstruction
* compaction before expensive turns
* avoiding repeated full-file reads when not needed

This is especially important because agent tasks are not single-turn prompts.

They are long-running interactions.

Performance, reliability, and context management are connected.

## 17. CLI Experience Needs Improvement

The CLI now works, but it is still rough.

Tool output currently looks like debug logs:

```text
--- step 1/15 ---
[ok] ls#0: .env
```

This is useful, but not pleasant.

As SkySail becomes more interactive, the CLI becomes the product surface.

It should better show:

* current step
* current tool call
* tool result summary
* assistant message
* question prompts
* long-running model waits
* compact vs verbose mode
* where trace logs are written

The user also wanted a way to “peek” into the process.

This should not expose hidden chain-of-thought.

But it can expose runtime-observable progress:

```text
current step
current tool call
last model-visible action
trace event
short visible plan
```

This should be part of a future CLI improvement.

## 18. Day 1 Design Summary

Day 1 started with a collaboration problem.

The path was:

```text
Need human-in-the-loop collaboration
   ↓
Add question tool
   ↓
Notice that long proposals do not fit question tool
   ↓
Allow normal replies without control frames
   ↓
Notice final and await_user are redundant
   ↓
Simplify runtime to tool_calls only
   ↓
Move message history into Agent
   ↓
Add multi-turn session loop
   ↓
See need for resume, compaction, cache, and better CLI
```

The final Day 1 runtime principle:

```text
Agent owns the session.
Model adapters normalize model output into tool calls.
Runtime executes tools until the model stops asking for tools.
Then it yields control back to the user.
```

## 19. Current Capability After Day 1

SkySail can now:

* hold a multi-turn session
* keep message history inside `Agent`
* call tools automatically until no tools are requested
* yield control to the user
* continue after the user replies
* ask structured questions
* produce long natural-language proposals
* inspect and edit its own files
* run checks
* write trace logs
* preserve raw model messages
* self-improve under human supervision

This is a meaningful step beyond Day 0.

Day 0 made SkySail a working agent loop.

Day 1 made it a collaborative agent session.

## 20. Next Questions

The next questions are now clearer:

1. Should the text-frame adapter be replaced by an OpenAI-style native tool-calling adapter?
2. What is the smallest useful session state for resume?
3. How should step-limit stops produce useful unfinished-work summaries?
4. How should context compaction preserve user decisions and current plan?
5. How can provider cache or prompt caching improve long-session performance?
6. How should the CLI show tool calls and long-running progress more clearly?
7. What should a safe edit workflow look like without making the runtime too complex?
8. When should permission policy be introduced?

## 21. Day 1 Conclusion

Day 1 was not mainly about adding features.

It was about removing unnecessary protocol states and finding the right runtime boundary.

The key result:

```text
tool calls continue the automatic loop
normal replies return control to the user
```

This simple rule made SkySail more natural.

It also made the next set of hard problems visible:

```text
resume
compaction
cache
CLI experience
native tool calling
reliability
```

That is the right kind of progress.
