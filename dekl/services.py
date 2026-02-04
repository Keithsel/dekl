import subprocess
from dataclasses import dataclass

from dekl.config import load_host_config, load_module
from dekl.output import info, success, error, added, removed


@dataclass
class Service:
    """Represents a service configuration."""

    name: str
    user: bool = False
    enabled: bool = True


def parse_service_config(config) -> Service | None:
    """Parse service config (string or dict) into Service object."""
    if config is None:
        return None

    if isinstance(config, str):
        name = config
        if not name.endswith('.service') and not name.endswith('.socket') and not name.endswith('.timer'):
            name = f'{name}.service'
        return Service(name=name)

    if isinstance(config, dict):
        name = config.get('name')
        if not name:
            return None
        if not name.endswith('.service') and not name.endswith('.socket') and not name.endswith('.timer'):
            name = f'{name}.service'
        return Service(
            name=name,
            user=config.get('user', False),
            enabled=config.get('enabled', True),
        )

    return None


def get_module_services(module_name: str) -> list[Service]:
    """Get services declared in a module."""
    module = load_module(module_name)
    services_config = module.get('services', [])

    result = []
    for config in services_config:
        service = parse_service_config(config)
        if service:
            result.append(service)

    return result


def get_declared_services() -> list[Service]:
    """Get all services from all enabled modules."""
    host = load_host_config()
    all_services = []

    for module_name in host.get('modules', []):
        all_services.extend(get_module_services(module_name))

    # Deduplicate by name (keep first occurrence)
    seen = set()
    unique = []
    for service in all_services:
        if service.name not in seen:
            seen.add(service.name)
            unique.append(service)

    return unique


def is_service_enabled(name: str, user: bool = False) -> bool:
    """Check if a service is currently enabled."""
    cmd = ['systemctl']
    if user:
        cmd.append('--user')
    cmd.extend(['is-enabled', name])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip() == 'enabled'


def enable_service(name: str, user: bool = False) -> bool:
    """Enable and start a service."""
    cmd = ['systemctl']
    if user:
        cmd.append('--user')
    else:
        cmd = ['sudo', 'systemctl']
    cmd.extend(['enable', '--now', name])

    result = subprocess.run(cmd)
    return result.returncode == 0


def disable_service(name: str, user: bool = False) -> bool:
    """Disable and stop a service."""
    cmd = ['systemctl']
    if user:
        cmd.append('--user')
    else:
        cmd = ['sudo', 'systemctl']
    cmd.extend(['disable', '--now', name])

    result = subprocess.run(cmd)
    return result.returncode == 0


def sync_services(dry_run: bool = False) -> bool:
    """Sync services to declared state. Returns True if successful."""
    declared = get_declared_services()

    to_enable = []
    to_disable = []

    for service in declared:
        current = is_service_enabled(service.name, service.user)

        if service.enabled and not current:
            to_enable.append(service)
        elif not service.enabled and current:
            to_disable.append(service)

    if not to_enable and not to_disable:
        info('Services in sync')
        return True

    if to_enable:
        for service in to_enable:
            user_flag = ' (user)' if service.user else ''
            added(f'{service.name}{user_flag}')

    if to_disable:
        for service in to_disable:
            user_flag = ' (user)' if service.user else ''
            removed(f'{service.name}{user_flag}')

    if dry_run:
        return True

    for service in to_enable:
        if not enable_service(service.name, service.user):
            error(f'Failed to enable: {service.name}')
            return False
        success(f'Enabled: {service.name}')

    for service in to_disable:
        if not disable_service(service.name, service.user):
            error(f'Failed to disable: {service.name}')
            return False
        success(f'Disabled: {service.name}')

    return True
