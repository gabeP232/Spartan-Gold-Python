import threading

import blockchain as bc_module
from client import Client

class Miner(Client):
    def __init__(self, obj = None):
        if obj is None:
            obj = {}
        super().__init__(obj)

        mining_rounds = obj.get('miningRounds') if obj.get('miningRounds') is not None \
            else bc_module.Blockchain.NUM_ROUNDS_MINING
        self.mining_rounds = mining_rounds

        self.transactions = set()

        self.current_block = None
        self._lock = threading.RLock()

    # Starts listeners and begin mining.
    def initialize(self):
        self.start_new_search()
        self.on(bc_module.Blockchain.START_MINING, self.find_proof)
        self.on(bc_module.Blockchain.POST_TRANSACTION, self.add_transaction)
        threading.Timer(0, lambda: self.emit(bc_module.Blockchain.START_MINING)).start()

    # Sets up the miner to start searching for a new block.
    def start_new_search(self, tx_set = None):
        if tx_set is None:
            tx_set = set()
        with self._lock:
            self.current_block = bc_module.Blockchain.make_block(self.address, self.last_block)

            for tx in tx_set:
                self.transactions.add(tx)

            for tx in self.transactions:
                self.current_block.add_transaction(tx, self)
            self.transactions.clear()

            self.current_block.proof = 0

    # Looks for a "proof". It breaks after some time to listen for messages.

    # The 'one_and_done' field is used for testing only; it prevents the findProof method
    # from looking for the proof again after the first attempt.
    def find_proof(self, one_and_done = False):
        cb = self.current_block
        pause_point = cb.proof + self.mining_rounds
        while cb is self.current_block and cb.proof < pause_point:
            with self._lock:
                if cb is not self.current_block:
                    break
                if cb.has_valid_proof():
                    self.log(
                        f"Found proof for block {cb.chain_length}: "
                        f"{cb.proof}"
                    )
                    self.announce_proof()
                    self.receive_block(cb)
                    return
            cb.proof += 1

        if not one_and_done:
            threading.Timer(0, lambda: self.emit(bc_module.Blockchain.START_MINING)).start()

    # Broadcast the block, with a valid proof included.
    def announce_proof(self):
        self.net.broadcast(bc_module.Blockchain.PROOF_FOUND, self.current_block)

    # Receives a block from another miner. If it is valid,
    # the block will be stored. If it is also a longer chain,
    # the miner will accept it and replace the currentBlock.
    def receive_block(self, s):
        b = super().receive_block(s)
        if b is None:
            return None

        with self._lock:
            if self.current_block and b.chain_length >= self.current_block.chain_length:
                self.log('Cutting over to new chain.')
                tx_set = self.sync_transactions(b)
                self.start_new_search(tx_set)

        return b

    # This function should determine what transactions
    # need to be added or deleted. It should find a common ancestor (retrieving
    # any transactions from the roll-back blocks), remove any transactions
    # already included in the newly accepted blocks, and add any remaining
    # transactions to the new block.
    def sync_transactions(self, nb):
        cb = self.current_block
        cb_txs = set()
        nb_txs = set()

        while nb.chain_length > cb.chain_length:
            for tx in nb.transactions.values():
                nb_txs.add(tx)
            nb = self.blocks.get(nb.prev_block_hash)

        while cb and cb.id != nb.id:
            for tx in cb.transactions.values():
                cb_txs.add(tx)
            for tx in nb.transactions.values():
                nb_txs.add(tx)
            cb = self.blocks.get(cb.prev_block_hash)
            nb = self.blocks.get(nb.prev_block_hash)

        cb_txs -= nb_txs
        return cb_txs

    # Returns false if transaction is not accepted. Otherwise, stores
    # the transaction to be added to the next block
    def add_transaction(self, tx):
        tx = bc_module.Blockchain.make_transaction(tx)
        self.transactions.add(tx)

    # When a miner posts a transaction, it must also add it to its current list of transactions.
    def post_transaction(self, *args, **kwargs):
        tx = super().post_transaction(*args, **kwargs)
        self.add_transaction(tx)
        return tx