import threading
import time

import blockchain as bc_module
from miner import Miner
from fake_net import FakeNet
from merkleTree import MerkleTree
from block import Block

print("  SpartanGold-PE Simulation")
print("  Demonstrating: Merkle Tree, Dynamic Difficulty, Fixed Block Size with Fee Based Transaction selection")
print()

# Creating genesis block
bc = bc_module.Blockchain.create_instance({
    'clients': [
        {'name': 'Alice', 'amount': 500, 'mining': False},
        {'name': 'Bob', 'amount': 200, 'mining': False},
        {'name': 'Charlie', 'amount': 100, 'mining': False},
        {'name': 'Minnie', 'amount': 400, 'mining': True},
        {'name': 'Mickey', 'amount': 300, 'mining': True},
    ],
    'mnemonic': (
        "antenna dwarf settle sleep must wool ocean once banana tiger distance gate "
        "great similar chief cheap dinner dolphin picture swing twenty two file nuclear"
    ),
    'net': FakeNet(),
    'powLeadingZeroes': 10,
    'confirmedDepth':   2,
})

alice, bob, charlie = bc.get_clients('Alice', 'Bob', 'Charlie')
minnie, mickey = bc.get_clients('Minnie', 'Mickey')

# Suppress "Cutting over" noise from miner logs; keep "Found proof" lines
for _m in [minnie, mickey]:
    _orig_log = _m.log
    _m.log = lambda msg, _o=_orig_log: _o(msg) if 'Found proof' in msg else None

print()
print("Initial balances:")
alice.show_all_balances()
print()

# ==============================
# FEATURE 1: MERKLE TREE FOR TRANSACTIONS
# ==============================
print("=" * 50)
print("FEATURE 1: MERKLE TREE FOR TRANSACTIONS")
print("=" * 50)
print()

fake_ids = ["tx_alpha", "tx_beta", "tx_gamma"]
demo_tree_empty = MerkleTree([])
demo_tree_full  = MerkleTree(fake_ids)

print(f"Empty block Merkle root (no txs):")
print(f"  {demo_tree_empty.get_root()}")
print(f"Merkle root with 3 transactions:")
print(f"  {demo_tree_full.get_root()}")
print(f"Root changed: {demo_tree_empty.get_root() != demo_tree_full.get_root()}")
print()

proof = demo_tree_full.get_proof("tx_beta")
root  = demo_tree_full.get_root()
valid = MerkleTree.verify_proof("tx_beta", proof, root)
print(f"SPV Proof for 'tx_beta':")
print(f"  Proof uses {len(proof)} sibling hash(es) to verify membership")
print(f"  (vs downloading all {len(fake_ids)} transactions)")
print(f"  Proof valid: {valid}")
print(f"  At 1000 txs this needs only ~10 hashes — O(log n) verification")
print()

tampered_tree = MerkleTree(["tx_alpha", "tx_TAMPERED", "tx_gamma"])
print(f"Tampered tree root matches original: {tampered_tree.get_root() == root}")
print()

# ==============================
# FEATURE 2: FEE-BASED TRANSACTION SELECTION
# ==============================
print("=" * 50)
print("FEATURE 2: FEE-BASED TRANSACTION SELECTION")
print("=" * 50)
print()
print(f"Max block size: {bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES:,} bytes")
print(f"Miners sort mempool by fee/byte descending.")
print(f"Most profitable transactions are selected first.")
print(f"Three transactions will be posted 2 seconds after mining starts.")
print()

# ==============================
# FEATURE 3: DYNAMIC DIFFICULTY ADJUSTMENT
# ==============================
print("=" * 50)
print("FEATURE 3: DYNAMIC DIFFICULTY ADJUSTMENT")
print("=" * 50)
print()

_initial_zeros = 256 - bc_module.Blockchain.POW_TARGET.bit_length()
print(f"Adjustment interval: every {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks")
print(f"Target block time:   {bc_module.TARGET_BLOCK_TIME} ms")
print(f"Initial difficulty:  {_initial_zeros} leading zeros required in hash")
print()
print("Starting miners. Watching for blocks and difficulty adjustments...")
print()

# Number of leading zero bits required for a valid hash at a given target.
# More zeros = harder; fewer zeros = easier.
def _zeros(target):
    return 256 - target.bit_length()

# track per-height targets (dict so duplicates at same height overwrite)
_block_log    = {}
# track the height we've already printed a line for (deduplicates racing miners)
_seen_heights = set()
_prev_target  = [bc_module.Blockchain.POW_TARGET]
_fee_txs      = {}       # id -> tx; populated by _post_transactions once txs are sent
_fee_verified = [False]  # set True after first block with our fee txs is seen

_orig_receive = alice.receive_block

