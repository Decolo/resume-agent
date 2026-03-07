# Execution Data Flow

Canonical runtime map for the CLI-first architecture.
Prefer this doc when changing control flow, tool orchestration, or session behavior.
Last updated: 2026-03-03.

## 1) End-to-End Pipeline (Interactive CLI)

```text
+--------------------------------------+
| CLI Start (resume_agent/cli/app.py)  |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Parse Args + Load Config             |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Config Validation                    |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Create Runtime Dependencies          |
| - SessionManager                     |
| - Tool Registry                      |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Resolve Agent Mode                   |
| --single-agent / --multi-agent / auto|
+--------------------------------------+
      |                    |                    |
      v                    v                    v
+---------------+  +------------------+  +----------------+
| ResumeAgent   |  | OrchestratorAgent|  | AutoAgent      |
| .run()        |  | .run()           |  | .run()         |
+---------------+  +------------------+  +----------------+
      \                    |                    /
       \                   |                   /
        +------------------------------------+
                          |
                          v
               +----------------------+
               | LLMAgent.run loop    |
               +----------------------+
                          |
                          v
               +----------------------+
               | Provider call        |
               | gemini/openai_compat |
               +----------------------+
                          |
                          v
               +----------------------+
               | Function calls?      |
               +----------------------+
                     |        |
                   No|        |Yes
                     v        v
      +--------------------+  +----------------------+
      | Render final text  |  | Execute tools        |
      | in CLI             |  +----------------------+
      +--------------------+            |
                                        v
                              +----------------------+
                              | Tool adapters        |
                              | (resume_agent/tools) |
                              +----------------------+
                                        |
                                        v
                              +----------------------+
                              | Domain functions     |
                              | (resume_agent/domain)|
                              +----------------------+
                                        |
                                        v
                              (back to LLMAgent loop)
```

Key files:
- `resume_agent/cli/app.py`
- `resume_agent/cli/config_validator.py`
- `resume_agent/cli/tool_factory.py`
- `resume_agent/core/agent_factory.py`
- `resume_agent/core/llm.py`
- `resume_agent/tools/*`
- `resume_agent/domain/*`

## 2) LLMAgent Step Loop (Core Runtime)

Two code paths exist in `LLMAgent.run()`:

### Wire path (`wire` param provided — interactive CLI default)

```text
[Start Step]
    |
    v
[Wire: TurnBegin]
    |
    v
[Add user message to HistoryManager]
    |
    v
[Wire: StepBegin(n)]
    |
    v
[Call provider: generate / generate_stream]
  (TextDelta events emitted to Wire during streaming)
    |
    v
[Parse response: text + function_calls]
    |
    v
[Append assistant message]
    |
    v
[Any function calls?] -- No --> [Wire: TurnEnd] --> [Return final text]
    |
   Yes
    v
[Contains write tool requiring approval?]
    | Yes
    v
[Inline approval via Wire]
  Approval.request() blocks on asyncio.Future
  _pipe_approval_to_wire sends ApprovalRequest to UI
  UI consumer prompts user and resolves the Future
  "approve_all" persists as LLMAgent auto-approve across subsequent turns
    |
    +--- rejected ---> [Inject rejection into history] --> (next step)
    |
    v (approved)
[Wire: ToolCallEvent for each tool]
    |
    v
[Execute calls with asyncio.gather]
    |
    v
[Wire: ToolResultEvent for each tool]
    |
    v
[Append tool responses]
    |
    v
[Auto-save if SessionManager present]
    |
    v
[Max steps / loop guard hit?] -- Yes --> [Return guarded fallback]
    |
   No
    v
(next step)
```

### Misconfiguration Path (Wire Without UI Subscriber)

```text
[run(..., wire=Wire())]
    |
    v
[No UI subscriber attached]
    |
    v
[Contains write tool requiring approval?]
    | Yes
    +--> if approval_handler exists: delegate approval via handler
    |
    +--> else: fail fast with
         "Tool call(s) require approval, but no Wire UI consumer or approval handler is available."
    |
   No
    v
[Continue normal execution]
```

Safety and reliability mechanisms in both paths:
- retry/backoff wrapper around provider calls
- loop guard for repeated tool-only cycles
- per-tool cache for read-heavy tools
- required-argument pre-validation before tool execution (missing required args fail fast with structured error)
- observability events for step/tool/llm lifecycle

### 2.1) Failure Path: Repeated Truncated `file_write` (Observed 2026-03-07)

This is the current control-flow behavior when the model repeatedly emits a
`file_write` call with syntactically valid but semantically truncated content.

