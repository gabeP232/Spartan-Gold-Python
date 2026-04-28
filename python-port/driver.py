import threading
import time

import blockchain as bc_module
from miner import Miner
from fake_net import FakeNet

print("Starting simulation. This may take a moment...")

bc = bc_module.Blockchain.create_instance({
    'clients': [
        {'name': 'Alice', 'amount': 233},
        {'name': 'Bob', 'amount': 99},
        {'name': 'Charlie', 'amount': 67},
        {'name': 'Minnie', 'amount': 400, 'mining': True},
        {'name': 'Mickey', 'amount': 300, 'mining': True},
    ],
    'mnemonic': (
        "antenna dwarf settle sleep must wool ocean once banna tiger distance gate "
        "great similar chief cheap dinner dolphin picture swing twenty two file nuclear"
    ),
    'net': FakeNet(),
})

alice, bob = bc.get_clients('Alice', 'Bob')

print("Initial balances:")
alice.show_all_balances()

bc.start(8000, lambda: (print("\nFinal balances, from Alice's perspective:"), alice.show_all_balances()))

print(f"Alice is transferring 40 gold to {bob.address}")
alice.post_transaction([{'amount': 40, 'address': bob.address}])

def _add_late_miner():
    donald = Miner({
        'name': 'Donald',
        'startingBlock': bc.genesis,
        'miningRounds': 3000,
    })
    print()
    print("***Starting a late-to-the-party miner***")
    print()
    bc.register(donald)
    donald.initialize()

threading.Timer(2.0, _add_late_miner).start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass