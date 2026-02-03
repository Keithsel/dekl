# dekl

Declarative package and dotfile management for Arch Linux.

dekl allows you to define your system's packages and configuration in YAML files, making your Arch Linux setup reproducible and version-controllable.

> **⚠️ Alpha Development Notice**
>
> This project is in early alpha stage. Features may be incomplete, unstable, or subject to breaking changes. Use at your own risk and expect bugs.

## Philosophy

dekl follows the [Repeatable Arch Manifesto](https://gist.github.com/Keithsel/9974f329267d16c78a6f7921eb24e740): declare intent, converge state, move on.

Your system matches your declaration, nothing more. Every package belongs to a module. Simplicity over features.

## Installation

Build from source: See the Development section for building instructions.

## Quick Start

1. Initialize dekl for your host:

   ```bash
   dekl init
   ```

   This creates the configuration directory `~/.config/dekl-arch/` with basic structure.

2. Capture your current system state:

   ```bash
   dekl merge
   ```

   This creates a `system` module with all currently installed packages.

3. Check the status:

   ```bash
   dekl status
   ```

   See what packages would be installed or removed.

4. Sync your system:

   ```bash
   dekl sync
   ```

   Apply the changes. Use `--dry-run` to preview first.

## Configuration

dekl uses YAML files in `~/.config/dekl-arch/`.

- `config.yaml`: Main config with host name.
- `hosts/{hostname}.yaml`: Host-specific config with modules and AUR helper.
- `modules/`: Directory with module definitions.

Each module is a directory with `module.yaml` containing a list of packages.

Example module (`modules/my-tools/module.yaml`):

```yaml
packages:
  - firefox
  - vim
  - git
  - htop
```

Add modules to your host config (`hosts/{hostname}.yaml`):

```yaml
aur_helper: paru  # or yay
modules:
  - base
  - system
  - my-tools
```

## Commands

- `dekl init [host]`: Initialize config for a host (defaults to current hostname)
- `dekl merge`: Capture current explicit packages into a `system` module
- `dekl status`: Show diff between declared and installed packages
- `dekl sync [--dry-run]`: Apply changes to sync system with declared state

## Development

This project uses [just](https://just.systems/) for task running.

```bash
# Install dependencies
just install

# Run the CLI
just run

# Lint code
just lint

# Show available tasks
just help
```

### Building Standalone Binaries

```bash
# PyInstaller (faster to build, larger size, slower startup)
just build-binary

# Nuitka (slower to build, smaller size, faster startup)
just build-nuitka
```
