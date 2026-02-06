from dataclasses import dataclass


@dataclass
class PackagePlan:
    """Computed package plan."""

    to_install: list[str]
    undeclared: list[str]
    orphans: list[str]


def compute_package_plan(
    declared: list[str],
    installed: set[str],
    orphans: set[str],
) -> PackagePlan:
    """Compute package changes. Always computes all lists."""
    declared_set = set(declared)

    return PackagePlan(
        to_install=[p for p in declared if p not in installed],
        undeclared=sorted(installed - declared_set),
        orphans=sorted(orphans),
    )


def resolve_prune_mode(host_config: dict, prune_override: bool | None) -> bool:
    """Resolve effective prune mode from host config and CLI override."""
    auto_prune = host_config.get('auto_prune', True)
    return auto_prune if prune_override is None else prune_override