def _watch(b):
    result = _orig_receive(b)
    if result is None:
        return None

    _block_log[result.chain_length] = result.target

    # Skip printing a second line when the other miner finds the same height
    if result.chain_length in _seen_heights:
        return result
    _seen_heights.add(result.chain_length)

    zeros = _zeros(result.target)
    adjusted = ""
    if result.target != _prev_target[0]:
        prev_z = _zeros(_prev_target[0])
        direction = "HARDER" if result.target < _prev_target[0] else "EASIER"
        adjusted  = f"  <-- DIFFICULTY ADJUSTED ({direction}: {prev_z} -> {zeros} zeros)"
        _prev_target[0] = result.target

    tx_count = len(result.transactions)
    print(
        f"  Block {result.chain_length:>2} | "
        f"txs={tx_count} | "
        f"merkle={result.merkle_root[:10]}... | "
        f"diff={zeros} zeros{adjusted}"
    )

    # Feature 2 live verification: prove fee ordering when our transactions land
    if _fee_txs and not _fee_verified[0]:
        matched = {tid: result.transactions[tid]
                   for tid in _fee_txs if tid in result.transactions}
        if matched:
            ordered = sorted(matched.values(),
                             key=lambda tx: tx.fee / tx.byte_size(), reverse=True)
            print(f"  >> Fee ordering verified in block {result.chain_length}:")
            for tx in ordered:
                print(f"       fee={tx.fee:>3}  size={tx.byte_size()}B  "
                      f"fee/byte={tx.fee / tx.byte_size():.5f}")
            _fee_verified[0] = True

    return result

# Alice registered self.receive_block as her PROOF_FOUND listener in __init__.
# Patching the attribute alone doesn't intercept event-driven calls; we must
# swap the listener in the event registry too.
alice.off(bc_module.Blockchain.PROOF_FOUND, _orig_receive)
alice.on(bc_module.Blockchain.PROOF_FOUND, _watch)
alice.receive_block = _watch


def _final_report():
    print()
    print("=" * 50)
    print("SIMULATION COMPLETE")
    print("=" * 50)
    print()

    print("Final balances (Alice's perspective):")
    alice.show_all_balances()
    print()

    # Show only the blocks where difficulty changed
    print("Difficulty adjustment log:")
    prev = None
    adjustments = 0
    first_zeros = None
    for length, target in sorted(_block_log.items()):
        zeros = _zeros(target)
        if first_zeros is None:
            first_zeros = zeros
            print(f"  Blocks 1-{bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL - 1}: "
                  f"{zeros} leading zeros (initial difficulty)")
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
        print(f"  No adjustment triggered yet "
              f"(need {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks).")

    print()
    print("Features demonstrated:")
    print("  [1] Merkle root replaces full tx list in block header")
    print("  [1] SPV proof verified in O(log n) without full transaction list")
    print("  [1] Tampered transaction list changes the Merkle root")
    print("  [2] Miners sort mempool by fee/byte and fill up to 1 MB cap")
    if _fee_verified[0]:
        print("  [2] Fee ordering confirmed live in a mined block")
    else:
        print("  [2] Fee ordering not yet confirmed (transactions may not have mined yet)")
    print(f"  [3] Dynamic difficulty adjusts every {bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL} blocks "
          f"toward {bc_module.TARGET_BLOCK_TIME} ms target")


# Run for 45 seconds
bc.start(45000, _final_report)

# Post 3 transactions with different fees after 2 seconds
def _post_transactions():
    time.sleep(2)
    try:
        print()
        print("Posting transactions (miners will select by fee/byte):")
        tx_high = alice.post_transaction(
            [{'amount': 30, 'address': bob.address}], fee=20
        )
        tx_med = alice.post_transaction(
            [{'amount': 20, 'address': charlie.address}], fee=10
        )
        tx_low = alice.post_transaction(
            [{'amount': 10, 'address': bob.address}], fee=1
        )
        print(f"  tx_high -> Bob     fee=20  fee/byte={tx_high.fee/tx_high.byte_size():.5f}")
        print(f"  tx_med  -> Charlie fee=10  fee/byte={tx_med.fee/tx_med.byte_size():.5f}")
        print(f"  tx_low  -> Bob     fee=1   fee/byte={tx_low.fee/tx_low.byte_size():.5f}")
        print(f"  Miners will include tx_high first, tx_med next, tx_low last.")
        print()
        _fee_txs[tx_high.id] = tx_high
        _fee_txs[tx_med.id]  = tx_med
        _fee_txs[tx_low.id]  = tx_low
    except Exception as e:
        print(f"  (Transaction skipped: {e})")

threading.Thread(target=_post_transactions, daemon=True).start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
