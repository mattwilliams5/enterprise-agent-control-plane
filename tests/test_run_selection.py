from ui.storeguard.run_selection import resolve_run_selection


def test_new_successful_run_is_selected():
    assert resolve_run_selection(
        ["old", "new"], selected="old", observed="old", latest_run="new"
    ) == ("new", "new")


def test_manual_historical_selection_is_preserved():
    assert resolve_run_selection(
        ["old", "new"], selected="old", observed="new", latest_run="new"
    ) == ("old", "new")


def test_missing_selection_defaults_to_latest():
    assert resolve_run_selection(
        ["old", "new"], selected="missing", observed="new", latest_run="new"
    ) == ("new", "new")


def test_no_audit_runs_returns_no_selection():
    assert resolve_run_selection(
        [], selected="old", observed="old", latest_run=None
    ) == (None, None)


def test_new_failure_does_not_select_historical_success():
    assert resolve_run_selection(
        ["old"], selected="old", observed="old", latest_run="old"
    ) == ("old", "old")
