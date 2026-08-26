"""Turns one SearchProfile into a bounded set of Adzuna search
configurations - the piece that keeps a broad profile (many keyword
groups x many locations) from turning into "every keyword x every
location" API traffic.

One `AdzunaSearchConfig` is planned per keyword group (all of that group's
keyword variants OR'd into a single `what_or` query, exactly as
AdzunaJobSource already does), searched across the profile's locations in
priority order. If the total (group x location) task count would exceed
`MAX_SEARCH_TASKS`, lower-priority locations are dropped first - every
keyword group still gets searched (at least in its highest-priority
location), rather than dropping whole role families.
"""

from __future__ import annotations

from app.domain.discovery import SearchProfile
from app.ingestion.adzuna_source import AdzunaSearchConfig

MAX_SEARCH_TASKS = 12


def _ranked_locations(profile: SearchProfile) -> list[str]:
    if not profile.locations:
        return [""]  # a single "no location filter" task
    return sorted(profile.locations, key=lambda loc: profile.location_priority.get(loc, 99))


def plan_adzuna_configs(
    profile: SearchProfile,
    *,
    results_per_page: int,
    max_pages: int,
    max_days_old: int | None,
) -> list[AdzunaSearchConfig]:
    groups = profile.all_keyword_groups()
    if not groups:
        return []

    locations = _ranked_locations(profile)
    total_tasks = len(groups) * len(locations)

    if total_tasks <= MAX_SEARCH_TASKS:
        tasks = [(group, loc) for group in groups for loc in locations]
    else:
        # Every group keeps at least its highest-priority location; fill
        # remaining budget round-robin across groups in location-priority order.
        tasks = [(group, locations[0]) for group in groups]
        remaining_budget = MAX_SEARCH_TASKS - len(tasks)
        for loc in locations[1:]:
            for group in groups:
                if remaining_budget <= 0:
                    break
                tasks.append((group, loc))
                remaining_budget -= 1
            if remaining_budget <= 0:
                break

    configs = []
    for group, location in tasks:
        configs.append(
            AdzunaSearchConfig(
                keywords=group.keywords,
                locations=[location] if location else [],
                results_per_page=results_per_page,
                max_pages=max_pages,
                max_days_old=max_days_old,
            )
        )
    return configs
