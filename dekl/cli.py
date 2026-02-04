import socket
import typer
import yaml

from dekl import __version__
from dekl.constants import CONFIG_DIR, HOSTS_DIR, MODULES_DIR, CONFIG_FILE
from dekl.config import get_declared_packages, get_host_name, load_host_config
from dekl.packages import (
    get_explicit_packages,
    get_orphan_packages,
    install_packages,
    remove_packages,
    upgrade_system,
)
from dekl.dotfiles import sync_dotfiles
from dekl.services import sync_services, enable_service, disable_service
from dekl.hooks import (
    run_module_hook,
    run_host_hook,
    reset_hook,
    list_hooks,
    force_run_hook,
)
from dekl.output import info, success, warning, error, added, removed, header

app = typer.Typer(name='dekl', help='Declarative Arch Linux system manager')
hook_app = typer.Typer(help='Manage hooks')
app.add_typer(hook_app, name='hook')


def version_callback(value: bool):
    if value:
        typer.echo(f'dekl {__version__}')
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, '--version', '-v', callback=version_callback, is_eager=True, help='Show version'
    ),
):
    """Declarative Arch Linux system manager."""
    pass


@app.command()
def init(host: str = typer.Option(None, '--host', '-H', help='Host name (defaults to hostname)')):
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
def sync(
    dry_run: bool = typer.Option(False, '--dry-run', '-n', help='Show what would be done'),
    no_hooks: bool = typer.Option(False, '--no-hooks', help='Skip all hooks'),
    no_dotfiles: bool = typer.Option(False, '--no-dotfiles', help='Skip dotfiles sync'),
    no_services: bool = typer.Option(False, '--no-services', help='Skip services sync'),
):
    """Sync system to declared state."""
    host_config = load_host_config()
    modules = host_config.get('modules', [])

    # Host pre_sync hook
    if not no_hooks:
        if not run_host_hook('pre_sync', dry_run):
            error('Host pre_sync hook failed')
            raise typer.Exit(1)

        # Module pre hooks
        for module_name in modules:
            if not run_module_hook(module_name, 'pre', dry_run):
                error(f'Pre hook failed for {module_name}')
                raise typer.Exit(1)

    # Packages
    declared = set(get_declared_packages())
    installed = get_explicit_packages()
    orphans = get_orphan_packages()

    to_install = declared - installed
    to_remove = (installed - declared) | orphans

    if to_install:
        header('Installing:')
        for pkg in sorted(to_install):
            added(pkg)

    if to_remove:
        header('Removing:')
        for pkg in sorted(to_remove):
            removed(pkg)

    if not to_install and not to_remove:
        info('Packages in sync')

    if not dry_run:
        if to_install:
            if not install_packages(list(to_install)):
                error('Failed to install packages')
                raise typer.Exit(1)

        if to_remove:
            if not remove_packages(list(to_remove)):
                error('Failed to remove packages')
                raise typer.Exit(1)

    # Dotfiles
    if not no_dotfiles:
        header('Syncing dotfiles:')
        if not sync_dotfiles(dry_run):
            error('Failed to sync dotfiles')
            raise typer.Exit(1)

    # Services
    if not no_services:
        header('Syncing services:')
        if not sync_services(dry_run):
            error('Failed to sync services')
            raise typer.Exit(1)

    # Post hooks
    if not no_hooks:
        for module_name in modules:
            if not run_module_hook(module_name, 'post', dry_run):
                error(f'Post hook failed for {module_name}')
                raise typer.Exit(1)

        # Host post_sync hook
        if not run_host_hook('post_sync', dry_run):
            error('Host post_sync hook failed')
            raise typer.Exit(1)

    if dry_run:
        warning('Dry run - no changes made')
    else:
        success('Sync complete')


