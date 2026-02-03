import shutil
import yaml

from dekl.constants import CONFIG_FILE, HOSTS_DIR, MODULES_DIR


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
        return yaml.safe_load(f)


def load_module(name: str) -> dict:
    """Load a module by name."""
    path = MODULES_DIR / name / 'module.yaml'
    if not path.exists():
        raise FileNotFoundError(f'Module not found: {name}')
    with open(path) as f:
        return yaml.safe_load(f)


def get_module_path(name: str):
    """Get the path to a module directory."""
    return MODULES_DIR / name


def get_declared_packages() -> list[str]:
    """Get all packages from all enabled modules."""
    host = load_host_config()
    packages = []

    for module_name in host.get('modules', []):
        module = load_module(module_name)
        packages.extend(module.get('packages', []))

    return list(set(packages))


def get_aur_helper() -> str:
    """Get configured or detected AUR helper."""
    host = load_host_config()

    if 'aur_helper' in host:
        helper = host['aur_helper']
        if shutil.which(helper):
            return helper

    for helper in ['paru', 'yay']:
        if shutil.which(helper):
            return helper

    return 'pacman'
