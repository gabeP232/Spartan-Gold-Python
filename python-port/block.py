import json
import time
import utils

class Block:
    def __init__(self, reward_addr = None, prev_block = None, target = None, coinbase_reward = None):
        if target is None or coinbase_reward is None:
            try:
                import blockchain as bc_module
                if target is None:
                    target = bc_module.Blockchain.POW_TARGET
                if coinbase_reward is None:
                    coinbase_reward = bc_module.Blockchain.COINBASE_AMT_ALLOWED
            except Exception:
                if target is None:
                    target = int("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16)
                if coinbase_reward is None:
                    coinbase_reward = 25

        self.prev_block_hash = prev_block.hash.val() if prev_block else None
        self.target = target
        self.coinbase_reward = coinbase_reward
        self.reward_addr = reward_addr

        self.balances = dict(prev_block.balances) if prev_block else {}
        self.next_nonce = dict(prev_block.next_nonce) if prev_block else {}

        if prev_block and prev_block.reward_addr:
            winner_balance = self.balance_of(prev_block.reward_addr)
            self.balances[prev_block.reward_addr] = winner_balance + prev_block.total_rewards()

        self.transactions = {}

        self.chain_length = (prev_block.chain_length + 1) if prev_block else 0
        self.timestamp = int(time.time() * 1000)

        self.proof = None

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

    def contains(self, tx):
        return tx.id in self.transactions

    def to_json(self):
        o = {
            'chainLength': self.chain_length,
            'timestamp': self.timestamp,
        }
        if self.is_genesis_block():
            o['balances'] = list(self.balances.items())
        else:
            o['transactions'] = [[tx_id, tx.to_dict()] for tx_id, tx, in self.transactions.items()]
            o['prevBlockHash'] = self.prev_block_hash
            o['proof'] = self.proof
            o['rewardAddr'] = self.reward_addr
        return o

    def serialize(self):
        return json.dumps(self.to_json(), separators = (',', ':'))

    def add_transactions(self, tx, client = None):
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

        return True

    def rerun(self, prev_block):
        self.balances = dict(prev_block.balances)
        self.next_nonce = dict(prev_block.next_nonce)

        if prev_block.reward_addr:
            winner_balance = self.balance_of(prev_block.reward_addr)
            self.balances[prev_block.reward_addr] = winner_balance + prev_block.total_rewards()

        txs = self.transactions
        self.transactions = {}
        for tx in txs.values():
            if not self.add_transactions(tx):
                return False

        return True