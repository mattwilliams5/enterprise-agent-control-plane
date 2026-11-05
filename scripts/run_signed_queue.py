"""Operator-triggered local signed SQLite queue flush; no background loop."""
import argparse
from pathlib import Path
from applications.storeguard.cloud_dr.delivery_reliability import DeliveryState
from applications.storeguard.cloud_dr.signed_queue_delivery import deliver_signed_queue


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue-db', required=True)
    p.add_argument('--identities', default='.local/storeguard-identity-demo')
    p.add_argument('--base-url', default='http://127.0.0.1:8081')
    p.add_argument('--max-items', type=int, default=40)
    a = p.parse_args()
    state = DeliveryState(Path(a.queue_db))
    try:
        for item in deliver_signed_queue(state, identity_directory=a.identities,
                                         base_url=a.base_url, max_items=a.max_items):
            print(item)
    finally:
        state.close()


if __name__ == '__main__':
    main()
