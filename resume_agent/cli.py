"""CLI - Command line interface for Resume Agent."""

import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from .agent import ResumeAgent, AgentConfig
from .llm import LLMConfig, load_config


console = Console()


def print_banner():
    """Print welcome banner."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                    📄 Resume Agent                        ║
║         AI-powered Resume Modification Assistant          ║
╠═══════════════════════════════════════════════════════════╣
║  Commands:                                                ║
║    /help     - Show this help message                     ║
║    /reset    - Reset conversation                         ║
║    /quit     - Exit the agent                             ║
║    /files    - List files in workspace                    ║
║                                                           ║
║  Tips:                                                    ║
║    • Drop your resume file in the workspace directory     ║
║    • Ask me to analyze, improve, or reformat your resume  ║
║    • I can tailor your resume for specific job postings   ║
╚═══════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="cyan")


def print_help():
    """Print help message."""
    help_text = """
## Available Commands

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/reset` | Reset conversation history |
| `/quit` or `/exit` | Exit the agent |
| `/files` | List files in workspace |
| `/config` | Show current configuration |

## Example Prompts

- "Parse my resume from resume.pdf and analyze it"
- "Improve my work experience section with stronger action verbs"
- "Tailor my resume for a Senior Software Engineer position at Google"
- "Convert my resume to a modern HTML format"
- "Add quantifiable metrics to my achievements"
- "Check if my resume is ATS-friendly"
"""
    console.print(Markdown(help_text))


async def handle_command(command: str, agent: ResumeAgent) -> bool:
    """Handle special commands. Returns True if should continue, False to exit."""
    cmd = command.lower().strip()
    
    if cmd in ["/quit", "/exit", "/q"]:
        console.print("\n👋 Goodbye!", style="yellow")
        return False
    
    elif cmd == "/help":
        print_help()
    
    elif cmd == "/reset":
        agent.reset()
        console.print("🔄 Conversation reset.", style="green")
    
    elif cmd == "/files":
        result = await agent.tools["file_list"].execute()
        console.print(Panel(result.output, title="📁 Workspace Files"))
    
    elif cmd == "/config":
        config_info = f"""
**Model**: {agent.llm_config.model}
**API Base**: {agent.llm_config.api_base}
**Max Tokens**: {agent.llm_config.max_tokens}
**Temperature**: {agent.llm_config.temperature}
**Workspace**: {agent.agent_config.workspace_dir}
"""
        console.print(Markdown(config_info))
    
    else:
        console.print(f"Unknown command: {command}. Type /help for available commands.", style="red")
    
    return True


async def run_interactive(agent: ResumeAgent):
    """Run interactive chat loop."""
    # Setup prompt with history
    history_file = Path.home() / ".resume_agent_history"
    session = PromptSession(history=FileHistory(str(history_file)))
    
    print_banner()
    
    while True:
        try:
            # Get user input
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.prompt("\n📝 You: "),
            )
            
            user_input = user_input.strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith("/"):
                should_continue = await handle_command(user_input, agent)
                if not should_continue:
                    break
                continue
            
            # Run agent
            console.print("\n🤔 Thinking...", style="dim")
            
            try:
                response = await agent.run(user_input)
                console.print("\n🤖 Assistant:", style="bold green")
                console.print(Markdown(response))
            except KeyboardInterrupt:
                console.print("\n⚠️ Interrupted.", style="yellow")
            except Exception as e:
                console.print(f"\n❌ Error: {str(e)}", style="red")
        
        except KeyboardInterrupt:
            console.print("\n\n👋 Goodbye!", style="yellow")
            break
        except EOFError:
            console.print("\n👋 Goodbye!", style="yellow")
            break


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Resume Agent - AI-powered resume modification assistant"
    )
    parser.add_argument(
        "--workspace", "-w",
        default=".",
        help="Workspace directory for resume files (default: current directory)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--prompt", "-p",
        help="Run a single prompt and exit (non-interactive mode)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Verbose output (show tool executions)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode (minimal output)",
    )
    
    args = parser.parse_args()
    
    # Load config
    try:
        llm_config = load_config(args.config)
    except FileNotFoundError:
        console.print(f"⚠️ Config file not found: {args.config}", style="yellow")
        console.print("Using default configuration. Set GEMINI_API_KEY environment variable.", style="dim")
        
        # Try to get API key from environment (priority: Gemini > OpenAI)
        import os
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        
        if os.environ.get("GEMINI_API_KEY"):
            api_base = "https://generativelanguage.googleapis.com/v1beta"
            model = "gemini-2.0-flash"
        else:
            api_base = "https://api.openai.com/v1"
            model = "gpt-4o"
        
        llm_config = LLMConfig(
            api_key=api_key,
            api_base=api_base,
            model=model,
        )
    
    # Create agent
    agent_config = AgentConfig(
        workspace_dir=args.workspace,
        verbose=not args.quiet,
    )
    
    agent = ResumeAgent(llm_config=llm_config, agent_config=agent_config)
    
    # Run
    if args.prompt:
        # Non-interactive mode
        async def run_once():
            response = await agent.run(args.prompt)
            console.print(Markdown(response))
        
        asyncio.run(run_once())
    else:
        # Interactive mode
        asyncio.run(run_interactive(agent))


if __name__ == "__main__":
    main()
