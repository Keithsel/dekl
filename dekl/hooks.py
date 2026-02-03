import subprocess

from dekl.constants import MODULES_DIR
from dekl.config import load_module
from dekl.state import load_state, save_state
from dekl.output import info, success, warning, error


def get_module_hooks(module_name: str) -> dict:
    """Get hooks config for a module."""
    module = load_module(module_name)
    module_path = MODULES_DIR / module_name
    scripts_dir = module_path / 'scripts'

    hooks_config = module.get('hooks', {})

    if scripts_dir.exists() and not hooks_config:
        warning(f"Module '{module_name}' has scripts/ but no hooks declaration")

    result = {}

    for hook_type in ['pre', 'post']:
        if hook_type in hooks_config:
            script_path = module_path / hooks_config[hook_type]
            if script_path.exists():
                result[hook_type] = script_path
            else:
                warning(f"Module '{module_name}' hook not found: {script_path}")

    return result


def run_hook(module_name: str, hook_type: str, dry_run: bool = False) -> bool:
    """Run a module hook. Returns True if successful."""
    hooks = get_module_hooks(module_name)

    if hook_type not in hooks:
        return True

    script = hooks[hook_type]

    state = load_state()
    hooks_run = state.get('hooks_run', {})
    hook_key = f'{module_name}:{hook_type}'

    if hook_key in hooks_run:
        return True

    info(f'Running {hook_type} hook for {module_name}')

    if dry_run:
        return True

    result = subprocess.run(['bash', str(script)])

    if result.returncode != 0:
        error(f'Hook failed: {script}')
        return False

    hooks_run[hook_key] = True
    state['hooks_run'] = hooks_run
    save_state(state)

    success(f'Hook completed: {module_name} {hook_type}')
    return True


def reset_hook(module_name: str, hook_type: str | None = None):
    """Reset hook state so it runs again."""
    state = load_state()
    hooks_run = state.get('hooks_run', {})

    if hook_type:
        hook_key = f'{module_name}:{hook_type}'
        if hook_key in hooks_run:
            del hooks_run[hook_key]
            success(f'Reset hook: {hook_key}')
    else:
        to_delete = [k for k in hooks_run if k.startswith(f'{module_name}:')]
        for k in to_delete:
            del hooks_run[k]
        if to_delete:
            success(f'Reset all hooks for: {module_name}')

    state['hooks_run'] = hooks_run
    save_state(state)
