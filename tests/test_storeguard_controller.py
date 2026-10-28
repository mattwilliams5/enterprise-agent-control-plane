from applications.storeguard.controller import StoreGuardController
from applications.storeguard.state_machine import StoreState


def test_controller_registers_store():
    controller = StoreGuardController()

    controller.register_store(1847)

    assert "1847" in controller.stores
    assert controller.stores["1847"].state == StoreState.NORMAL

def test_controller_allows_valid_transition():
    controller = StoreGuardController()
    controller.register_store(1847)

    result = controller.request_transition(1847, StoreState.PROTECTED)

    assert result is True
    assert controller.stores["1847"].state == StoreState.PROTECTED

def test_controller_rejects_invalid_transition():
    controller = StoreGuardController()
    controller.register_store(1847)

    # Request NORMAL → RECOVERY
    result = controller.request_transition(1847, StoreState.RECOVERY)

    # Assert the result is False
    assert result is False

    # Assert the store remains NORMAL
    assert controller.stores["1847"].state == StoreState.NORMAL