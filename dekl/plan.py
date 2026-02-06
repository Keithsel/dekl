def compute_package_plan(
    declared: list[str],
    installed: set[str],
    orphans: set[str],
    prune_enabled: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Compute package changes.

    Returns (to_install, to_remove_undeclared, to_remove_orphans).
    """
    declared_set = set(declared)

    # Preserve declaration order
    to_install = [p for p in declared if p not in installed]

    if not prune_enabled:
        return to_install, [], []

    to_remove_undeclared = sorted(installed - declared_set)
    to_remove_orphans = sorted(orphans)

    return to_install, to_remove_undeclared, to_remove_orphans


def resolve_prune_mode(host_config: dict, prune_override: bool | None) -> bool:
    """Resolve effective prune mode from host config and CLI override."""
    auto_prune = host_config.get('auto_prune', True)
    return auto_prune if prune_override is None else prune_override
