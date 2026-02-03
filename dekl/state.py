import yaml

from dekl.constants import STATE_FILE, CONFIG_DIR


def load_state() -> dict:
    """Load current state."""
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        return yaml.safe_load(f) or {}


def save_state(state: dict):
    """Save state."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        yaml.dump(state, f)
