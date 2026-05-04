import threading
import time

# Patch difficulty constants BEFORE importing blockchain 
# TARGET_BLOCK_TIME is a module-level constant used directly in calculate_target().
# We set it to 3000ms (3s per block) so blocks mine faster than the target
# early on, causing HARDER adjustments, then as difficulty climbs miners slow
# down below the target and we see EASIER adjustments too.
# DIFFICULTY_ADJUSTMENT_INTERVAL is set to 5 so we see adjustments more often.
import blockchain as bc_module
bc_module.TARGET_BLOCK_TIME = 3000  # 3s target per block
bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL = 5  # adjust every 5 blocks

from fake_net import FakeNet
from merkleTree import MerkleTree

print("SpartanGold-Python Simulation")
print("Demonstrating: Merkle Tree, Dynamic Difficulty, Fee-Based Transaction Selection")
print()

# genesis block 
bc = bc_module.Blockchain.create_instance({
    'clients': [
        {'name': 'Alice', 'amount': 2000, 'mining': False},
        {'name': 'Bob', 'amount': 200, 'mining': False},
        {'name': 'Charlie','amount': 200, 'mining': False},
        {'name': 'Minnie','amount': 400, 'mining': True},
        {'name': 'Mickey', 'amount': 300, 'mining': True},
    ],
    'mnemonic': (
        "antenna dwarf settle sleep must wool ocean once banana tiger distance gate "
        "great similar chief cheap dinner dolphin picture swing twenty two file nuclear"
    ),
    'net': FakeNet(),
    'powLeadingZeroes': 16,
    'confirmedDepth': 2,
})

alice, bob, charlie = bc.get_clients('Alice', 'Bob', 'Charlie')
minnie, mickey = bc.get_clients('Minnie', 'Mickey')

# Suppress miner noise  keep only "Found proof" lines
for _m in [minnie, mickey]:
    _orig_log = _m.log
    _m.log = lambda msg, _o=_orig_log: _o(msg) if 'Found proof' in msg else None

print()
print("Initial balances:")
alice.show_all_balances()
print()

# FEATURE 1 — MERKLE TREE
print("FEATURE 1: MERKLE TREE FOR TRANSACTIONS")
print()

demo_tree_empty = MerkleTree([])
demo_tree_full = MerkleTree(["tx_a", "tx_b", "tx_c"])

# Demo an empty merkle tree when there are no txs
print("Empty block Merkle root (no user txs):")
print(f" {demo_tree_empty.get_root()}")
# Show how it changes and is stored when there are txs on the block
print("Merkle root with 3 transactions:")
print(f" {demo_tree_full.get_root()}")
print(f"Root changed: {demo_tree_empty.get_root() != demo_tree_full.get_root()}")
print()

# FEATURE 2 — FEE-BASED TRANSACTION SELECTION
print("FEATURE 2: FEE-BASED TRANSACTION SELECTION")
print()
print(f"Max block size: {bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES:,} bytes")
print("Miners sort mempool by fee/byte descending.")
print("Most profitable transactions are selected first.")
print("Three waves of transactions will be posted at t=1s, t=15s, t=30s.")
print()

# FEATURE 3 — DYNAMIC DIFFICULTY ADJUSTMENT
print("FEATURE 3: DYNAMIC DIFFICULTY ADJUSTMENT")
print()

_initial_zeros = 256 - bc_module.Blockchain.POW_TARGET.bit_length()
print(f"Adjustment interval: every {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks")

print(f"Target block time: {bc_module.TARGET_BLOCK_TIME} ms ({bc_module.TARGET_BLOCK_TIME // 1000}s per block)")

print(f"Initial difficulty: {_initial_zeros} leading zeros required in hash")

print(f"Window target: {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} x {bc_module.TARGET_BLOCK_TIME}ms = "
      f"{bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL * bc_module.TARGET_BLOCK_TIME // 1000}s")

