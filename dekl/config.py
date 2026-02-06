import shutil
import yaml
from pathlib import Path

from dekl.constants import CONFIG_FILE, HOSTS_DIR, MODULES_DIR
from dekl.output import info, warning


def load_config() -> dict:
    """Load main config."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def get_host_name() -> str:
    """Get configured host name."""
    config = load_config()
    if 'host' not in config:
        raise RuntimeError("No host configured. Run 'dekl init' first.")
    return config['host']


def load_host_config() -> dict:
    """Load host configuration."""
    host = get_host_name()
    path = HOSTS_DIR / f'{host}.yaml'
    if not path.exists():
        raise FileNotFoundError(f'Host config not found: {path}')
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_module(name: str) -> dict:
    """Load a module by name."""
    path = MODULES_DIR / name / 'module.yaml'
    if not path.exists():
        raise FileNotFoundError(f'Module not found: {name}')
    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_module_path(name: str):
    """Get the path to a module directory."""
    return MODULES_DIR / name


def module_exists(name: str) -> bool:
    """Check if a module exists."""
    path = MODULES_DIR / name / 'module.yaml'
    return path.exists()


def validate_modules() -> list[str]:
    """Validate all modules in host config exist. Returns list of missing modules."""
    host = load_host_config()
    missing = []
    for module_name in host.get('modules', []):
        if not module_exists(module_name):
            missing.append(module_name)
    return missing


def get_declared_packages() -> list[str]:
    """Get all packages from enabled modules."""
    host = load_host_config()
    packages = []

    for module_name in host.get('modules', []):
        try:
            module = load_module(module_name)
            packages.extend(module.get('packages', []))
        except FileNotFoundError:
            pass

    # Stable de-dupe preserving first-seen order
    seen = set()
    unique = []
    for p in packages:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def get_aur_helper() -> str:
    """Get configured or detected AUR helper."""
    try:
        host = load_host_config()
    except (RuntimeError, FileNotFoundError):
        host = {}

    if 'aur_helper' in host:
        helper = host['aur_helper']
        if shutil.which(helper):
            return helper
        else:
            warning(f'Configured AUR helper "{helper}" not found, falling back to pacman')

    for helper in ['paru', 'yay']:
        if shutil.which(helper):
            return helper

    return 'pacman'


def ensure_module(name: str, dry_run: bool = False) -> tuple[Path, dict]:
    """Ensure module exists. Returns (module_file, module_data)."""
    module_path = MODULES_DIR / name
    module_file = module_path / 'module.yaml'

    if not module_path.exists():
        if dry_run:
            info(f'Would create module: {name}')
        else:
            module_path.mkdir(parents=True)
            info(f'Creating module: {name}')

        host_name = get_host_name()
        host_file = HOSTS_DIR / f'{host_name}.yaml'
        with open(host_file) as f:
            host_config = yaml.safe_load(f) or {}
        if name not in host_config.get('modules', []):
            host_config.setdefault('modules', []).append(name)
            if not dry_run:
                save_yaml(host_file, host_config)
                info(f'Added {name} to host config')
            else:
                info(f'Would add {name} to host config')

    if module_file.exists():
        with open(module_file) as f:
            module_data = yaml.safe_load(f) or {}
    else:
        module_data = {}

    return module_file, module_data


def save_module(module_file: Path, module_data: dict):
    """Save module data."""
    save_yaml(module_file, module_data)


def save_yaml(path: Path, data: dict):
    """Save YAML consistently."""
    with open(path, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def normalize_service_name(name: str) -> str:
    """Ensure service name has a unit suffix."""
    if not any(name.endswith(s) for s in ['.service', '.socket', '.timer']):
        return f'{name}.service'
    return name
