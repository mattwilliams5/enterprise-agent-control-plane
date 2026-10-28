from applications.storeguard.state_machine import StoreState
from ui.storeguard.view_models import StoreMode


def test_backend_states_map_to_gui_modes():
    for state in StoreState:
        gui_mode = StoreMode[state.name]

        assert gui_mode.name == state.name