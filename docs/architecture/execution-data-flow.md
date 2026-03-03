# Execution Data Flow

Canonical runtime map for the CLI-first architecture.
Prefer this doc when changing control flow, tool orchestration, or session behavior.
Last updated: 2026-02-28.

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

```text
[Start Step]
    |
    v
[Add user message to HistoryManager]
    |
    v
[Call provider: generate / generate_stream]
    |
    v
[Parse response: text + function_calls]
    |
    v
[Append assistant message]
    |
    v
[Any function calls?] -- No --> [Return final text]
    |
   Yes
    v
[Contains write tool requiring approval?]
    | Yes
    v
[Queue pending calls + pause]
    |
    v
[Wait /approve or /reject]
    |
    v
[Resume loop]
    |
    +----------------------------------------------+
                                                   |
    | No or approved                               |
    v                                              |
[Execute calls with asyncio.gather]               |
    |                                              |
    v                                              |
[Append tool responses]                           |
    |                                              |
    v                                              |
[SessionManager exists?] -- No -------------------+
    |
   Yes
    v
[Auto-save session]
    |
    v
[Max steps / loop guard hit?] -- Yes --> [Return guarded fallback or last result]
    |
   No
    v
(next step)
```

Safety and reliability mechanisms in this loop:
- retry/backoff wrapper around provider calls
- loop guard for repeated tool-only cycles
- per-tool cache for read-heavy tools
- required-argument pre-validation before tool execution (missing required args fail fast with structured error)
- LinkedIn mixed-call policy: `job_detail` is rejected when requested in the same step as `job_search`
- observability events for step/tool/llm lifecycle

Key file:
- `resume_agent/core/llm.py`

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

[/save command] --------------------> [SessionManager.save_session]
[/load command] --> [SessionManager.load_session]
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
