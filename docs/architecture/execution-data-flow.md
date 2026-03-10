# Execution Data Flow

Canonical runtime map for the CLI-first architecture.
Prefer this doc when changing control flow, tool orchestration, prompt caching,
or session behavior.
Last updated: 2026-03-10.

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
| Create ResumeAgent                   |
| - create_agent(...)                  |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| LLMAgent.run loop                    |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Provider call                        |
| gemini / openai_compat               |
+--------------------------------------+
                  |
                  v
+--------------------------------------+
| Function calls?                      |
+--------------------------------------+
             |              |
           No|              |Yes
             v              v
 +--------------------+  +----------------------+
 | Render final text  |  | Execute tools        |
 | in CLI             |  +----------------------+
 +--------------------+             |
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
- `resume_agent/core/agent.py`
- `resume_agent/core/llm.py`
- `resume_agent/tools/*`
- `resume_agent/domain/*`

## 2) LLMAgent Step Loop (Core Runtime)

`LLMAgent.run()` uses wire mode as the canonical execution path.

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
[Contains approval-required tool call?]
    | Yes
    v
[Inline approval via Wire]
  Build approval metadata per tool call:
    - loop asks tool for build_approval_request(**args) when available
    - tool returns action key + description
    - fallback path uses generic call summary
  Approval.request() blocks on asyncio.Future
  UI consumer prompts user and resolves the Future
  "approve_all" persists as action-scoped auto-approve across subsequent turns
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
[Max steps reached?] -- Yes --> [Return max-steps fallback]
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

Safety and reliability mechanisms:
- retry/backoff wrapper around provider calls
- provider-level prompt cache support for OpenAI-compatible backends
- required-argument pre-validation before tool execution
- malformed function-call response retry for provider-level empty payload cases
- observability events for step/tool/llm lifecycle

### 2.1) Approval Metadata Ownership

Approval metadata is generated by tools, not by loop-side resource inspection.

```text
[LLMAgent approval phase]
    |
    v
[for each function call]
    |
    +--> call tool.build_approval_request(**args) when available
              |
              +--> action key (e.g. file_write, file_edit, file_rename)
              +--> description (can embed unified diff preview)
    |
    v
[compose ApprovalRequest(action, description)]
```

Current ownership boundary:
1. Loop (`core/llm.py`) orchestrates only; it does not read target files to compute diffs.
2. Tools (`tools/file_tool.py`) own mutation preview semantics and action-level approval metadata.
3. UI (`cli/app.py`) only renders `ApprovalRequest.description`.

Key files:
- `resume_agent/core/llm.py`
- `resume_agent/core/wire/`
- `resume_agent/tools/file_tool.py`

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

## 4) Session Persistence Flow

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
3. `resume_agent/core/agent.py`
4. `resume_agent/core/llm.py`
5. `resume_agent/cli/tool_factory.py`
6. `resume_agent/tools/resume_tools.py`
7. `resume_agent/domain/*.py`
8. `resume_agent/providers/*.py`
9. `resume_agent/core/session.py`