```text
[Step N provider response]
  function_calls=[file_write(path, content="<...initial-scale=1.0\\")]
        |
        v
[LLMAgent._repair_function_call_args_from_raw_response]
  - may log: llm_repaired_tool_args_from_raw
  - does NOT guarantee content completeness
        |
        v
[Approval path]
  - file_write is a write tool => approval required
  - user approves
        |
        v
[LLMAgent._execute_tool]
  - required args check passes (path/content exist)
  - FileWriteTool overwrites target file directly
        |
        v
[Tool result added to history]
  "Successfully wrote 140 characters ..."
        |
        v
[Step N+1 provider response]
  - model can emit the same truncated file_write again
        |
        +--> [_check_loop_guard] triggers only on tool-only repeated call thresholds
        |
        +--> [_check_repeated_write_guard] triggers after repeated identical successful writes
               (current threshold allows at least one repeated identical write before abort)
```

Important implication:
- "has required args" is treated as executable, even when content is obviously
  short/incomplete for the target format (for example, HTML with no closing
  tags). This allows destructive overwrite before guards stop the loop.

Current guard layering:
1. `_check_loop_guard`: generic repeated-tool/tool-only protection.
2. `_check_repeated_write_guard`: repeated identical write protection.

Observed production effect:
- File can be overwritten by short/truncated payload multiple times before the
  run aborts.

Related runtime points:
- `resume_agent/core/llm.py`:
  `_repair_function_call_args_from_raw_response`,
  `_check_loop_guard`, `_check_repeated_write_guard`, `_execute_tool`
- `resume_agent/tools/file_tool.py`: `FileWriteTool.execute`
- `resume_agent/providers/openai_compat.py`: `_safe_parse_args`

Key files:
- `resume_agent/core/llm.py`
- `resume_agent/core/wire/` (Wire protocol, Approval, Queue primitives)

## 3) Tool and Domain Data Path

```text
[Tool schema registration]
          |
          v
[LLM chooses tool name + args]
          |
          v
[LLMAgent._execute_tool]
          |
          v
[Tool adapter (resume_agent/tools)]
          |
          v
[I/O + format translation]
          |
          v
[Pure domain function (resume_agent/domain)]
          |
          v
[ToolResult]
          |
          v
[FunctionResponse added to history]
          |
          v
[Next LLM step]
```

For resume-specific tools:
- adapters: `resume_agent/tools/resume_tools.py`
- domain: `resume_agent/domain/resume_parser.py`, `resume_linter.py`, `job_matcher.py`, `resume_writer.py`, `resume_validator.py`

## 4) Multi-Agent Delegation Path

```text
[User task]
    |
    v
[OrchestratorAgent]
    |
    v
[delegate_to_* via AgentTool]
    |
    v
[DelegationManager creates AgentTask]
    |
    v
[Target agent?]
   | Parser      | Writer      | Formatter
   v             v             v
[ParserAgent] [WriterAgent] [FormatterAgent]
   |             |             |
   +-------------+-------------+
                 |
                 v
            [Agent result]
                 |
                 v
[Return as tool response to Orchestrator]
                 |
                 v
           [OrchestratorAgent]
```

Key files:
- `resume_agent/core/agent_factory.py`
- `resume_agent/core/agents/orchestrator_agent.py`
- `resume_agent/core/agents/agent_tool.py`
- `resume_agent/core/agents/delegation.py`
- `resume_agent/core/agents/parser_agent.py`
- `resume_agent/core/agents/writer_agent.py`
- `resume_agent/core/agents/formatter_agent.py`

## 5) Session Persistence Flow

```text
[Tool execution completes]
    |
    v
[SessionManager present?] -- No --> [Continue without persistence]
    |
   Yes
    v
[Ensure workspace/sessions path exists (auto-create missing dirs)]
    |
    v
[SessionManager.save_session]
    |
    v
[Write JSON to workspace/sessions]
    |
    v
[Update sessions index]
    |
    v
[Continue runtime]

[/sessions picker selection] --> [SessionManager.load_session]
                      |
                      v
         [Restore history / observability / state]
                      |
                      v
         [Continue conversation with restored context]
```

Files:
- `resume_agent/core/session.py`
- `resume_agent/cli/app.py`

## Suggested Reading Order

Fast path:
1. `resume_agent/cli/app.py`
2. `resume_agent/core/agent_factory.py`
3. `resume_agent/core/llm.py`
4. `resume_agent/cli/tool_factory.py`
5. `resume_agent/tools/resume_tools.py`
6. `resume_agent/domain/*.py`
7. `resume_agent/providers/*.py`
8. `resume_agent/core/session.py`

If debugging multi-agent:
1. `resume_agent/core/agents/orchestrator_agent.py`
2. `resume_agent/core/agents/agent_tool.py`
3. `resume_agent/core/agents/delegation.py`
