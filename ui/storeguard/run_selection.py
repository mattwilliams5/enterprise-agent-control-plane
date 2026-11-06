"""Pure run-selection correlation for StoreGuard Mission Control."""


def resolve_run_selection(run_ids, *, selected=None, observed=None, latest_run=None):
    """Follow new successful runs while preserving manual historical selection."""
    available = [str(value) for value in run_ids if value]
    latest = str(latest_run) if latest_run else None

    if not available:
        return None, latest

    if latest and latest in available and latest != observed:
        return latest, latest

    if selected in available:
        return selected, latest

    if latest and latest in available:
        return latest, latest

    return available[-1], latest