print("Faster than target -> HARDER  |  Slower than target -> EASIER")
print()
print("Starting miners. Watching for blocks and difficulty adjustments...")
print()

# helpers 
def _zeros(target):
    return 256 - target.bit_length()

#  tracking state 
# maps block height and PoW target at that height
_block_log = {}
# prevents from printing same block twice, so only display the block Alice accepts into the chain
_seen_heights = set()
# tracks list of known targets to detect when it changes
_prev_target = [bc_module.Blockchain.POW_TARGET]
# maps the tx.id to the tx for every tx posted 
_all_fee_txs = {}
# set of tx ids already confirmed, so no reporting twice
_confirmed = set()
_lock = threading.Lock()

# block watcher 
# called every time a block is received
# For each block
#   record the blocks PoW target in block log
#   Skip block if already printed
#   check if target has changed since last block, then print difficulty if it has
#   print a summary: block num, tx count, merkle root, difficulty
#   Check if any fee txs were included in the block and print them in fee/byte order
_orig_receive = alice.receive_block

def _watch(b):
    result = _orig_receive(b)
    if result is None:
        return None

    h = result.chain_length
    with _lock:
        _block_log[h] = result.target

    if h in _seen_heights:
        return result
    _seen_heights.add(h)

    zeros = _zeros(result.target)

    adjusted = ""
    if result.target != _prev_target[0]:
        prev_z = _zeros(_prev_target[0])
        direction = "HARDER" if result.target < _prev_target[0] else "EASIER"
        adjusted = f"   DIFFICULTY ADJUSTED ({direction}: {prev_z} -> {zeros} zeros)"
        _prev_target[0] = result.target

    root = result.merkle_root
    root_str = root[:10] + "..." if root != "0" * 64 else "[no user txs]  "

    # Print the 
    print(
        f"  Block {h:>2} | "
        f"txs={len(result.transactions)} | "
        f"merkle={root_str} | "
        f"diff={zeros} zeros{adjusted}"
    )

    # Show fee txs confirmed in this block, highest fee/byte first
    with _lock:
        newly = {
            tid: result.transactions[tid]
            for tid in _all_fee_txs
            if tid in result.transactions and tid not in _confirmed
        }
        if newly:
            ordered = sorted(newly.values(),
                             key=lambda tx: tx.fee / tx.byte_size(),
                             reverse=True)
            print(f" -> Fee txs confirmed in block {h}, highest fee/byte first:")
            for tx in ordered:
                fpb = tx.fee / tx.byte_size()
                print(f"       fee={tx.fee:>3}  size={tx.byte_size()}B  fee/byte={fpb:.5f}")
            _confirmed.update(newly.keys())

            if _confirmed >= set(_all_fee_txs.keys()):
                print(f" -> All {len(_all_fee_txs)} fee txs confirmed")

    return result

alice.off(bc_module.Blockchain.PROOF_FOUND, _orig_receive)
alice.on(bc_module.Blockchain.PROOF_FOUND, _watch)
alice.receive_block = _watch

