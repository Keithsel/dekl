from pathlib import Path

from dekl.constants import MODULES_DIR
from dekl.config import load_host_config, load_module
from dekl.output import info, warning, error, added


def get_module_dotfiles(module_name: str) -> list[dict]:
    """Get dotfiles config for a module.

    Returns list of {source: Path, target: Path}
    """
    module = load_module(module_name)
    module_path = MODULES_DIR / module_name
    dotfiles_dir = module_path / 'dotfiles'

    if not dotfiles_dir.exists():
        return []

    dotfiles_config = module.get('dotfiles')

    if dotfiles_config is None:
        warning(f"Module '{module_name}' has dotfiles/ but no dotfiles declaration")
        return []

    # Explicitly disabled
    if dotfiles_config is False:
        return []

    home = Path.home()
    config_dir = home / '.config'

    if dotfiles_config is True:
        overrides = {}
    elif isinstance(dotfiles_config, dict):
        overrides = dotfiles_config
    else:
        warning(f"Module '{module_name}' has invalid dotfiles config")
        return []

    result = []

    for item in dotfiles_dir.iterdir():
        source = item
        name = item.name

        if name in overrides:
            # Explicit target from map
            target = Path(overrides[name]).expanduser()
        else:
            # Default to ~/.config/{name}
            target = config_dir / name

        result.append({
            'source': source,
            'target': target,
            'module': module_name,
        })

    return result


def get_all_dotfiles() -> list[dict]:
    """Get all dotfiles from all enabled modules."""
    host = load_host_config()
    all_dotfiles = []

    for module_name in host.get('modules', []):
        all_dotfiles.extend(get_module_dotfiles(module_name))

    return all_dotfiles


def check_conflicts(dotfiles: list[dict]) -> list[dict]:
    """Check for dotfile conflicts. Returns list of conflicts."""
    targets = {}
    conflicts = []

    for df in dotfiles:
        target = str(df['target'])
        if target in targets:
            conflicts.append({
                'target': target,
                'modules': [targets[target], df['module']],
            })
        else:
            targets[target] = df['module']

    return conflicts


def show_dotfiles_status():
    """Display the status of all dotfiles."""
    dotfiles = get_all_dotfiles()

    if not dotfiles:
        info('No dotfiles configured')
        return

    conflicts = check_conflicts(dotfiles)
    if conflicts:
        error('Dotfile conflicts detected:')
        for c in conflicts:
            error(f'  {c["target"]} claimed by: {", ".join(c["modules"])}')
        return

    for df in dotfiles:
        source = df['source']
        target = df['target']

        if target.is_symlink() and target.resolve() == source.resolve():
            info(f'{source.name} -> {target} (synced)')
        else:
            added(f'{source.name} -> {target} (needs sync)')


def sync_dotfiles(dry_run: bool = False) -> bool:
    """Sync all dotfiles. Returns True if successful."""
    dotfiles = get_all_dotfiles()

    if not dotfiles:
        info('No dotfiles to sync')
        return True

    conflicts = check_conflicts(dotfiles)
    if conflicts:
        error('Dotfile conflicts detected:')
        for c in conflicts:
            error(f'  {c["target"]} claimed by: {", ".join(c["modules"])}')
        return False

    for df in dotfiles:
        source = df['source']
        target = df['target']

        # Symlink already correct
        if target.is_symlink() and target.resolve() == source.resolve():
            continue

        if dry_run:
            added(f'{source.name} -> {target}')
            continue

        if target.exists() and not target.is_symlink():
            backup = target.with_suffix(target.suffix + '.bak')
            warning(f'Backing up {target} to {backup}')
            target.rename(backup)

        if target.is_symlink():
            target.unlink()

        target.parent.mkdir(parents=True, exist_ok=True)

        target.symlink_to(source)
        added(f'{source.name} -> {target}')

    return True
