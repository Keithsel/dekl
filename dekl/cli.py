import socket
import typer
import yaml

from dekl import __version__
from dekl.constants import CONFIG_DIR, HOSTS_DIR, MODULES_DIR, CONFIG_FILE
from dekl.config import (
    get_declared_packages,
    get_host_name,
    load_host_config,
    validate_modules,
    ensure_module,
    save_module,
    save_yaml,
    normalize_service_name,
)
from dekl.packages import (
    get_explicit_packages,
    get_orphan_packages,
    install_packages,
    remove_packages,
    upgrade_system,
)
from dekl.dotfiles import sync_dotfiles, get_all_dotfiles, show_dotfiles_status
from dekl.services import (
    sync_services,
    enable_service,
    disable_service,
    get_declared_services,
)
from dekl.hooks import (
    run_module_hook,
    run_host_hook,
    reset_hook,
    list_hooks,
    force_run_hook,
)
from dekl.plan import compute_package_plan, resolve_prune_mode
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


def print_package_plan(to_install, to_remove_undeclared, to_remove_orphans, prune_enabled):
    """Print package plan consistently."""
    if to_install:
        header('Installing:')
        for pkg in to_install:
            added(pkg)

    if prune_enabled:
        if to_remove_undeclared:
            header('Removing undeclared:')
            for pkg in to_remove_undeclared:
                removed(pkg)

        if to_remove_orphans:
            header('Removing orphans:')
            for pkg in to_remove_orphans:
                removed(pkg)
    else:
        if to_remove_orphans:
            header('Orphans (not removing, prune disabled):')
            for pkg in to_remove_orphans:
                info(f'  {pkg}')

    if not to_install and not to_remove_undeclared and not to_remove_orphans:
        info('Packages in sync')


@app.command()
def init(host: str = typer.Option(None, '--host', '-H', help='Host name (defaults to hostname)')):
    """Scaffold a new dekl configuration."""
    if host is None:
        host = socket.gethostname()

    HOSTS_DIR.mkdir(parents=True, exist_ok=True)
    MODULES_DIR.mkdir(parents=True, exist_ok=True)
    (MODULES_DIR / 'base').mkdir(exist_ok=True)

    if not CONFIG_FILE.exists():
        save_yaml(CONFIG_FILE, {'host': host})
        success(f'Created {CONFIG_FILE}')
    else:
        info(f'Config already exists: {CONFIG_FILE}')

    host_file = HOSTS_DIR / f'{host}.yaml'
    if not host_file.exists():
        host_config = {
            'aur_helper': 'paru',
            'auto_prune': True,
            'modules': ['base'],
        }
        save_yaml(host_file, host_config)
        success(f'Created {host_file}')
    else:
        info(f'Host config already exists: {host_file}')

    base_module = MODULES_DIR / 'base' / 'module.yaml'
    if not base_module.exists():
        save_yaml(base_module, {'packages': ['base']})
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

    save_yaml(module_path, module)

    success(f'Captured {len(packages)} packages into system module')
    info('')
    info("Add 'system' to your host config:")
    info('  modules:')
    info('    - system')


@app.command()
def status():
    """Show diff between declared and current state."""
    host = get_host_name()
    host_config = load_host_config()

    missing = validate_modules()
    if missing:
        warning('Missing modules:')
        for m in missing:
            warning(f'  {m}')

    declared = get_declared_packages()
    installed = get_explicit_packages()
    orphans = get_orphan_packages()

    prune_enabled = resolve_prune_mode(host_config, None)
    to_install, to_remove_undeclared, to_remove_orphans = compute_package_plan(
        declared, installed, orphans, prune_enabled
    )

    dotfiles = get_all_dotfiles()
    services = get_declared_services()

    info(f'Host: {host}')
    info(f'Declared: {len(declared)} packages, {len(dotfiles)} dotfiles, {len(services)} services')
    info(f'Installed: {len(installed)} explicit, {len(orphans)} orphans')
    info(f'Prune: {"enabled" if prune_enabled else "disabled"}')

    print_package_plan(to_install, to_remove_undeclared, to_remove_orphans, prune_enabled)

    if dotfiles:
        header('Dotfiles:')
        show_dotfiles_status()

    if not to_install and not to_remove_undeclared and not to_remove_orphans and not missing:
        success('System is in sync')


