#!/bin/bash

set -e

REPO_URL="https://github.com/nayanjaiswal1/better-way-to-ship"
INSTALL_DIR="${1:-$HOME/.config/opencode/skills}"

echo "🚀 Better Way To Ship - One-Click Setup"
echo "======================================="

# Detect if running in a project
if [ -d ".git" ]; then
    INSTALL_TYPE="project"
    TARGET_DIR=".opencode/skills"
    echo "📁 Project detected - installing to .opencode/skills/"
else
    INSTALL_TYPE="global"
    TARGET_DIR="$INSTALL_DIR"
    echo "🌍 Global install - skills will be available to all projects"
fi

# Check for OpenCode
if ! command -v opencode &> /dev/null; then
    echo "⚠️  OpenCode not found. Install: curl -fsSL https://opencode.ai/install | bash"
    exit 1
fi

# Clone to temp directory
TEMP_DIR=$(mktemp -d)
echo "📥 Cloning repository..."
git clone --depth 1 "$REPO_URL" "$TEMP_DIR/repo" 2>/dev/null || {
    echo "❌ Failed to clone repo"
    exit 1
}

# Create directory
mkdir -p "$TARGET_DIR"

# Copy skills
echo "📋 Installing skills..."
cp -r "$TEMP_DIR/repo/.opencode/skills/"* "$TARGET_DIR/"

# Create AGENTS.md if not exists
if [ ! -f "AGENTS.md" ]; then
    echo "📄 Adding AGENTS.md..."
    cp "$TEMP_DIR/repo/AGENTS.md" .
fi

# Setup MCP server
read -p "🔧 Setup MCP server for OpenCode? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Get the script directory for proper path
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    MCP_SOURCE="$TEMP_DIR/repo/mcp-server/dist/index.js"
    MCP_DEST="$HOME/.local/bin/better-way-to-ship-mcp"
    
    mkdir -p "$(dirname "$MCP_DEST")"
    cp "$MCP_SOURCE" "$MCP_DEST"
    chmod +x "$MCP_DEST"
    
    # Create config snippet
    CONFIG_FILE="${HOME}/.config/opencode/opencode.json"
    mkdir -p "$(dirname "$CONFIG_FILE")"
    
    if [ -f "$CONFIG_FILE" ]; then
        # Backup and add to existing config
        cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
        echo "📝 Added MCP server to existing config (backup: ${CONFIG_FILE}.backup)"
    else
        # Create new config
        cat > "$CONFIG_FILE" << 'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "better-way-to-ship": {
      "type": "local",
      "command": ["node", "/home/nayan/.local/bin/better-way-to-ship-mcp"]
    }
  }
}
EOF
        echo "📝 Created OpenCode config at $CONFIG_FILE"
    fi
    echo "✅ MCP server installed to $MCP_DEST"
fi

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "======================================="
echo "✅ Setup complete!"
echo ""
echo "📚 Available skills:"
for skill in "$TARGET_DIR"/*/; do
    NAME=$(basename "$skill")
    echo "   - $NAME"
done
echo ""
echo "🚀 Usage:"
echo "   opencode"
echo "   skill <skill-name>  # e.g., skill django-reviewer"
echo ""
echo "🌐 Repo: $REPO_URL"
