import pytest

import utils
import blockchain as bc_module
from block import Block
from transaction import Transaction
from client import Client
from miner import Miner

KP = utils.generate_keypair()
ADDR = utils.calc_address(KP['public'])

EASY_POW_TARGET = int("0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16)

# Ensures a fresh Blockchain for every test.
@pytest.fixture(autouse = True)
def reset_blockchain():
    bc_module.Blockchain.reset_instance()
    bc_module.Blockchain.create_instance({
        'blockClass': Block,
        'transactionClass': Transaction,
    })
    yield
    bc_module.Blockchain.reset_instance()

class TestUtils:
    def setup_method(self):
        self.sig = utils.sign(KP['private'], "hello")

    def test_valid_signature_accepted(self):
        assert utils.verify_signatures(KP['public'], "hello", self.sig)

    def test_invalid_signature_rejected(self):
        assert not utils.verify_signatures(KP['public'], "goodbye", self.sig)

class TestTransaction:
    def setup_method(self):
        outputs = [
            {'amount': 20, 'address': 'ffff'},
            {'amount': 40, 'address': 'face'},
        ]
        self.tx = Transaction({
            'from': ADDR,
            'pubKey': KP['public'],
            'outputs': outputs,
            'fee': 1,
            'nonce': 1
        })
        self.tx.sign(KP['private'])

    def test_total_output_sums_outputs_and_fee(self):
        assert self.tx.total_output() == 61

class TestBlock:
    def setup_method(self):
        self.prev_block = Block("8e7912")
        self.prev_block.balances = {ADDR: 500, 'ffff': 100, 'face': 99}

        outputs= [
            {'amount': 20, 'address': 'ffff'},
            {'amount': 40, 'address': 'face'},
        ]
        self.t = Transaction({
            'from': ADDR,
            'pubKey': KP['public'],
            'outputs': outputs,
            'fee': 1,
            'nonce': 0,
        })

    def test_add_transaction_fails_if_unsigned(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        assert b.add_transaction(tx) is False

    def test_add_transaction_fails_if_insufficient_funds(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.outputs = [{'amount': 20000000000000, 'address': 'ffff'}]
        tx.sign(KP['private'])
        assert b.add_transaction(tx) is False

    def test_add_transaction_transfers_gold(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)
        assert b.balances.get(ADDR) == 500 - 61
        assert b.balances.get('ffff') == 100 + 20
        assert b.balances.get('face') == 99 + 40

    def test_add_transaction_ignores_duplicate_from_previous_block(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)

        b2 = Block(ADDR, b)
        b2.add_transaction(tx)
        assert len(b2.transactions) == 0

    def test_rerun_restores_balances(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)

        b.balances = {}
        b.rerun(self.prev_block)

        assert self.prev_block.balances.get(ADDR) == 500
        assert self.prev_block.balances.get('ffff') == 100
        assert self.prev_block.balances.get('face') == 99

        assert b.balances.get(ADDR) == 500 - 61
        assert b.balances.get('ffff') == 100 + 20
        assert b.balances.get('face') == 99 + 40

    def test_rerun_after_serialize_deserialize_matches_hash(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)

        original_hash = b.hash_val()

        o = b.to_json()
        b2 = bc_module.Blockchain.deserialize_block(o)
        b2.rerun(self.prev_block)

        assert b2.hash_val() == original_hash
        assert b2.balances.get(ADDR) == 500 - 61
        assert b2.balances.get('ffff') == 100 + 20
        assert b2.balances.get('face') == 99 + 40

class TestClient:
    def setup_method(self):
        self.genesis = Block("8e7912")
        self.genesis.balances = {ADDR: 500, 'ffff': 100, 'face': 99}

        class _MockNet:
            def broadcast(self, *a): pass
            def send_message(self, *a): pass

        self.net = _MockNet()

        outputs1 = [{'amount': 20, 'address': 'ffff'}, {'amount': 40, 'address': 'face'}]
        self.t = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': outputs1, 'fee': 1, 'nonce': 0})
        self.t.sign(KP['private'])

        outputs2 = [{'amount': 10, 'address': 'face'}]
        self.t2 = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': outputs2, 'fee': 1, 'nonce': 1})
        self.t2.sign(KP['private'])

        self.clint = Client({'net': self.net, 'startingBlock': self.genesis})
        self.clint.log = lambda msg: None

        self.miner = Miner({'name': 'Minnie', 'net': self.net, 'startingBlock': self.genesis})
        self.miner.log = lambda msg: None

    # Force the miner to search until it finds a valid proof.
    def _mine_block(self, block):
        self.miner.current_block = block
        block.proof = 0
        self.miner.find_proof(one_and_done = True)

    def test_receive_block_rejects_block_without_valid_proof(self):
        b = Block(ADDR, self.genesis)
        b.add_transaction(self.t)
        result = self.clint.receive_block(b)
        assert result is None

    def test_receive_block_stores_valid_blocks_and_updates_last_block(self):
        b = Block(ADDR, self.genesis, EASY_POW_TARGET)
        b.add_transaction(self.t)
        self._mine_block(b)

        self.clint.receive_block(b)
        assert self.clint.blocks.get(b.id) is b
        assert self.clint.last_block is b

        b2 = Block(ADDR, b, EASY_POW_TARGET)
        b2.add_transaction(self.t2)
        self._mine_block(b2)

        self.clint.receive_block(b2)
        assert self.clint.blocks.get(b2.id) is b2
        assert self.clint.last_block is b2

        b_alt = Block(ADDR, self.genesis, EASY_POW_TARGET)
        b_alt.add_transaction(self.t2)
        self._mine_block(b_alt)

        self.clint.receive_block(b_alt)
        assert self.clint.blocks.get(b_alt.id) is b_alt
        assert self.clint.last_block is b2


from merkleTree import MerkleTree

class TestMerkleTree:
    def test_empty_tree_returns_empty_hash(self):
        tree = MerkleTree([])
        assert tree.get_root() == MerkleTree.EMPTY_HASH

    def test_single_tx_root_equals_hash_of_tx_id(self):
        import utils
        tx_id = "abc123"
        tree = MerkleTree([tx_id])
        assert tree.get_root() == utils.hash(tx_id)

    def test_two_tx_root_differs_from_single(self):
        tree1 = MerkleTree(["tx1"])
        tree2 = MerkleTree(["tx1", "tx2"])
        assert tree1.get_root() != tree2.get_root()

    def test_includes_transaction_true_for_member(self):
        tree = MerkleTree(["tx1", "tx2"])
        assert tree.includes_transaction("tx1") is True
        assert tree.includes_transaction("tx2") is True

    def test_includes_transaction_false_for_non_member(self):
        tree = MerkleTree(["tx1", "tx2"])
        assert tree.includes_transaction("tx99") is False

    def test_includes_transaction_false_on_empty_tree(self):
        tree = MerkleTree([])
        assert tree.includes_transaction("tx1") is False

    def test_get_proof_returns_none_for_missing_tx(self):
        tree = MerkleTree(["tx1"])
        assert tree.get_proof("tx99") is None

    def test_verify_proof_valid_for_single_tx(self):
        tx_id = "abc"
        tree = MerkleTree([tx_id])
        proof = tree.get_proof(tx_id)
        assert MerkleTree.verify_proof(tx_id, proof, tree.get_root()) is True

    def test_verify_proof_valid_for_multiple_txs(self):
        ids = ["tx1", "tx2", "tx3", "tx4"]
        tree = MerkleTree(ids)
        root = tree.get_root()
        for tx_id in ids:
            proof = tree.get_proof(tx_id)
            assert MerkleTree.verify_proof(tx_id, proof, root) is True

    def test_verify_proof_fails_for_wrong_tx_id(self):
        ids = ["tx1", "tx2"]
        tree = MerkleTree(ids)
        proof = tree.get_proof("tx1")
        assert MerkleTree.verify_proof("tx2", proof, tree.get_root()) is False

    def test_odd_number_of_txs_still_produces_valid_proof(self):
        ids = ["tx1", "tx2", "tx3"]
        tree = MerkleTree(ids)
        root = tree.get_root()
        for tx_id in ids:
            proof = tree.get_proof(tx_id)
            assert MerkleTree.verify_proof(tx_id, proof, root) is True

class TestMerkleBlockIntegration:
    def setup_method(self):
        self.prev_block = Block("8e7912")
        self.prev_block.balances = {ADDR: 500, 'ffff': 100, 'face': 99}
        outputs = [{'amount': 20, 'address': 'ffff'}, {'amount': 40, 'address': 'face'}]
        self.t = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': outputs, 'fee': 1, 'nonce': 0})

    def test_empty_block_has_empty_merkle_root(self):
        b = Block(ADDR, self.prev_block)
        assert b.merkle_root == MerkleTree.EMPTY_HASH

    def test_adding_transaction_updates_merkle_root(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)
        assert b.merkle_root != MerkleTree.EMPTY_HASH

    def test_block_contains_tx_via_merkle_root(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)
        assert b.contains(tx) is True

    def test_block_does_not_contain_unknown_tx(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        assert b.contains(tx) is False

    def test_merkle_root_stored_in_to_json(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)
        o = b.to_json()
        assert o['merkleRoot'] == b.merkle_root

    def test_deserialize_raises_on_tampered_transactions(self):
        b = Block(ADDR, self.prev_block)
        tx = Transaction(self.t)
        tx.sign(KP['private'])
        b.add_transaction(tx)

        o = b.to_json()
        fake_tx = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': [{'amount': 1, 'address': 'ffff'}], 'fee': 0, 'nonce': 99})
        fake_tx.sign(KP['private'])
        o['transactions'].append([fake_tx.id, fake_tx.to_dict()])

        with pytest.raises(ValueError, match = "Merkle root mismatch"):
            bc_module.Blockchain.deserialize_block(o)

from blockchain import DIFFICULTY_ADJUSTMENT_INTERVAL, POW_BASE_TARGET

class TestDynamicPoW:
    def setup_method(self):
        self.prev_block = Block("8e7912")
        self.prev_block.balances = {ADDR: 500}

    def test_target_stored_as_hex_in_to_json(self):
        b = Block(ADDR, self.prev_block)
        o = b.to_json()
        assert isinstance(o['target'], str)
        assert o['target'].startswith('0x')
        assert int(o['target'], 16) == b.target

    def test_deserialize_restores_target(self):
        b = Block(ADDR, self.prev_block)
        custom_target = EASY_POW_TARGET
        b.target = custom_target
        o = b.to_json()
        b2 = bc_module.Blockchain.deserialize_block(o)
        assert b2.target == custom_target

    def test_calculate_target_returns_base_when_insufficient_history(self):
        bc = bc_module.Blockchain.get_instance()
        short_block = Block(ADDR, self.prev_block)
        short_block.chain_length = 5
        result = bc_module.Blockchain.calculate_target(short_block)
        assert result == bc.pow_target

    def test_calculate_target_returns_base_when_no_miners(self):
        bc = bc_module.Blockchain.get_instance()
        deep_block = Block(ADDR, self.prev_block)
        deep_block.chain_length = DIFFICULTY_ADJUSTMENT_INTERVAL
        result = bc_module.Blockchain.calculate_target(deep_block)
        assert result == bc.pow_target

    def test_fast_mining_increases_difficulty(self):
        bc = bc_module.Blockchain.get_instance()
        miner = Miner({'name': 'TestMiner', 'net': None, 'startingBlock': self.prev_block})
        miner.log = lambda _: None
        bc_module.Blockchain.get_instance().miners.append(miner)

        chain = [self.prev_block]
        for i in range(DIFFICULTY_ADJUSTMENT_INTERVAL):
            blk = Block.__new__(Block)
            blk.chain_length = i + 1
            blk.prev_block_hash = chain[-1].id if hasattr(chain[-1], 'id') else None
            blk.timestamp = chain[-1].timestamp + 100
            blk.reward_addr = ADDR
            blk.target = bc.pow_target
            blk.coinbase_reward = bc.coinbase_reward
            blk.transactions = {}
            blk.balances = {}
            blk.next_nonce = {}
            blk.proof = 0
            blk.merkle_root = MerkleTree.EMPTY_HASH
            miner.blocks[blk.id] = blk
            chain.append(blk)

        old_target = bc.pow_target
        new_target = bc_module.Blockchain.calculate_target(chain[-1])

        # Mining was very fast which means difficulty should increase which means target should decrease
        assert new_target < old_target

    def test_slow_mining_decreases_difficulty(self):
        bc = bc_module.Blockchain.get_instance()
        miner = Miner({'name': 'TestMiner2', 'net': None, 'startingBlock': self.prev_block})
        miner.log = lambda _: None
        bc_module.Blockchain.get_instance().miners.append(miner)

        chain = [self.prev_block]
        for i in range(DIFFICULTY_ADJUSTMENT_INTERVAL):
            blk = Block.__new__(Block)
            blk.chain_length = i + 1
            blk.prev_block_hash = chain[-1].id if hasattr(chain[-1], 'id') else None
            blk.timestamp = chain[-1].timestamp + 1000000
            blk.reward_addr = ADDR
            blk.target = bc.pow_target
            blk.coinbase_reward = bc.coinbase_reward
            blk.transactions = {}
            blk.balances = {}
            blk.next_nonce = {}
            blk.proof = 0
            blk.merkle_root = MerkleTree.EMPTY_HASH
            miner.blocks[blk.id] = blk
            chain.append(blk)

        old_target = bc.pow_target
        new_target = bc_module.Blockchain.calculate_target(chain[-1])

        # Mining was very slow (1000s per block vs 10s target) so difficulty should decrease
        # meaning the target threshold increases (easier to find valid hashes)
        assert new_target > old_target

    def test_target_clamped_to_pow_base_target(self):
        bc = bc_module.Blockchain.get_instance()
        miner = Miner({'name': 'TestMiner3', 'net': None, 'startingBlock': self.prev_block})
        miner.log = lambda _: None
        bc_module.Blockchain.get_instance().miners.append(miner)

        chain = [self.prev_block]
        for i in range(DIFFICULTY_ADJUSTMENT_INTERVAL):
            blk = Block.__new__(Block)
            blk.chain_length = i + 1
            blk.prev_block_hash = chain[-1].id if hasattr(chain[-1], 'id') else None
            blk.timestamp = chain[-1].timestamp + 1000000
            blk.reward_addr = ADDR
            blk.target = 1
            blk.coinbase_reward = bc.coinbase_reward
            blk.transactions = {}
            blk.balances = {}
            blk.next_nonce = {}
            blk.proof = 0
            blk.merkle_root = MerkleTree.EMPTY_HASH
            miner.blocks[blk.id] = blk
            chain.append(blk)

        result = bc_module.Blockchain.calculate_target(chain[-1])
        assert result <= POW_BASE_TARGET

class TestFixedBlockSize:
    def setup_method(self):
        self.prev_block = Block("8e7912")
        self.prev_block.balances = {ADDR: 500000000}
        outputs = [{'amount': 1, 'address': 'ffff'}]
        self.base_tx_cfg = {'from': ADDR, 'pubKey': KP['public'], 'outputs': outputs, 'fee': 1}

    def _make_tx(self, nonce, fee=None):
        cfg = {**self.base_tx_cfg, 'nonce': nonce}
        if fee is not None:
            cfg['fee'] = fee
        tx = Transaction(cfg)
        tx.sign(KP['private'])
        return tx

    def test_byte_size_is_positive(self):
        tx = self._make_tx(0)
        assert tx.byte_size() > 0

    def test_byte_size_is_integer(self):
        tx = self._make_tx(0)
        assert isinstance(tx.byte_size(), int)

    def test_larget_output_list_has_bigger_byte_size(self):
        small_tx = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': [{'amount': 1, 'address': 'ffff'}], 'fee': 1, 'nonce': 0})
        small_tx.sign(KP['private'])

        big_tx = Transaction({'from': ADDR, 'pubKey': KP['public'], 'outputs': [{'amount': 1, 'address': 'ffff'}, {'amount': 1, 'address': 'face'}, {'amount': 1, 'address': 'dead'}], 'fee': 1, 'nonce': 0})
        big_tx.sign(KP['private'])

        assert big_tx.byte_size() > small_tx.byte_size()

    def test_max_block_size_constant_defined(self):
        assert bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES == 1000000

    def test_total_tx_bytes_fit_within_max_block_size(self):
        b = Block(ADDR, self.prev_block)
        for i in range(5):
            tx = self._make_tx(i)
            b.add_transaction(tx)

        total = sum(tx.byte_size() for tx in b.transactions.values())
        assert total < bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES

    def test_miner_includes_high_fee_tx_and_drops_low_fee_when_block_is_full(self):
        """When the block size cap allows only one tx, the miner picks the highest fee/byte one."""
        miner = Miner({'name': 'FeeOrderMiner', 'net': None, 'startingBlock': self.prev_block})
        miner.log = lambda _: None
        bc_module.Blockchain.get_instance().miners.append(miner)

        # nonce=0 high-fee, nonce=1 low-fee — fee desc order matches nonce order
        # so the high-fee tx is a valid first add (nonce=0 == next_nonce)
        tx_high = self._make_tx(0, fee=1000)
        tx_low  = self._make_tx(1, fee=1)

        # Allow exactly one transaction by capping at tx_high's byte size.
        # tx_low would push the block over the limit.
        original_max = bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES
        bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES = tx_high.byte_size()
        try:
            miner.transactions = {tx_high.id: tx_high, tx_low.id: tx_low}
            miner.start_new_search()
            block_txs = miner.current_block.transactions
            assert tx_high.id in block_txs, "High fee/byte tx must be selected"
            assert tx_low.id not in block_txs, "Low fee/byte tx must be dropped when block is full"
        finally:
            bc_module.Blockchain.MAX_BLOCK_SIZE_BYTES = original_max

    def test_miner_all_txs_included_when_within_size_limit(self):
        """All transactions are included when their combined size fits in the block."""
        miner = Miner({'name': 'AllTxMiner', 'net': None, 'startingBlock': self.prev_block})
        miner.log = lambda _: None
        bc_module.Blockchain.get_instance().miners.append(miner)

        tx_a = self._make_tx(0, fee=10)
        tx_b = self._make_tx(1, fee=5)
        tx_c = self._make_tx(2, fee=1)
        miner.transactions = {tx_a.id: tx_a, tx_b.id: tx_b, tx_c.id: tx_c}
        miner.start_new_search()

        block_txs = miner.current_block.transactions
        assert tx_a.id in block_txs
        assert tx_b.id in block_txs
        assert tx_c.id in block_txs

if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '--v']))