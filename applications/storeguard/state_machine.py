from enum import Enum


# 1. Define the possible states
class StoreState(Enum):
    NORMAL = "normal"
    PROTECTED = "protected"
    MAINTENANCE = "maintenance"
    RECOVERY = "recovery"


# 2. Define legal transitions
ALLOWED_TRANSITIONS = {
    StoreState.NORMAL: {StoreState.PROTECTED},
    StoreState.PROTECTED: {
        StoreState.MAINTENANCE,
        StoreState.NORMAL
    },
    StoreState.MAINTENANCE: {StoreState.RECOVERY},
    StoreState.RECOVERY: {StoreState.NORMAL}
}


# 3. Validate transitions
def can_transition(current_state, new_state):
    return new_state in ALLOWED_TRANSITIONS.get(current_state, set())


# 4. Store class goes HERE
class Store:
    def __init__(self, store_id):
        self.store_id = store_id
        self.state = StoreState.NORMAL

    def transition(self, new_state):
        if can_transition(self.state, new_state):
            self.state = new_state
            return True
        else:
            return False

    # What goes here?'s state here
        # Return True
    # Return False if denied
    

# 5. Manual testing
if __name__ == "__main__":
    store = Store(1847)

    print("Initial:", store.state)

    result = store.transition(StoreState.PROTECTED)
    print("Allowed:", result)
    print("Current:", store.state)

    result = store.transition(StoreState.RECOVERY)
    print("Allowed:", result)
    print("Current:", store.state)