@app.command()
def update(
    dry_run: bool = typer.Option(False, '--dry-run', '-n', help='Show what would be done'),
    no_hooks: bool = typer.Option(False, '--no-hooks', help='Skip hooks'),
):
    """Upgrade system packages."""
    if not no_hooks:
        if not run_host_hook('pre_update', dry_run):
            error('Host pre_update hook failed')
            raise typer.Exit(1)

    if dry_run:
        info('Would run system upgrade')
    else:
        if not upgrade_system():
            error('System upgrade failed')
            raise typer.Exit(1)

    if not no_hooks:
        if not run_host_hook('post_update', dry_run):
            error('Host post_update hook failed')
            raise typer.Exit(1)

    if dry_run:
        warning('Dry run - no changes made')
    else:
        success('Update complete')


@app.command()
def add(
    package: str = typer.Argument(..., help='Package to add'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (default: local)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Add a package to a module and install it."""
    target_module = module or 'local'
    module_path = MODULES_DIR / target_module
    module_file = module_path / 'module.yaml'

    if not module_path.exists():
        module_path.mkdir(parents=True)
        module_data = {'packages': []}
        info(f'Creating module: {target_module}')

        host_name = get_host_name()
        host_file = HOSTS_DIR / f'{host_name}.yaml'
        with open(host_file) as f:
            host_config = yaml.safe_load(f) or {}
        if target_module not in host_config.get('modules', []):
            host_config.setdefault('modules', []).append(target_module)
            if not dry_run:
                with open(host_file, 'w') as f:
                    yaml.dump(host_config, f, default_flow_style=False)
            info(f'Added {target_module} to host config')
    else:
        with open(module_file) as f:
            module_data = yaml.safe_load(f) or {}

    packages = module_data.setdefault('packages', [])
    if package in packages:
        warning(f'{package} already in {target_module}')
        return

    packages.append(package)
    added(f'{package} → {target_module}')

    if dry_run:
        info('Dry run - no changes made')
        return

    with open(module_file, 'w') as f:
        yaml.dump(module_data, f, default_flow_style=False)

    if install_packages([package]):
        success(f'Installed {package}')
    else:
        error(f'Failed to install {package}')
        raise typer.Exit(1)


@app.command()
def drop(
    package: str = typer.Argument(..., help='Package to remove'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Remove a package from all modules and uninstall it."""
    host = load_host_config()
    found_in = []

    for module_name in host.get('modules', []):
        module_file = MODULES_DIR / module_name / 'module.yaml'
        if not module_file.exists():
            continue

        with open(module_file) as f:
            module_data = yaml.safe_load(f) or {}

        packages = module_data.get('packages', [])
        if package in packages:
            found_in.append(module_name)
            packages.remove(package)
            removed(f'{package} ← {module_name}')

            if not dry_run:
                with open(module_file, 'w') as f:
                    yaml.dump(module_data, f, default_flow_style=False)

    if not found_in:
        warning(f'{package} not found in any module')
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    if remove_packages([package]):
        success(f'Removed {package}')
    else:
        error(f'Failed to remove {package}')
        raise typer.Exit(1)


@app.command()
def enable(
    service: str = typer.Argument(..., help='Service to enable'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (default: local)'),
    user: bool = typer.Option(False, '--user', help='User service (systemctl --user)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Add a service to a module and enable it."""
    target_module = module or 'local'
    module_path = MODULES_DIR / target_module
    module_file = module_path / 'module.yaml'

    if not module_path.exists():
        module_path.mkdir(parents=True)
        module_data = {'services': []}
        info(f'Creating module: {target_module}')

        host_name = get_host_name()
        host_file = HOSTS_DIR / f'{host_name}.yaml'
        with open(host_file) as f:
            host_config = yaml.safe_load(f) or {}
        if target_module not in host_config.get('modules', []):
            host_config.setdefault('modules', []).append(target_module)
            if not dry_run:
                with open(host_file, 'w') as f:
                    yaml.dump(host_config, f, default_flow_style=False)
            info(f'Added {target_module} to host config')
    else:
        with open(module_file) as f:
            module_data = yaml.safe_load(f) or {}

    svc_name = service
    if not any(svc_name.endswith(s) for s in ['.service', '.socket', '.timer']):
        svc_name = f'{svc_name}.service'

    services = module_data.setdefault('services', [])
    for i, existing in enumerate(services):
        existing_name = existing if isinstance(existing, str) else existing.get('name', '')
        if not any(existing_name.endswith(s) for s in ['.service', '.socket', '.timer']):
            existing_name = f'{existing_name}.service'

        if existing_name == svc_name:
            if isinstance(existing, dict) and not existing.get('enabled'):
                services[i] = {'name': service, 'user': user, 'enabled': True} if user else service
                info(f'Re-enabling {svc_name} in {target_module}')
            else:
                warning(f'{svc_name} already enabled in {target_module}')
                return
            break
    else:
        if user:
            services.append({'name': service, 'user': True})
        else:
            services.append(service)
        added(f'{svc_name} → {target_module}')

    if dry_run:
        info('Dry run - no changes made')
        return

    with open(module_file, 'w') as f:
        yaml.dump(module_data, f, default_flow_style=False)

    user_flag = ' (user)' if user else ''
    if enable_service(svc_name, user):
        success(f'Enabled {svc_name}{user_flag}')
    else:
        error(f'Failed to enable {svc_name}')
        raise typer.Exit(1)


@app.command()
def disable(
    service: str = typer.Argument(..., help='Service to disable'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (searches all if not specified)'),
    remove: bool = typer.Option(False, '-r', '--remove', help='Remove from module instead of setting enabled: false'),
    user: bool = typer.Option(False, '--user', help='User service (systemctl --user)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Disable a service (set enabled: false or remove from module)."""
    svc_name = service
    if not any(svc_name.endswith(s) for s in ['.service', '.socket', '.timer']):
        svc_name = f'{svc_name}.service'

    host = load_host_config()
    found_in = []
    user_flag_detected = user

    modules_to_search = [module] if module else host.get('modules', [])

    for module_name in modules_to_search:
        module_file = MODULES_DIR / module_name / 'module.yaml'
        if not module_file.exists():
            continue

        with open(module_file) as f:
            module_data = yaml.safe_load(f) or {}

        services = module_data.get('services', [])
        for i, existing in enumerate(services):
            existing_name = existing if isinstance(existing, str) else existing.get('name', '')
            if not any(existing_name.endswith(s) for s in ['.service', '.socket', '.timer']):
                existing_name = f'{existing_name}.service'

            if existing_name == svc_name:
                found_in.append(module_name)

                if isinstance(existing, dict) and existing.get('user'):
                    user_flag_detected = True

                if remove:
                    services.pop(i)
                    removed(f'{svc_name} ← {module_name}')
                else:
                    services[i] = {
                        'name': service,
                        'enabled': False,
                    }
                    if user_flag_detected:
                        services[i]['user'] = True
                    info(f'{svc_name} → enabled: false in {module_name}')

                if not dry_run:
                    with open(module_file, 'w') as f:
                        yaml.dump(module_data, f, default_flow_style=False)
                break

    if not found_in:
        warning(f'{svc_name} not found in any module')
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    user_str = ' (user)' if user_flag_detected else ''
    if disable_service(svc_name, user_flag_detected):
        success(f'Disabled {svc_name}{user_str}')
    else:
        error(f'Failed to disable {svc_name}')
        raise typer.Exit(1)


# Hook subcommands
@hook_app.command('list')
def hook_list():
    """List all hooks and their status."""
    list_hooks()


@hook_app.command('run')
def hook_run(name: str = typer.Argument(..., help='Hook name (e.g., neovim:post, host:post_sync)')):
    """Manually run a hook (ignores tracking)."""
    if not force_run_hook(name):
        error(f'Hook failed: {name}')
        raise typer.Exit(1)
    success(f'Hook completed: {name}')


@hook_app.command('reset')
def hook_reset_cmd(name: str = typer.Argument(..., help='Hook name or module (e.g., neovim:post, neovim, host)')):
    """Reset a hook to run again on next sync."""
    reset_hook(name)


def main():
    app()


if __name__ == '__main__':
    main()
