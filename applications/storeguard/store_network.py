"""Geographic store registry for StoreGuard."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class StoreLocation:
    store_id: str
    name: str
    region: str
    latitude: float
    longitude: float

    def __post_init__(self):
        if not self.store_id.strip():
            raise ValueError("Store ID cannot be empty")
        if not self.name.strip():
            raise ValueError("Store name cannot be empty")
        if not self.region.strip():
            raise ValueError("Region cannot be empty")
        if not -90 <= self.latitude <= 90:
            raise ValueError("Invalid latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError("Invalid longitude")


class StoreNetwork:
    def __init__(self):
        self._stores = {}

    def register(self, store: StoreLocation):
        if store.store_id in self._stores:
            raise ValueError(f"Duplicate store: {store.store_id}")
        self._stores[store.store_id] = store

    def get(self, store_id: str):
        return self._stores.get(str(store_id))

    def all_stores(self):
        return tuple(self._stores.values())

    def by_region(self, region: str):
        return tuple(
            store for store in self._stores.values()
            if store.region == region
        )

    def __len__(self):
        return len(self._stores)


def build_demo_network() -> StoreNetwork:
    """Create 40 fictional stores with deterministic US coordinates."""
    regions = {
        "Oklahoma": (35.4676, -97.5164),
        "Kansas": (37.6872, -97.3301),
        "Texas": (32.7767, -96.7970),
        "Missouri": (39.0997, -94.5786),
    }

    network = StoreNetwork()

    for region_index, (region, center) in enumerate(regions.items()):
        for local_index in range(10):
            number = region_index * 10 + local_index + 1
            row, column = divmod(local_index, 5)

            network.register(
                StoreLocation(
                    store_id=f"SG-{number:03d}",
                    name=f"Store {number:03d}",
                    region=region,
                    latitude=round(center[0] + (row - 0.5) * 0.12, 5),
                    longitude=round(center[1] + (column - 2) * 0.12, 5),
                )
            )

    return network