#final report
def _final_report():
    print()
    print("SIMULATION COMPLETE")
    print()

    print("Final balances Alice's POV:")
    alice.show_all_balances()
    print()

    with _lock:
        log_snap = dict(_block_log)
        conf_snap = set(_confirmed)
        fee_snap = dict(_all_fee_txs)

    print("Difficulty adjustment log:")
    prev = None
    adjustments = 0
    first_zeros = None
    for length, target in sorted(log_snap.items()):
        zeros = _zeros(target)
        if first_zeros is None:
            first_zeros = zeros
            print(f"  Blocks 1-{bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL - 1}: {zeros} leading zeros (initial)")
        if prev is not None and target != prev:
            prev_z = _zeros(prev)
            direction = "HARDER" if target < prev else "EASIER"
            print(f"  Block {length:>2}: {prev_z} -> {zeros} zeros ({direction})")
            adjustments += 1
        prev = target

    print()
    if adjustments:
        print(f"  Total difficulty adjustments: {adjustments}")
    else:
        print(f"  No adjustment triggered (need {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks per window).")

    print()
    print("Features demonstrated:")
    print(" Merkle root replaces full tx list in block header")
    print(" Coinbase-only blocks show zero root (user txs only are hashed)")
    print(" Miners sort mempool by fee/byte and fill up to 1 MB cap")
    if conf_snap and fee_snap:
        ordered = sorted(
            [fee_snap[tid] for tid in conf_snap if tid in fee_snap],
            key=lambda tx: tx.fee / tx.byte_size(),
            reverse=True,
        )
        print(f" Fee ordering confirmed - {len(conf_snap)}/{len(fee_snap)} txs mined in order:")
        for tx in ordered:
            fpb = tx.fee / tx.byte_size()
            print(f"      fee={tx.fee:>3}  size={tx.byte_size()}B  fee/byte={fpb:.5f}")
    print(f" Dynamic difficulty adjusts every {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks "
          f"toward {bc_module.TARGET_BLOCK_TIME}ms target")

# start network for 90 secs
bc.start(90000, _final_report)

# TRANSACTION WAVES
# To demonstrate fee-based selection we post transactions in three separate
# "waves" at different points during the simulation. Each wave is sent from
# a background thread that sleeps until its scheduled time (delay_s).
#
# The t=Ns notation means "N seconds after the simulation starts":
# Wave 1 at t=1s, Wave 2 at t=15s, Wave 3 at t=30s 
#
# Each wave has 5 transactions with different fees so we can verify the miner
# always picks the highest fee/byte transaction from whatever is in the mempool.
# _WAVES is a list of tuples: (delay_in_seconds, list_of_(amount, fee)_pairs).
_WAVES = [
    (1, [(30, 50), (20, 30), (15, 20), (10, 10), (5, 1)]),
    (15, [(25, 45), (18, 25), (12, 15), (8, 5), (3, 2)]),
    (30, [(35, 60), (22, 35), (14, 12), (9, 7), (4, 3)]),
]

# We cycle through these recipient addresses so not every transaction goes to
# the same person.
_RECIPIENTS = [bob.address, charlie.address, bob.address, charlie.address, bob.address]

# After all txs are done and the driver run finishes
def _post_wave(wave_num, delay_s, outputs_fees):
    # Sleep until this wave's scheduled time. Because this runs in a daemon
    # thread, it doesn't block the main thread or the miners.
    time.sleep(delay_s)

    rows = []
    for i, (amt, fee) in enumerate(outputs_fees):
        try:
            # post_transaction() signs the transaction with Alice's key and broadcasts it to the network so
            # both Minnie and Mickey see it
            # We register each tx in _all_fee_txs immediately so _watch can
            # match it even if a block is found before the loop finishes
            tx = alice.post_transaction(
                [{'amount': amt, 'address': _RECIPIENTS[i % len(_RECIPIENTS)]}],
                fee=fee,
            )
            with _lock:
                _all_fee_txs[tx.id] = tx
                
            rows.append((fee, tx.byte_size(), fee / tx.byte_size()))
            
        except Exception as e:
            print(f" (Wave {wave_num} tx skipped: {e})")

    # Sort and print so we can see what the miner should prefer
    rows.sort(key=lambda r: r[2], reverse=True)
    print()
    print(f"Posting Wave {wave_num} at t={delay_s}s - miners will select by fee/byte:")
    for fee, sz, fpb in rows:
        print(f"  fee={fee:>3}  size={sz}B  fee/byte={fpb:.5f}")
    print()

# Launch each wave in its own daemon thread so they fire independently at
# their scheduled times without blocking each other or the main loop
for wave_num, (delay, of) in enumerate(_WAVES, start=1):
    threading.Thread(
        target=_post_wave,
        args=(wave_num, delay, of),
        daemon=True,
    ).start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass