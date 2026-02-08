# Justfile for dekl - Declarative Arch Linux system manager
# https://just.systems/man/en/index.html

# ----------------
# Global Variables
# ----------------

REQUIRED_CMDS := "uv gh"
version := `grep '__version__' dekl/__init__.py | cut -d"'" -f2`
EXPECTED_USER := "Keithsel"

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
alias gd := gh-doctor
alias bb := build-binary
alias bn := build-nuitka
alias sc := symlink-config
alias pc := pre-commit
alias v := version
alias b := bump
alias rel := release

# ----------------
# Utility Commands
# ----------------

# List available commands
[group('meta')]
help:
  @just --list --unsorted

# Check GitHub CLI setup
[group('meta')]
gh-doctor:
  #!/usr/bin/env sh
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh not installed"
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh not authenticated. Run 'gh auth login'"
    exit 1
  fi
  USER=$(gh api user --jq .login 2>/dev/null)
  if [ -z "$USER" ]; then
    echo "Failed to get gh user"
    exit 1
  fi
  echo "gh authenticated as $USER"
  if [ "$USER" != "{{EXPECTED_USER}}" ]; then
    echo "gh user is $USER, expected {{EXPECTED_USER}}"
    exit 1
  fi

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
  uv run python -m nuitka --onefile --output-filename=dekl --output-dir=dist --assume-yes-for-downloads --lto=yes --follow-imports --include-package=rich --include-package-data=rich dekl

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
    #!/usr/bin/env bash
    sed -i "s/__version__ = '.*'/__version__ = '{{new_version}}'/" dekl/__init__.py
    git add dekl/__init__.py
    git commit -m "release: v{{new_version}}"
    git push
    echo "Bumped to v{{new_version}}"

# Full release (usage: just release 0.2.0 path/to/arch-repo path/to/aur)
[group('release')]
release new_version arch_repo_dir aur_dir: gh-doctor (bump new_version)
    #!/usr/bin/env bash
    set -euo pipefail

    echo ">>> Triggering GitHub Release workflow..."
    gh workflow run release.yml -f version={{new_version}}

    echo ">>> Waiting for release workflow..."
    sleep 5
    gh run watch --exit-status

    echo ">>> Updating arch-repo..."
    cd "{{arch_repo_dir}}"
    sed -i "s/^pkgver=.*/pkgver={{new_version}}/" PKGBUILDS/dekl/PKGBUILD

    rm -f x86_64/dekl-*.pkg.tar.zst*

    cd PKGBUILDS/dekl
    makepkg -sr --sign --noconfirm
    mv *.pkg.tar.zst *.pkg.tar.zst.sig ../../x86_64/
    cd ../..

    cd x86_64
    rm -f keithsel.db* keithsel.files*
    repo-add --verify --sign keithsel.db.tar.gz *.pkg.tar.zst
    cd ..

    git add -A
    git commit -m "dekl: update to {{new_version}}"
    git push

    echo ">>> Updating AUR..."
    cp PKGBUILDS/dekl/PKGBUILD "{{aur_dir}}/"
    cd "{{aur_dir}}"
    makepkg --printsrcinfo > .SRCINFO
    git add PKGBUILD .SRCINFO
    git commit -m "Update to {{new_version}}"
    git push

    echo ">>> Done! Released v{{new_version}}"