@app.command()
def sync(
    dry_run: bool = typer.Option(False, '--dry-run', '-n', help='Show what would be done'),
    prune: bool | None = typer.Option(None, '--prune/--no-prune', help='Remove undeclared packages'),
    yes: bool = typer.Option(False, '--yes', '-y', help='Skip confirmation prompts'),
    no_hooks: bool = typer.Option(False, '--no-hooks', help='Skip all hooks'),
    no_dotfiles: bool = typer.Option(False, '--no-dotfiles', help='Skip dotfiles sync'),
    no_services: bool = typer.Option(False, '--no-services', help='Skip services sync'),
):
    """Sync system to declared state."""
    missing = validate_modules()
    if missing:
        error('Missing modules:')
        for m in missing:
            warning(f'  {m}')
        error('Fix your host config or create the missing modules.')
        raise typer.Exit(1)

    host_config = load_host_config()
    modules = host_config.get('modules', [])
    prune_enabled = resolve_prune_mode(host_config, prune)

    # Pre hooks
    if not no_hooks:
        if not run_host_hook('pre_sync', dry_run):
            error('Host pre_sync hook failed')
            raise typer.Exit(1)
        for module_name in modules:
            if not run_module_hook(module_name, 'pre', dry_run):
                error(f'Pre hook failed for {module_name}')
                raise typer.Exit(1)

    # Packages
    declared = get_declared_packages()
    installed = get_explicit_packages()
    orphans = get_orphan_packages()

    to_install, to_remove_undeclared, to_remove_orphans = compute_package_plan(
        declared, installed, orphans, prune_enabled
    )

    print_package_plan(to_install, to_remove_undeclared, to_remove_orphans, prune_enabled)

    to_remove = to_remove_undeclared + to_remove_orphans

    if not dry_run and to_remove and not yes:
        if not typer.confirm(f'Remove {len(to_remove)} packages?'):
            warning('Aborted')
            raise typer.Exit(0)

    if not dry_run:
        if to_install:
            if not install_packages(to_install):
                error('Failed to install packages')
                raise typer.Exit(1)

        if to_remove:
            if not remove_packages(to_remove):
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
    target = module or 'local'
    module_file, module_data = ensure_module(target, dry_run)

    packages = module_data.setdefault('packages', [])
    if package in packages:
        warning(f'{package} already in {target}')
        return

    packages.append(package)
    added(f'{package} → {target}')

    if dry_run:
        info('Dry run - no changes made')
        return

    save_module(module_file, module_data)

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
                save_yaml(module_file, module_data)

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
    target = module or 'local'
    module_file, module_data = ensure_module(target, dry_run)
    svc_name = normalize_service_name(service)

    services = module_data.setdefault('services', [])
    for i, existing in enumerate(services):
        existing_name = existing if isinstance(existing, str) else existing.get('name', '')
        existing_name = normalize_service_name(existing_name)

        if existing_name == svc_name:
            if isinstance(existing, dict) and not existing.get('enabled', True):
                services[i] = {'name': service, 'user': user, 'enabled': True} if user else service
                info(f'Re-enabling {svc_name} in {target}')
                break
            else:
                warning(f'{svc_name} already enabled in {target}')
                return
    else:
        if user:
            services.append({'name': service, 'user': True})
        else:
            services.append(service)
        added(f'{svc_name} → {target}')

    if dry_run:
        info('Dry run - no changes made')
        return

    save_module(module_file, module_data)

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
    svc_name = normalize_service_name(service)

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
            existing_name = normalize_service_name(existing_name)

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
                    save_yaml(module_file, module_data)
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
