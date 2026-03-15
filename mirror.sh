#!/usr/bin/env bash
set -euo pipefail

# Tom Lehrer Songs Mirror — Quick Start
# ======================================
# This script creates a venv, installs deps, and runs the scraper.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo ""
echo "  ♫ Tom Lehrer Songs Mirror — Setup"
echo "  =================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python 3 is required. Install it first."
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "  → Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "  → Installing Python dependencies..."
pip install --upgrade pip -q 2>/dev/null
pip install requests beautifulsoup4 -q

# Run scraper
echo ""
echo "  → Running scraper (this may take 30-60 minutes for all MP3s)..."
echo "    Tip: If interrupted, re-run with --resume to continue."
echo ""
python3 "$SCRIPT_DIR/scrape_mirror.py" "$@"

# Post-scrape reminder
echo ""
echo "  ──────────────────────────────────────────────"
echo "  Before deploying, remember to:"
echo ""
echo "  1. Edit site/about-this-mirror.html"
echo "     → Replace YOUR_USERNAME with your GitHub username"
echo ""
echo "  2. Push to GitHub:"
echo "     git init"
echo "     git add -A"
echo "     git commit -m 'Initial mirror of tomlehrersongs.com'"
echo "     git remote add origin git@github.com:YOUR_USERNAME/tomlehrersongs-mirror.git"
echo "     git push -u origin main"
echo ""
echo "  3. Deploy site/ to your hosting (Cloudflare Pages, GitHub Pages, etc.)"
echo "  ──────────────────────────────────────────────"
