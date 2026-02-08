# dekl

Declarative package and dotfile management for Arch Linux.

[![dekl](https://img.shields.io/aur/version/dekl?color=1793d1&label=dekl&logo=arch-linux&style=for-the-badge)](https://aur.archlinux.org/packages/dekl/)
[![dekl-git](https://img.shields.io/aur/version/dekl-git?color=1793d1&label=dekl-git&logo=arch-linux&style=for-the-badge)](https://aur.archlinux.org/packages/dekl-git/)

`dekl` allows you to define your system's packages and configuration in YAML files, making your Arch Linux setup reproducible and version-controllable.

> **⚠️ Alpha Development Notice**
>
> This project is in early alpha stage. Features may be incomplete, unstable, or subject to breaking changes. Use at your own risk and expect bugs.

## Philosophy

`dekl` follows the [Repeatable Arch Manifesto](https://gist.github.com/Keithsel/9974f329267d16c78a6f7921eb24e740): declare intent, converge state, move on.

Your system matches your declaration, nothing more. Every package belongs to a module. Simplicity over features. Safety first - destructive operations require confirmation by default.

## Todo

- [x] Confirmation prompts before destructive operations
- [ ] `--json` output for scripting
- [ ] Module dependencies/conflicts
- [ ] Dotfile pruning when modules are disabled
- [ ] Wiki

## Installation

Install from the Arch User Repository:

**Stable release:**

```bash
# Using paru
paru -S dekl
```

**Development version (tracks git master):**

```bash
# Using paru
paru -S dekl-git
```

Or build from source: See the Development section for building instructions.

## Quick Start

1. Initialize `dekl` for your host:

   ```bash
   dekl init
   ```

   This creates the configuration directory `~/.config/dekl-arch/` with basic structure and prompts you to select an AUR helper (paru recommended, yay, or pacman only).

2. Capture your current system state:

   ```bash
   dekl merge
   ```

   This creates a `system` module with all currently installed packages. It will be gitignored by default.

3. Check the status:

   ```bash
   dekl status
   ```

   See what packages, services, and dotfiles would be installed, enabled, or removed.

4. Sync your system:

   ```bash
   dekl sync
   ```

   Apply the changes to packages, services, and dotfiles. Use `--dry-run` to preview first. Use `--yes` to skip confirmation prompts for removals. Use `--prune` or `--no-prune` to control removal of undeclared packages (default: prune).

## Configuration

`dekl` uses YAML files in `~/.config/dekl-arch/`.

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

Modules can also declare services to enable:

```yaml
packages:
  - firefox
  - vim

services:
  - sshd
  - docker
  - name: my-user-service
    user: true
```

Services can be strings or objects with `name`, `user` (for user services), and `enabled` (defaults to true).

Add modules to your host config (`hosts/{hostname}.yaml`):

```yaml
aur_helper: paru  # paru (recommended), yay, or pacman
auto_prune: true  # Remove undeclared packages (default: true)
modules:
  - base
  - system
  - my-tools
```

## Directory Structure

```
~/.config/dekl-arch/
├── config.yaml              # Points to host
├── hosts/
│   └── myhost.yaml          # Modules list, AUR helper
├── modules/
│   ├── base/
│   │   └── module.yaml      # Core packages
│   ├── neovim/
│   │   ├── module.yaml      # Packages, hooks, dotfiles
│   │   ├── dotfiles/
│   │   │   └── nvim/        # -> ~/.config/nvim/
│   │   └── scripts/
│   │       └── setup.sh
│   └── system/              # Generated, gitignored
│       └── module.yaml
└── state.yaml               # Gitignored, tracks hook runs
```

### Hooks

Modules and hosts can define hooks: scripts that run at specific points.

Module hooks: `pre` (before sync), `post` (after sync).

Host hooks: `pre_sync`, `post_sync`, `pre_update`, `post_update`.

Example module with hooks (`modules/neovim/module.yaml`):

```yaml
packages:
  - neovim

hooks:
  post: scripts/setup.sh
```

Example host config with hooks (`hosts/{hostname}.yaml`):

```yaml
modules:
  - base
  - system
  - my-tools

hooks:
  post_sync: scripts/restart-services.sh
```

Hook scripts can be configured with options:

```yaml
hooks:
  post:
    run: scripts/setup.sh
    always: true  # Run every time, not just once
    root: true    # Run with sudo
```

### Dotfiles

Modules can include dotfiles to symlink into your home directory.

Create a `dotfiles/` directory in the module with your config files.

Supported formats:

```yaml
# Symlink all to ~/.config/
dotfiles: true

# Disabled
dotfiles: false

# Explicit mapping
dotfiles:
  nvim: ~/.config/nvim
  fonts: ~/.local/share/fonts
  conf: ~/.config/app/conf       # auto-detect
  conf/: ~/.config/app/conf.d/   # explicit directory
```

- `dotfiles: true`: Symlink all files and directories in `dotfiles/` to `~/.config/`
- `dotfiles: false`: Disable dotfiles for this module
- Dict format: Map source files/directories to target paths
    - Trailing slash on source indicates directory (e.g., `conf/`)
    - Targets are expanded with `~` for home directory

## Commands

- `dekl init [host]`: Initialize config for a host (defaults to current hostname) and select AUR helper
- `dekl merge [--services] [--dry-run]`: Capture current explicit packages into a `system` module
- `dekl status [--prune/--no-prune]`: Show diff between declared and installed packages, services, and dotfiles
- `dekl sync [--dry-run] [--prune/--no-prune] [--yes] [--no-hooks] [--no-dotfiles] [--no-services]`: Apply changes to sync system with declared state
- `dekl update [--dry-run] [--no-hooks]`: Upgrade system packages
- `dekl add <package>... [-m module] [--dry-run]`: Add package(s) to a module and install them
- `dekl drop <package>... [--dry-run]`: Remove package(s) from all modules and uninstall them
- `dekl enable <service>... [-m module] [--user] [--dry-run]`: Add service(s) to a module and enable them
- `dekl disable <service>... [-m module] [--remove] [--user] [--dry-run]`: Disable service(s) (set enabled: false or remove from module)
- `dekl hook list`: List all hooks and their status
- `dekl hook run <name>`: Manually run a hook
- `dekl hook reset <name>`: Reset a hook to run again on next sync

## See Also

- [Repeatable Arch Manifesto](https://gist.github.com/Keithsel/9974f329267d16c78a6f7921eb24e740) - The philosophy behind dekl
- [rebos](https://gitlab.com/Oglo12/rebos) - Bring repeatable system configuration to any Linux distribution
- [dcli](https://gitlab.com/theblackdon/dcli) - Declarative config tool for Arch Linux

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

## Release

1. Run the release command:

   ```bash
   just release 0.2.0
   ```

   This will bump the version, commit, push, trigger the GitHub release workflow, and wait for it to complete.

2. Review and publish the draft release on GitHub.

3. Update the repos:

   ```bash
   just update-repos 0.2.0 ~repo ~aur
   ```
