# Justfile for dekl - Declarative Arch Linux system manager
# https://just.systems/man/en/index.html

# ----------------
# Global Variables
# ----------------

REQUIRED_CMDS := "uv"

# --------------
# Setup Commands
# --------------

# Default target
[group('meta')]
default: help doctor install

# -------
# Aliases
# -------

alias i := install
alias h := help
alias r := run
alias l := lint
alias f := format
alias c := clean
alias do := doctor
alias bb := build-binary
alias bn := build-nuitka
alias sc := symlink-config
alias pc := pre-commit

# ----------------
# Utility Commands
# ----------------

# List available commands
[group('meta')]
help:
  @just --list --unsorted

# Check availability of commands
[group('meta')]
doctor:
  #!/usr/bin/env sh
  CMDS="{{REQUIRED_CMDS}}"
  for cmd in $CMDS; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "$cmd not installed"; exit 1; }
  done
  echo "All required commands: $(echo $CMDS | tr ' ' ',') are available."

# ---------------------
# Installation Commands
# ---------------------

# Install dependencies
[group('setup')]
install: doctor
  #!/usr/bin/env sh
  if [ ! -d ".venv" ]; then
    echo ".venv not found. Creating virtual environment..."
    uv sync
  else
    echo ".venv already exists."
  fi

# ------------
# Run Commands
# ------------

# Run dekl CLI
[group('run')]
run *args: install
  #!/usr/bin/env sh
  if [ "{{args}}" = "" ]; then
    uv run python -m dekl --help
  else
    uv run python -m dekl {{args}}
  fi

# -------------
# Lint Commands
# -------------

# Lint and format code (ruff)
[group('lint')]
lint: install
  #!/usr/bin/env sh
  if [ -f ".ruff.toml" ]; then
    uv run ruff check . --config .ruff.toml --fix --unsafe-fixes
    uv run ruff format . --config .ruff.toml
  else
    echo "No .ruff.toml found. Skipping lint."
  fi

# Format code only
[group('lint')]
format: install
  #!/usr/bin/env sh
  if [ -f ".ruff.toml" ]; then
    uv run ruff format . --config .ruff.toml
  else
    echo "No .ruff.toml found. Skipping format."
  fi

# Run pre-commit hooks
[group('lint')]
pre-commit: install
  #!/usr/bin/env sh
  uv run prek run --all-files --verbose --show-diff-on-failure

# -------
# Cleanup
# -------

# Clean up Python caches and build artifacts
[group('cleanup')]
clean:
  #!/usr/bin/env sh
  echo "Cleaning Python caches..."
  find . -type d -name "__pycache__" -exec rm -rf {} + || true
  find . -type d -name "*.egg-info" -exec rm -rf {} + || true
  find . -type d -name ".pytest_cache" -exec rm -rf {} + || true
  find . -type d -name ".ruff_cache" -exec rm -rf {} + || true
  find . -type d -name "*.pyc" -exec rm -rf {} + || true
  echo "Cleanup complete."

# -----------------
# Config Commands
# -----------------

# Create symlink to config directory
[group('config')]
symlink-config:
  #!/usr/bin/env sh
  ln -s ~/.config/dekl-arch ./config

# Build standalone executable with PyInstaller
[group('build')]
build-binary: install
  #!/usr/bin/env sh
  uv sync --group dev
  uv run pyinstaller --onefile --name dekl dekl

# Build compiled binary with Nuitka
[group('build')]
build-nuitka: install
  #!/usr/bin/env sh
  uv sync --group dev
  uv run python -m nuitka --onefile --output-filename=dekl --output-dir=dist --assume-yes-for-downloads --lto=yes -m dekl
