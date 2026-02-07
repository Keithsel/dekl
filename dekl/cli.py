import shutil
import socket
import typer
import yaml

from dekl import __version__
from dekl.constants import CONFIG_DIR, HOSTS_DIR, MODULES_DIR, CONFIG_FILE
from dekl.config import (
    get_aur_helper,
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
    get_all_installed_packages,
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
from dekl.plan import PackagePlan, compute_package_plan, resolve_prune_mode
from dekl.bootstrap import bootstrap_aur_helper, get_available_aur_helper
from dekl.output import info, success, warning, error, added, removed, header

app = typer.Typer(
    name='dekl',
    help='Declarative Arch Linux system manager',
    context_settings={
        'help_option_names': ['--help', '-h'],
    },
)
hook_app = typer.Typer(help='Manage hooks')
app.add_typer(hook_app, name='hook')


def require_configured_helper_or_exit() -> None:
    """Ensure configured aur_helper exists; otherwise exit with a clear message."""
    try:
        get_aur_helper(strict=True)
    except RuntimeError as e:
        error(str(e))
        info("Fix: install the helper, or run 'dekl sync' to bootstrap it, or change aur_helper in your host yaml.")
        raise typer.Exit(1)


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


def print_package_plan(plan: PackagePlan, prune_enabled: bool):
    """Print package plan consistently."""
    if plan.to_install:
        header('Installing:')
        for pkg in plan.to_install:
            added(pkg)

    if prune_enabled:
        if plan.undeclared:
            header('Removing undeclared:')
            for pkg in plan.undeclared:
                removed(pkg)

        if plan.orphans:
            header('Removing orphans:')
            for pkg in plan.orphans:
                removed(pkg)
    else:
        if plan.undeclared:
            header('Undeclared (not removing, prune disabled):')
            for pkg in plan.undeclared:
                info(f'  {pkg}')

        if plan.orphans:
            header('Orphans (not removing, prune disabled):')
            for pkg in plan.orphans:
                info(f'  {pkg}')

    if not plan.to_install and not plan.undeclared and not plan.orphans:
        info('Packages in sync')


@app.command()
def init(host: str = typer.Option(None, '--host', '-H', help='Host name (defaults to hostname)')):
    """Initialize dekl configuration and select AUR helper."""
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
        info('Select AUR helper:')
        info('  1) paru (recommended, default)')
        info('  2) yay')
        info('  3) none (pacman only)')

        while True:
            choice = typer.prompt('Choice', default='1')
            if choice == '1':
                aur_helper = 'paru'
                break
            elif choice == '2':
                aur_helper = 'yay'
                break
            elif choice == '3':
                aur_helper = 'pacman'
                break
            else:
                error(f'Invalid choice "{choice}". Please enter 1, 2, or 3.')

        host_config = {
            'aur_helper': aur_helper,
            'auto_prune': True,
            'modules': ['base'],
        }
        save_yaml(host_file, host_config)
        success(f'Created {host_file} with aur_helper: {aur_helper}')
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
def status(
    prune: bool | None = typer.Option(None, '--prune/--no-prune', help='Override host auto_prune'),
):
    """Show diff between declared and current state."""
    host = get_host_name()
    host_config = load_host_config()

    missing = validate_modules()
    if missing:
        warning('Missing modules:')
        for m in missing:
            warning(f'  {m}')

    declared = get_declared_packages()
    installed_explicit = get_explicit_packages()
    installed_all = get_all_installed_packages()
    orphans = get_orphan_packages()

    prune_enabled = resolve_prune_mode(host_config, prune)
    plan = compute_package_plan(declared, installed_explicit, installed_all, orphans)

    dotfiles = get_all_dotfiles()
    services = get_declared_services()

    info(f'Host: {host}')
    info(f'Declared: {len(declared)} packages, {len(dotfiles)} dotfiles, {len(services)} services')
    info(f'Installed: {len(installed_explicit)} explicit, {len(orphans)} orphans')
    info(f'Prune: {"enabled" if prune_enabled else "disabled"}')

    print_package_plan(plan, prune_enabled)

    if dotfiles:
        header('Dotfiles:')
        show_dotfiles_status()

    if not plan.to_install and not plan.undeclared and not plan.orphans and not missing:
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
    """Sync packages, services, dotfiles, and run hooks."""
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

    # Bootstrap AUR helper if needed (skip if using pacman only)
    configured_helper = host_config.get('aur_helper', 'paru')

    if configured_helper in {'paru', 'yay'} and not shutil.which(configured_helper):
        available_helper = get_available_aur_helper()

        if available_helper is None:
            warning('No AUR helper found.')
            if dry_run:
                info(f'Would bootstrap {configured_helper}')
            elif yes or typer.confirm(f'Bootstrap {configured_helper}?'):
                if not bootstrap_aur_helper(configured_helper):
                    error('Bootstrap failed. Install an AUR helper manually.')
                    raise typer.Exit(1)
            else:
                error(f'Cannot continue: no AUR helper available and {configured_helper} is configured.')
                info('Either bootstrap it, install manually, or set aur_helper: pacman in host config.')
                raise typer.Exit(1)
        else:
            warning(f'Configured helper "{configured_helper}" not found, but "{available_helper}" is available.')
            if dry_run:
                info(f'Would bootstrap {configured_helper}')
            elif yes or typer.confirm(f'Bootstrap {configured_helper}? (recommended to match your declaration)'):
                if not bootstrap_aur_helper(configured_helper):
                    error('Bootstrap failed.')
                    raise typer.Exit(1)
            else:
                error(f'Cannot continue: host config declares aur_helper: {configured_helper} but it is not installed.')
                info(
                    f'Either install {configured_helper}, or change aur_helper to '
                    f'"{available_helper}" in your host yaml.'
                )
                raise typer.Exit(1)
    # else: configured_helper == 'pacman' or configured_helper already exists, no bootstrap needed

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
    installed_explicit = get_explicit_packages()
    installed_all = get_all_installed_packages()
    orphans = get_orphan_packages()

    plan = compute_package_plan(declared, installed_explicit, installed_all, orphans)
    print_package_plan(plan, prune_enabled)

    to_remove = []
    if prune_enabled:
        to_remove = sorted(set(plan.undeclared) | set(plan.orphans))

    if not dry_run and to_remove and not yes:
        if not typer.confirm(f'Remove {len(to_remove)} packages?'):
            warning('Aborted')
            raise typer.Exit(0)

    if not dry_run:
        if plan.to_install or to_remove:
            require_configured_helper_or_exit()

        if plan.to_install:
            if not install_packages(plan.to_install):
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
        require_configured_helper_or_exit()
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
    packages: list[str] = typer.Argument(..., help='Package(s) to add'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (default: local)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Add package(s) to a module and install."""
    target = module or 'local'
    module_file, module_data = ensure_module(target, dry_run)

    pkg_list = module_data.setdefault('packages', [])
    to_install = []

    for package in packages:
        if package in pkg_list:
            warning(f'{package} already in {target}')
        else:
            pkg_list.append(package)
            to_install.append(package)
            added(f'{package} → {target}')

    if not to_install:
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    save_module(module_file, module_data)

    require_configured_helper_or_exit()
    if install_packages(to_install):
        success(f'Installed {len(to_install)} package(s)')
    else:
        error('Failed to install packages')
        raise typer.Exit(1)


@app.command()
def drop(
    packages: list[str] = typer.Argument(..., help='Package(s) to remove'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Remove package(s) from all modules and uninstall."""
    host = load_host_config()
    to_remove = []

    for package in packages:
        found = False
        for module_name in host.get('modules', []):
            module_file = MODULES_DIR / module_name / 'module.yaml'
            if not module_file.exists():
                continue

            with open(module_file) as f:
                module_data = yaml.safe_load(f) or {}

            pkg_list = module_data.get('packages', [])
            if package in pkg_list:
                found = True
                pkg_list.remove(package)
                removed(f'{package} ← {module_name}')

                if not dry_run:
                    save_yaml(module_file, module_data)

        if found:
            to_remove.append(package)
        else:
            warning(f'{package} not found in any module')

    if not to_remove:
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    require_configured_helper_or_exit()
    if remove_packages(to_remove):
        success(f'Removed {len(to_remove)} package(s)')
    else:
        error('Failed to remove packages')
        raise typer.Exit(1)


@app.command()
def enable(
    services: list[str] = typer.Argument(..., help='Service(s) to enable'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (default: local)'),
    user: bool = typer.Option(False, '--user', help='User service (systemctl --user)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Add service(s) to a module and enable."""
    target = module or 'local'
    module_file, module_data = ensure_module(target, dry_run)
    svc_list = module_data.setdefault('services', [])

    to_enable = []

    for service in services:
        svc_name = normalize_service_name(service)
        already_exists = False

        for i, existing in enumerate(svc_list):
            existing_name = existing if isinstance(existing, str) else existing.get('name', '')
            existing_name = normalize_service_name(existing_name)

            if existing_name == svc_name:
                if isinstance(existing, dict) and not existing.get('enabled', True):
                    svc_list[i] = {'name': service, 'user': user, 'enabled': True} if user else service
                    info(f'Re-enabling {svc_name} in {target}')
                    to_enable.append((svc_name, user))
                else:
                    warning(f'{svc_name} already enabled in {target}')
                already_exists = True
                break

        if not already_exists:
            if user:
                svc_list.append({'name': service, 'user': True})
            else:
                svc_list.append(service)
            added(f'{svc_name} → {target}')
            to_enable.append((svc_name, user))

    if not to_enable:
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    save_module(module_file, module_data)

    failed = []
    for svc_name, is_user in to_enable:
        user_flag = ' (user)' if is_user else ''
        if enable_service(svc_name, is_user):
            success(f'Enabled {svc_name}{user_flag}')
        else:
            failed.append(svc_name)
            error(f'Failed to enable {svc_name}')

    if failed:
        raise typer.Exit(1)


@app.command()
def disable(
    services: list[str] = typer.Argument(..., help='Service(s) to disable'),
    module: str = typer.Option(None, '-m', '--module', help='Target module (searches all if not specified)'),
    remove: bool = typer.Option(False, '-r', '--remove', help='Remove from module instead of setting enabled: false'),
    user: bool = typer.Option(False, '--user', help='User service (systemctl --user)'),
    dry_run: bool = typer.Option(False, '-n', '--dry-run', help='Show what would happen'),
):
    """Disable service(s) (set enabled: false or remove from module)."""
    host = load_host_config()
    modules_to_search = [module] if module else host.get('modules', [])

    to_disable = []

    for service in services:
        svc_name = normalize_service_name(service)
        found = False
        user_flag_detected = user

        for module_name in modules_to_search:
            module_file = MODULES_DIR / module_name / 'module.yaml'
            if not module_file.exists():
                continue

            with open(module_file) as f:
                module_data = yaml.safe_load(f) or {}

            svc_list = module_data.get('services', [])
            for i, existing in enumerate(svc_list):
                existing_name = existing if isinstance(existing, str) else existing.get('name', '')
                existing_name = normalize_service_name(existing_name)

                if existing_name == svc_name:
                    found = True

                    if isinstance(existing, dict) and existing.get('user'):
                        user_flag_detected = True

                    if remove:
                        svc_list.pop(i)
                        removed(f'{svc_name} ← {module_name}')
                    else:
                        entry = {'name': svc_name, 'enabled': False}
                        if user_flag_detected:
                            entry['user'] = True
                        svc_list[i] = entry
                        info(f'{svc_name} → enabled: false in {module_name}')

                    if not dry_run:
                        save_yaml(module_file, module_data)
                    break

            if found:
                break

        if found:
            to_disable.append((svc_name, user_flag_detected))
        else:
            warning(f'{svc_name} not found in any module')

    if not to_disable:
        return

    if dry_run:
        info('Dry run - no changes made')
        return

    failed = []
    for svc_name, is_user in to_disable:
        user_str = ' (user)' if is_user else ''
        if disable_service(svc_name, is_user):
            success(f'Disabled {svc_name}{user_str}')
        else:
            failed.append(svc_name)
            error(f'Failed to disable {svc_name}')

    if failed:
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
