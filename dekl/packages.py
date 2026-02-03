import subprocess

from dekl.config import get_aur_helper


def get_explicit_packages() -> set[str]:
    """Get explicitly installed packages."""
    result = subprocess.run(
        ['pacman', '-Qqe'],
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if not output:
        return set()
    return set(output.split('\n'))


def get_orphan_packages() -> set[str]:
    """Get orphaned dependencies."""
    result = subprocess.run(
        ['pacman', '-Qdtq'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    output = result.stdout.strip()
    if not output:
        return set()
    return set(output.split('\n'))


def install_packages(packages: list[str]) -> bool:
    """Install packages."""
    if not packages:
        return True
    helper = get_aur_helper()
    result = subprocess.run([helper, '-S', '--needed'] + packages)
    return result.returncode == 0


def remove_packages(packages: list[str]) -> bool:
    """Remove packages and orphaned dependencies."""
    if not packages:
        return True
    helper = get_aur_helper()
    result = subprocess.run([helper, '-Rsu', '--noconfirm'] + packages)
    return result.returncode == 0


def upgrade_system() -> bool:
    """Upgrade all system packages."""
    helper = get_aur_helper()
    result = subprocess.run([helper, '-Syu'])
    return result.returncode == 0
