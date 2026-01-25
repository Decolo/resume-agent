#!/bin/bash
# Quick setup script for Resume Agent

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Resume Agent - Quick Setup Script                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "✅ uv is installed"
echo ""

# Sync dependencies
echo "📦 Installing dependencies..."
uv sync
echo "✅ Dependencies installed"
echo ""

# Create workspace directory
echo "📁 Creating workspace directory..."
mkdir -p workspace
echo "✅ Workspace created at ./workspace"
echo ""

# Check for resume file
echo "📄 Looking for resume files..."
if [ -f "resume.pdf" ] || [ -f "resume.docx" ] || [ -f "resume.md" ]; then
    echo "✅ Resume file found in current directory"
elif [ -f "workspace/resume.pdf" ] || [ -f "workspace/resume.docx" ] || [ -f "workspace/resume.md" ]; then
    echo "✅ Resume file found in workspace directory"
else
    echo "⚠️  No resume file found. Please copy your resume to:"
    echo "   - Current directory: ./resume.pdf"
    echo "   - Or workspace: ./workspace/resume.pdf"
    echo ""
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    Ready to Start!                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "To start the Resume Agent, run:"
echo ""
echo "  Interactive mode (recommended):"
echo "    resume-agent"
echo ""
echo "  Or with workspace:"
echo "    resume-agent --workspace ./workspace"
echo ""
echo "  Or single prompt:"
echo "    resume-agent --prompt \"Parse my resume and analyze it\""
echo ""
echo "For more help, run:"
echo "    resume-agent --help"
echo ""
