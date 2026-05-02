import json
import time
import utils

from merkleTree import MerkleTree
import blockchain as bc_module
class Block:
    def __init__(self, reward_addr = None, prev_block = None, target = None, coinbase_reward = None):
        if target is None or coinbase_reward is None:
            try:
                if target is None:
                    # Inherit the parent block's target so each block carries its own
                    # difficulty in the header (mirrors Bitcoin's design). Using the
                    # mutable bc.pow_target would cause racing miners to clobber each
                    # other's adjustment when two blocks at the same height are created.
                    if prev_block is not None:
                        target = prev_block.target
                    else:
                        target = bc_module.Blockchain.POW_TARGET
                if coinbase_reward is None:
                    coinbase_reward = bc_module.Blockchain.COINBASE_AMT_ALLOWED
            except Exception:
                if target is None:
                    target = int("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16)
                if coinbase_reward is None:
                    coinbase_reward = 25

        self.prev_block_hash = prev_block.id if prev_block else None
        self.target = target
        self.coinbase_reward = coinbase_reward
        self.reward_addr = reward_addr

        self.balances = dict(prev_block.balances) if prev_block else {}
        self.next_nonce = dict(prev_block.next_nonce) if prev_block else {}

        if prev_block and prev_block.reward_addr:
            winner_balance = self.balance_of(prev_block.reward_addr)
            self.balances[prev_block.reward_addr] = winner_balance + prev_block.total_rewards()


        ### Adjusted to build a Merkle Tree from the Transactions ###
        #
        # Only stores the root hash in the serialized header
        self.transactions = {}
        # Empty hash until a transaction is added to the block
        self.merkle_root = MerkleTree([]).get_root()
        
        self.chain_length = (prev_block.chain_length + 1) if prev_block else 0
        self.timestamp = int(time.time() * 1000)

        self.proof = None
        
        ### Add check for Dynamic Difficulty for POW ###
        #
        # After all fields are set, check if the block can be adjusted and recalculate the
        # PoW based on how fast the last N blocks were mined
        # Conditions are:
        # Cant be the genesis block, blockchain instance exists, and the chain_length % interval == 0
        # Which means it only adjusts every N blocks.
        #
        if (prev_block is not None and bc_module.Blockchain.has_instance() and self.chain_length % bc_module.DIFFICULTY_ADJUSTMENT_INTERVAL == 0):
            self.target = bc_module.Blockchain.calculate_target(prev_block)

    def is_genesis_block(self):
        return self.chain_length == 0

    def has_valid_proof(self):
        h = utils.hash(self.serialize())
        n = int(h, 16)
        return n < self.target

    def hash_val(self):
        return utils.hash(self.serialize())

    @property
    def id(self):
        return self.hash_val()

    def balance_of(self, addr):
        return self.balances.get(addr, 0)

    def total_rewards(self):
        return sum (tx.fee for tx in self.transactions.values()) + self.coinbase_reward

    # Instead of checking if the transaction exists within the block
    # Now we check through the MerkleTree 
    def contains(self, tx):
        return MerkleTree(list(self.transactions.keys())).includes_transaction(tx.id)

    # function to rebuild the merkle tree from the curr transaction set
    # then update self.merkle_root
    def _rebuild_merkle(self):
        # Runs after every 'add_transaction()' and at the end of 'rerun()'
        tree = MerkleTree(list(self.transactions.keys()))
        self.merkle_root = tree.get_root()
    
    # Adjusted so that merkle root is stored as well
    # Also the PoW target for dynamic difficulty
    def to_json(self):
        o = {
            'chainLength': self.chain_length,
            'timestamp': self.timestamp,
        }
        if self.is_genesis_block():
            o['balances'] = list(self.balances.items())
        else:  
            o['merkleRoot'] = self.merkle_root
            o['transactions'] = [[tx_id, tx.to_dict()] for tx_id, tx in self.transactions.items()]
            o['prevBlockHash'] = self.prev_block_hash
            o['proof'] = self.proof
            o['rewardAddr'] = self.reward_addr
            o['target'] = hex(self.target)
        return o

    # Create the string that gets hashed for PoW
    #
    # Unlike in the JS version, the transactions are excluded and the MerkleRoot
    # is included. Miners now hash the header instead of the full tx list
    #
    def serialize(self):
        # Create a header
        h = {
            'chainLength': self.chain_length,
            'timestamp': self.timestamp,
        }
        # Check if block is the genesis blockm if it is store the balances here
        if self.is_genesis_block():
            h['balances'] = list(self.balances.items()) 
        else:
            h['merkleRoot'] = self.merkle_root
            h['prevBlockHash'] = self.prev_block_hash
            h['proof'] = self.proof
            h['rewardAddr'] = self.reward_addr
            h['target'] = hex(self.target)
        
        return json.dumps(h, separators = (',', ':'))

    # As mentioned before, after every transaction is added
    # rebuild the merkle tree
    def add_transaction(self, tx, client = None):
        if tx.id in self.transactions:
            if client:
                client.log(f"Duplicate transaction {tx.id}.")
            return False
        if tx.sig is None:
            if client:
                client.log(f"Unsigned transaction {tx.id}.")
            return False
        if not tx.valid_signature():
            if client:
                client.log(f"Invalid signature for transaction {tx.id}.")
            return False
        if not tx.sufficient_funds(self):
            if client:
                client.log(f"Insufficient gold for transaction {tx.id}.")
            return False

        nonce = self.next_nonce.get(tx.from_addr, 0)
        if tx.nonce < nonce:
            if client:
                client.log(f"Replayed transaction {tx.id}.")
            return False
        elif tx.nonce > nonce:
            if client:
                client.log(f"Out of order transaction {tx.id}.")
            return False
        else:
            self.next_nonce[tx.from_addr] = nonce + 1

        self.transactions[tx.id] = tx

        sender_balance = self.balance_of(tx.from_addr)
        self.balances[tx.from_addr] = sender_balance - tx.total_output()

        for output in tx.outputs:
            old_balance = self.balance_of(output['address'])
            self.balances[output['address']] = old_balance + output['amount']

        # Rebuild merkle tree
        self._rebuild_merkle()
        return True

    # Replay the tx against the new parent block
    def rerun(self, prev_block):
        self.balances = dict(prev_block.balances)
        self.next_nonce = dict(prev_block.next_nonce)

        if prev_block.reward_addr:
            winner_balance = self.balance_of(prev_block.reward_addr)
            self.balances[prev_block.reward_addr] = winner_balance + prev_block.total_rewards()

        txs = self.transactions
        self.transactions = {}
        for tx in txs.values():
            if not self.add_transaction(tx):
                return False

        # Rebuild merkle root after finished
        self._rebuild_merkle()
        
        return True