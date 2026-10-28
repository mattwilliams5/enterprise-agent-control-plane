from applications.storeguard.state_machine import Store, StoreState


def test_store_starts_normal():
    store = Store(1847)

    assert store.state == StoreState.NORMAL

def test_valid_transition():
    store = Store(1847)

    result = store.transition(StoreState.PROTECTED)

    assert result is True
    assert store.state == StoreState.PROTECTED

def test_invalid_transition():
    store = Store(1847)

    result = store.transition(StoreState.RECOVERY)

    assert result is False
    assert store.state == StoreState.NORMAL
