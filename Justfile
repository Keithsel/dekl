# Justfile for dekl - Declarative Arch Linux system manager
# https://just.systems/man/en/index.html

# ----------------
# Global Variables
# ----------------

REQUIRED_CMDS := "uv"
version := `grep '__version__' dekl/__init__.py | cut -d"'" -f2`

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
  uv run python -m nuitka --onefile --output-filename=dekl --output-dir=dist --assume-yes-for-downloads --lto=yes dekl

# -----------------
# Release Commands
# -----------------

# Show current version
[group('release')]
version:
    @echo {{version}}

# Bump version (usage: just bump 0.2.0)
[group('release')]
bump new_version:
    #!/usr/bin/env sh
    sed -i "s/__version__ = '.*'/__version__ = '{{new_version}}'/" dekl/__init__.py
    git add dekl/__init__.py
    git commit -m "release: v{{new_version}}"
    git push
    echo "Now go to GitHub Actions and run the Release workflow with version {{new_version}}"

# Update AUR PKGBUILD (usage: just aur-update 0.1.0 path/to/aur/dekl)
aur-update new_version aur_dir:
    #!/bin/bash
    set -euo pipefail

    SHA256=$(curl -sL https://github.com/Keithsel/dekl/releases/download/v{{new_version}}/dekl | sha256sum | cut -d' ' -f1)

    cd "{{aur_dir}}"

    sed -i "s/^pkgver=.*/pkgver={{new_version}}/" PKGBUILD
    sed -i "s/^sha256sums=.*/sha256sums=('$SHA256')/" PKGBUILD

    makepkg --printsrcinfo > .SRCINFO

    echo "Updated PKGBUILD:"
    grep -E '^(pkgver|sha256sums)=' PKGBUILD
    echo ""
    echo "Test with: cd {{aur_dir}} && makepkg -si"
    echo "Push with: cd {{aur_dir}} && git add -A && git commit -m 'Update to {{new_version}}' && git push"
