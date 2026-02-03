import subprocess
from pathlib import Path
from dataclasses import dataclass

from dekl.constants import MODULES_DIR, CONFIG_DIR
from dekl.config import load_module, load_host_config
from dekl.state import load_state, save_state
from dekl.output import info, success, warning, error


@dataclass
class Hook:
    """Represents a hook configuration."""

    path: Path
    always: bool = False
    root: bool = False


def parse_hook_config(config, base_path: Path) -> Hook | None:
    """Parse hook config (string or dict) into Hook object."""
    if config is None:
        return None

    if isinstance(config, str):
        return Hook(path=base_path / config)

    if isinstance(config, dict):
        run = config.get('run')
        if not run:
            return None
        return Hook(
            path=base_path / run,
            always=config.get('always', False),
            root=config.get('root', False),
        )

    return None


def get_module_hooks(module_name: str) -> dict[str, Hook]:
    """Get hooks config for a module."""
    module = load_module(module_name)
    module_path = MODULES_DIR / module_name
    scripts_dir = module_path / 'scripts'

    hooks_config = module.get('hooks', {})

    if scripts_dir.exists() and not hooks_config:
        warning(f"Module '{module_name}' has scripts/ but no hooks declaration")

    result = {}

    for hook_type in ['pre', 'post']:
        hook = parse_hook_config(hooks_config.get(hook_type), module_path)
        if hook:
            if hook.path.exists():
                result[hook_type] = hook
            else:
                warning(f"Module '{module_name}' hook not found: {hook.path}")

    return result


def get_host_hooks() -> dict[str, Hook]:
    """Get hooks config for the host."""
    host = load_host_config()
    hooks_config = host.get('hooks', {})

    result = {}

    for hook_type in ['pre_sync', 'post_sync', 'pre_update', 'post_update']:
        hook = parse_hook_config(hooks_config.get(hook_type), CONFIG_DIR)
        if hook:
            if hook.path.exists():
                result[hook_type] = hook
            else:
                warning(f'Host hook not found: {hook.path}')

    return result


def should_run_hook(hook_key: str, hook: Hook) -> bool:
    """Check if hook should run based on state and config."""
    if hook.always:
        return True

    state = load_state()
    hooks_run = state.get('hooks_run', {})
    return hook_key not in hooks_run


def mark_hook_run(hook_key: str):
    """Mark hook as run in state."""
    state = load_state()
    hooks_run = state.get('hooks_run', {})
    hooks_run[hook_key] = True
    state['hooks_run'] = hooks_run
    save_state(state)


def execute_hook(hook: Hook) -> bool:
    """Execute a hook script. Returns True if successful."""
    cmd = ['bash', str(hook.path)]

    if hook.root:
        cmd = ['sudo'] + cmd

    result = subprocess.run(cmd)
    return result.returncode == 0


def run_module_hook(module_name: str, hook_type: str, dry_run: bool = False) -> bool:
    """Run a module hook. Returns True if successful."""
    hooks = get_module_hooks(module_name)

    if hook_type not in hooks:
        return True

    hook = hooks[hook_type]
    hook_key = f'{module_name}:{hook_type}'

    if not should_run_hook(hook_key, hook):
        return True

    info(f'Running {hook_type} hook for {module_name}')

    if dry_run:
        return True

    if not execute_hook(hook):
        error(f'Hook failed: {hook.path}')
        return False

    if not hook.always:
        mark_hook_run(hook_key)

    success(f'Hook completed: {module_name} {hook_type}')
    return True


def run_host_hook(hook_type: str, dry_run: bool = False) -> bool:
    """Run a host hook. Returns True if successful."""
    hooks = get_host_hooks()

    if hook_type not in hooks:
        return True

    hook = hooks[hook_type]
    hook_key = f'host:{hook_type}'

    if not should_run_hook(hook_key, hook):
        return True

    info(f'Running host hook: {hook_type}')

    if dry_run:
        return True

    if not execute_hook(hook):
        error(f'Hook failed: {hook.path}')
        return False

    if not hook.always:
        mark_hook_run(hook_key)

    success(f'Host hook completed: {hook_type}')
    return True


def force_run_hook(name: str) -> bool:
    """Force run a hook by name, ignoring tracking."""
    if ':' not in name:
        error(f"Invalid hook name: {name}. Use format 'module:type' or 'host:type'")
        return False

    target, hook_type = name.split(':', 1)

    if target == 'host':
        hooks = get_host_hooks()
        if hook_type not in hooks:
            error(f'Host hook not found: {hook_type}')
            return False
        return execute_hook(hooks[hook_type])
    else:
        hooks = get_module_hooks(target)
        if hook_type not in hooks:
            error(f'Module hook not found: {target}:{hook_type}')
            return False
        return execute_hook(hooks[hook_type])


def reset_hook(name: str):
    """Reset hook state so it runs again."""
    state = load_state()
    hooks_run = state.get('hooks_run', {})

    if ':' in name:
        # Specific hook
        if name in hooks_run:
            del hooks_run[name]
            success(f'Reset hook: {name}')
        else:
            info(f'Hook not tracked: {name}')
    else:
        # All hooks for a module/host
        to_delete = [k for k in hooks_run if k.startswith(f'{name}:')]
        for k in to_delete:
            del hooks_run[k]
        if to_delete:
            success(f'Reset all hooks for: {name}')
        else:
            info(f'No hooks tracked for: {name}')

    state['hooks_run'] = hooks_run
    save_state(state)


def list_hooks():
    """List all hooks and their status."""
    state = load_state()
    hooks_run = state.get('hooks_run', {})

    host_config = load_host_config()
    modules = host_config.get('modules', [])

    host_hooks = get_host_hooks()
    if host_hooks:
        info('Host hooks:')
        for hook_type, hook in host_hooks.items():
            hook_key = f'host:{hook_type}'
            status = 'always' if hook.always else ('run' if hook_key in hooks_run else 'pending')
            root_flag = ' (root)' if hook.root else ''
            info(f'  {hook_type}: {hook.path.name} [{status}]{root_flag}')
        info('')

    for module_name in modules:
        hooks = get_module_hooks(module_name)
        if hooks:
            info(f'{module_name}:')
            for hook_type, hook in hooks.items():
                hook_key = f'{module_name}:{hook_type}'
                status = 'always' if hook.always else ('run' if hook_key in hooks_run else 'pending')
                root_flag = ' (root)' if hook.root else ''
                info(f'  {hook_type}: {hook.path.name} [{status}]{root_flag}')
