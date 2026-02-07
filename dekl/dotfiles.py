from pathlib import Path

from dekl.constants import MODULES_DIR
from dekl.config import load_host_config, load_module
from dekl.output import info, warning, error, added


def get_module_dotfiles(module_name: str) -> list[dict]:
    """Get dotfiles config for a module.

    Returns list of {source: Path, target: Path, module: str}
    """
    module = load_module(module_name)
    module_path = MODULES_DIR / module_name
    dotfiles_dir = module_path / 'dotfiles'

    dotfiles_config = module.get('dotfiles')

    if dotfiles_config is None:
        if dotfiles_dir.exists():
            warning(f"Module '{module_name}' has dotfiles/ but no dotfiles declaration")
        return []

    # Explicitly disabled
    if dotfiles_config is False:
        return []

    if not dotfiles_dir.exists():
        warning(f"Module '{module_name}' declares dotfiles but has no dotfiles/ directory")
        return []

    home = Path.home()
    config_dir = home / '.config'
    result = []

    if dotfiles_config is True:
        for item in dotfiles_dir.iterdir():
            result.append({
                'source': item,
                'target': config_dir / item.name,
                'module': module_name,
            })
        return result

    if not isinstance(dotfiles_config, dict):
        warning(f"Module '{module_name}' has invalid dotfiles config (must be true, false, or dict)")
        return []

    for source_key, target_str in dotfiles_config.items():
        # Trailing slash indicates directory
        is_dir = source_key.endswith('/')
        source_name = source_key.rstrip('/')

        source = dotfiles_dir / source_name
        target = Path(target_str).expanduser()

        if not source.exists():
            warning(f"Module '{module_name}' dotfile not found: {source}")
            continue

        if is_dir and not source.is_dir():
            warning(f"Module '{module_name}' dotfile '{source_key}' has trailing slash but is not a directory")
            continue

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
