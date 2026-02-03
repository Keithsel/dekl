from pathlib import Path

CONFIG_DIR = Path.home() / '.config' / 'dekl-arch'
HOSTS_DIR = CONFIG_DIR / 'hosts'
MODULES_DIR = CONFIG_DIR / 'modules'
CONFIG_FILE = CONFIG_DIR / 'config.yaml'
STATE_FILE = CONFIG_DIR / 'state.yaml'
