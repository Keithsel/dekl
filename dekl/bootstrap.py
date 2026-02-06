import shutil
import subprocess
import tempfile
from pathlib import Path

from dekl.output import info, success, error


SUPPORTED_HELPERS = ['paru', 'yay']


def has_aur_helper() -> bool:
    """Check if any AUR helper is available."""
    for helper in SUPPORTED_HELPERS:
        if shutil.which(helper):
            return True
    return False


def get_available_aur_helper() -> str | None:
    """Get first available AUR helper, or None."""
    for helper in SUPPORTED_HELPERS:
        if shutil.which(helper):
            return helper
    return None


def bootstrap_aur_helper(helper: str = 'paru') -> bool:
    """Bootstrap an AUR helper from AUR. Returns True if successful.

    Supports: paru, yay
    """
    if helper not in SUPPORTED_HELPERS:
        error(f'Unsupported AUR helper: {helper}. Supported: {", ".join(SUPPORTED_HELPERS)}')
        return False

    info(f'Bootstrapping {helper}...')

    info('Installing base-devel and git...')
    result = subprocess.run(
        ['sudo', 'pacman', '-S', '--needed', '--noconfirm', 'base-devel', 'git'],
    )
    if result.returncode != 0:
        error('Failed to install base-devel and git')
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_url = f'https://aur.archlinux.org/{helper}.git'
        clone_path = Path(tmpdir) / helper

        info(f'Cloning {repo_url}...')
        result = subprocess.run(
            ['git', 'clone', '--depth=1', repo_url, str(clone_path)],
        )
        if result.returncode != 0:
            error(f'Failed to clone {helper}')
            return False

        info(f'Building {helper}...')
        result = subprocess.run(
            ['makepkg', '-si', '--noconfirm'],
            cwd=clone_path,
        )
        if result.returncode != 0:
            error(f'Failed to build {helper}')
            return False

    if shutil.which(helper):
        success(f'{helper} installed successfully')
        return True
    else:
        error(f'{helper} installation verification failed')
        return False
