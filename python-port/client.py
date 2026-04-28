import utils
import blockchain as bc_module

class EventEmitter:
    def __init__(self):
        self._listeners = {}

    def on(self, event, handler):
        self._listeners.setdefault(event, []).append(handler)

    def off(self, event, handler = None):
        if handler is None:
            self._listeners.pop(event, None)
        elif event in self._listeners:
            self._listeners[event] = [h for h in self._listeners[event] if h != handler]

    def emit(self, event, *args):
        for handler in list(self._listeners.get(event, [])):
            handler(*args)

class Client(EventEmitter):
    def __init__(self, obj = None):
        super().__init__()

        if obj is None:
            obj = {}

        self.net = obj.get('net')
        self.name = obj.get('name')
        self.password = obj.get('password') or (self.name + '_pswd' if self.name else '_pswd')

        self.key_pair = None
        self.address = None

        if bc_module.Blockchain.has_instance():
            bc = bc_module.Blockchain.get_instance()
            self.generate_address(bc.mnemonic)

        self.nonce = 0

        self.pending_outgoing_transactions = {}
        self.pending_received_transactions = {}

        self.blocks = {}

        self.pending_blocks = {}

        starting_block = obj.get('startingBlock')
        if starting_block:
            self.set_genesis_block(starting_block)

        self.on(bc_module.Blockchain.PROOF_FOUND, self.receive_block)
        self.on(bc_module.Blockchain.MISSING_BLOCK, self.provide_missing_block)

    def set_genesis_block(self, starting_block):
        if hasattr(self, 'last_block') and self.last_block:
            raise RuntimeError("Cannot set genesis block for existing blockchain.")
        self.last_confirmed_block = starting_block
        self.last_block = starting_block
        self.blocks[starting_block.id] = starting_block

    def generate_address(self, mnemonic):
        if mnemonic is None:
            raise RuntimeError("mnemonic not set")
        self.key_pair = utils.generate_keypair_from_mnemonic(mnemonic, self.password)
        self.address = utils.calc_address(self.key_pair['public'])
        print(f"{self.name}'s address is: {self.address}")

    @property
    def confirmed_balance(self):
        return self.last_confirmed_block.balance_of(self.address)

    @property
    def available_gold(self):
        pending_spent = sum(tx.total_output() for tx in self.pending_outgoing_transactions.values())
        return self.confirmed_balance - pending_spent

    def post_transaction(self, outputs, fee = None):
        if fee is None:
            fee = bc_module.Blockchain.DEFAULT_TX_FEE

        total_payments = sum(o['amount'] for o in outputs) + fee
        if total_payments > self.available_gold:
            raise RuntimeError(
                f"Requested {total_payments}, but account only has {self.available_gold}."
            )
        return self.post_generic_transaction({'outputs': outputs, 'fee': fee})

    def post_generic_transaction(self, tx_data):
        data = {
            'from': self.address,
            'nonce': self.nonce,
            'pubKey': self.key_pair['public'],
        }
        data.update(tx_data)

        tx = bc_module.Blockchain.make_transaction(data)
        tx.sign(self.key_pair['private'])

        self.pending_outgoing_transactions[tx.id] = tx
        self.nonce += 1
        self.net.broadcast(bc_module.Blockchain.POST_TRANSACTION, tx)
        return tx

    def receive_block(self, block):
        block = bc_module.Blockchain.deserialize_block(block)

        if block.id in self.blocks:
            return None

        if not block.has_valid_proof() and not block.is_genesis_block():
            self.log(f"Block {block.id} does not have a valid proof.")
            return None

        prev_block = self.blocks.get(block.prev_block_hash)
        if prev_block is None and not block.is_genesis_block():
            stuck = self.pending_blocks.get(block.prev_block_hash)
            if stuck is None:
                self.request_missing_block(block)
                stuck = set()
            stuck.add(block)
            self.pending_blocks[block.prev_block_hash] = stuck
            return None

        if not block.is_genesis_block():
            if not block.rerun(prev_block):
                return None

        self.blocks[block.id] = block

        if self.last_block.chain_length < block.chain_length:
            self.last_block = block
            self.set_last_confirmed()

        unstuck = self.pending_blocks.pop(block.id, set())
        for b in unstuck:
            self.log(f"Processing unstuck block {b.id}")
            self.receive_block(b)
        return block

    def request_missing_block(self, block):
        self.log(f"Asking for missing block: {block.prev_block_hash}")
        msg = {'from': self.address, 'missing': block.prev_block_hash}
        self.net.broadcast(bc_module.Blockchain.MISSING_BLOCK, msg)

    def resend_pending_transactions(self):
        for tx in self.pending_outgoing_transactions.values():
            self.net.broadcast(bc_module.Blockchain.POST_TRANSACTION, tx)

    def provide_missing_block(self, msg):
        if msg['missing'] in self.blocks:
            self.log(f"Providing missing block {msg['missing']}")
            block = self.blocks[msg['missing']]
            self.net.send_message(msg['from'], bc_module.Blockchain.PROOF_FOUND, block)

    def set_last_confirmed(self):
        block = self.last_block
        confirmed_height = block.chain_length - bc_module.Blockchain.CONFIRMED_DEPTH
        if confirmed_height < 0:
            confirmed_height = 0
        while block.chain_length > confirmed_height:
            block = self.blocks.get(block.prev_block_hash)
        self.last_confirmed_block = block

        for tx_id, tx in list(self.pending_outgoing_transactions.items()):
            if self.last_confirmed_block.contains(tx):
                del self.pending_outgoing_transactions[tx_id]

    def show_all_balances(self):
        bc = bc_module.Blockchain.get_instance()
        self.log("Showing balances:")
        for addr, balance in self.last_confirmed_block.balances.items():
            name = bc.get_client_name(addr)
            if name:
                print(f" {addr} ({name}): {balance}")
            else:
                print(f" {addr}: {balance}")

    def show_blockchain(self):
        block = self.last_block
        print("BLOCKCHAIN:")
        while block is not None:
            print(block.id)
            block = self.blocks.get(block.prev_block_hash)

    def log(self, msg):
        name = self.name or self.address[:10]
        print(f"{name}: {msg}")