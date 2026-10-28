from applications.storeguard.state_machine import Store, StoreState


def test_store_starts_normal():
    store = Store(1847)

    assert store.state == StoreState.NORMAL