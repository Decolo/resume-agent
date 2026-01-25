#!/bin/bash
# Resume Agent Launcher Script
# Makes it easy to start the Resume Agent with your workspace

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default workspace
WORKSPACE="${1:-.}"

# Show banner
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    📄 Resume Agent                        ║"
echo "║         AI-powered Resume Modification Assistant          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Workspace: $WORKSPACE"
echo ""

# Check if workspace exists
if [ ! -d "$WORKSPACE" ]; then
    echo "❌ Error: Workspace directory not found: $WORKSPACE"
    exit 1
fi

# Check if resume files exist
if ! ls "$WORKSPACE"/*.{pdf,docx,md,txt,json} 2>/dev/null | grep -q .; then
    echo "⚠️  No resume files found in $WORKSPACE"
    echo "Supported formats: .pdf, .docx, .md, .txt, .json"
    echo ""
    echo "To add your resume, run:"
    echo "  cp /path/to/your/resume.pdf $WORKSPACE/"
    echo ""
fi

# Start the agent
cd "$SCRIPT_DIR"
uv run resume-agent --workspace "$WORKSPACE"
