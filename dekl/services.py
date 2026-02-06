import subprocess
from dataclasses import dataclass

from dekl.config import load_host_config, load_module, normalize_service_name
from dekl.state import load_state, save_state
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
        name = normalize_service_name(config)
        return Service(name=name)

    if isinstance(config, dict):
        name = config.get('name')
        if not name:
            return None
        name = normalize_service_name(name)
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

    # Unique by (name, user)
    seen = set()
    unique = []
    for service in all_services:
        key = (service.name, service.user)
        if key not in seen:
            seen.add(key)
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


def get_tracked_services() -> dict[str, bool]:
    """Get services we previously enabled. Returns {name|user: True}."""
    state = load_state()
    return state.get('services', {})


def save_tracked_services(services: list[Service]):
    """Save services we've enabled."""
    state = load_state()
    state['services'] = {f'{s.name}|{s.user}': True for s in services if s.enabled}
    save_state(state)


def sync_services(dry_run: bool = False) -> bool:
    """Sync services to declared state. Returns True if successful."""
    declared = get_declared_services()
    tracked = get_tracked_services()

    declared_map = {}
    for service in declared:
        if service.enabled:
            declared_map[f'{service.name}|{service.user}'] = True

    to_enable = []
    for service in declared:
        if service.enabled:
            current = is_service_enabled(service.name, service.user)
            if not current:
                to_enable.append(service)

    to_disable = []
    for key in tracked:
        if key not in declared_map:
            name, user_str = key.split('|', 1)
            user = user_str == 'True'
            if is_service_enabled(name, user):
                to_disable.append(Service(name=name, user=user, enabled=False))

    for service in declared:
        if not service.enabled:
            if is_service_enabled(service.name, service.user):
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

    save_tracked_services(declared)

    return True
