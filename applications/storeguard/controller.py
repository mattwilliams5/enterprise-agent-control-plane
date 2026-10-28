from applications.storeguard.state_machine import Store, StoreState


class StoreGuardController:
    def __init__(self):
        self.stores = {}

    def register_store(self, store_id):
        store_id = str(store_id)
        self.stores[store_id] = Store(store_id)

    def request_transition(self, store_id, new_state):
        store_id = str(store_id)
        store = self.stores.get(store_id)

        if store is None:
            return False

        return store.transition(new_state)