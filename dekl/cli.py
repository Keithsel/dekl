import socket
import typer
import yaml

from dekl.constants import CONFIG_DIR, HOSTS_DIR, MODULES_DIR, CONFIG_FILE
from dekl.config import get_declared_packages, get_host_name
from dekl.packages import (
    get_explicit_packages,
    get_orphan_packages,
    install_packages,
    remove_packages,
)
from dekl.output import info, success, warning, error, added, removed, header

app = typer.Typer(name='dekl', help='Declarative Arch Linux system manager')


@app.command()
def init(host: str = typer.Option(None, '--host', '-h', help='Host name (defaults to your hostname)')):
    """Scaffold a new dekl configuration."""
    if host is None:
        host = socket.gethostname()

    HOSTS_DIR.mkdir(parents=True, exist_ok=True)
    MODULES_DIR.mkdir(parents=True, exist_ok=True)
    (MODULES_DIR / 'base').mkdir(exist_ok=True)

    if not CONFIG_FILE.exists():
        config = {'host': host}
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f)
        success(f'Created {CONFIG_FILE}')
    else:
        info(f'Config already exists: {CONFIG_FILE}')

    host_file = HOSTS_DIR / f'{host}.yaml'
    if not host_file.exists():
        host_config = {
            'aur_helper': 'paru',
            'modules': ['base'],
        }
        with open(host_file, 'w') as f:
            yaml.dump(host_config, f)
        success(f'Created {host_file}')
    else:
        info(f'Host config already exists: {host_file}')

    base_module = MODULES_DIR / 'base' / 'module.yaml'
    if not base_module.exists():
        module = {'packages': ['base']}
        with open(base_module, 'w') as f:
            yaml.dump(module, f)
        success(f'Created {base_module}')
    else:
        info(f'Base module already exists: {base_module}')

    gitignore = CONFIG_DIR / '.gitignore'
    if not gitignore.exists():
        with open(gitignore, 'w') as f:
            f.write('state.yaml\n')
            f.write('modules/system/\n')
        success(f'Created {gitignore}')

    header(f'Initialized dekl for host: {host}')
    info('')
    info('Next steps:')
    info("  1. Run 'dekl merge' to capture current system state")
    info('  2. Add your own modules in ~/.config/dekl-arch/modules/')
    info("  3. Run 'dekl status' to see the diff")
    info("  4. Run 'dekl sync' to apply changes")


@app.command()
def merge():
    """Capture current system state into system module."""
    system_dir = MODULES_DIR / 'system'
    system_dir.mkdir(parents=True, exist_ok=True)

    packages = sorted(get_explicit_packages())

    module = {'packages': packages}
    module_path = system_dir / 'module.yaml'

    with open(module_path, 'w') as f:
        yaml.dump(module, f, default_flow_style=False)

    success(f'Captured {len(packages)} packages into system module')
    info('')
    info("Add 'system' to your host config:")
    info('  modules:')
    info('    - system')


@app.command()
def status():
    """Show diff between declared and current state."""
    host = get_host_name()

    declared = set(get_declared_packages())
    installed = get_explicit_packages()
    orphans = get_orphan_packages()

    to_install = declared - installed
    to_remove = (installed - declared) | orphans

    info(f'Host: {host}')
    info(f'Declared: {len(declared)} packages')
    info(f'Installed: {len(installed)} explicit, {len(orphans)} orphans')

    if to_install:
        header('Would install:')
        for pkg in sorted(to_install):
            added(pkg)

    if to_remove:
        header('Would remove:')
        for pkg in sorted(to_remove):
            removed(pkg)

    if not to_install and not to_remove:
        success('System is in sync')


@app.command()
def sync(dry_run: bool = typer.Option(False, '--dry-run', '-n', help='Show what would be done')):
    """Sync system to declared state."""
    declared = set(get_declared_packages())
    installed = get_explicit_packages()
    orphans = get_orphan_packages()

    to_install = declared - installed
    to_remove = (installed - declared) | orphans

    if not to_install and not to_remove:
        success('System is in sync')
        return

    if to_install:
        header('Installing:')
        for pkg in sorted(to_install):
            added(pkg)

    if to_remove:
        header('Removing:')
        for pkg in sorted(to_remove):
            removed(pkg)

    if dry_run:
        warning('Dry run - no changes made')
        return

    info('')

    if to_install:
        if not install_packages(list(to_install)):
            error('Failed to install packages')
            raise typer.Exit(1)

    if to_remove:
        if not remove_packages(list(to_remove)):
            error('Failed to remove packages')
            raise typer.Exit(1)

    success('Sync complete')


def main():
    app()


if __name__ == '__main__':
    main()
