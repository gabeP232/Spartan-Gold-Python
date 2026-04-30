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

# A client has a public/private keypair and an address.
# It can send and receive messages on the Blockchain network.
class Client(EventEmitter):
    def __init__(self, obj = None):
        super().__init__()

        if obj is None:
            obj = {} # The properties of the client.

        self.net = obj.get('net') # The network used by the client to send messages to all miners and clients.
        self.name = obj.get('name') # The client's name, used for debugging messages.
        self.password = obj.get('password') or (self.name + '_pswd' if self.name else '_pswd') # The client's password,
        # used for generating address.

        self.key_pair = None # The public private keypair for the client.
        self.address = None

        if bc_module.Blockchain.has_instance():
            bc = bc_module.Blockchain.get_instance()
            self.generate_address(bc.mnemonic)

        # Establishes order of transactions. Incremented with each
        # new output transaction from this client. This feature
        # avoids replay attacks.
        self.nonce = 0

        # A dictionary of transactions where the client has spent money,
        # but where the transaction has not yet been confirmed.
        self.pending_outgoing_transactions = {}

        # A dictionary of transactions received but not yet confirmed.
        self.pending_received_transactions = {}

        # A dictionary of all block hashes to the accepted blocks.
        self.blocks = {}

        # A dictionary of missing block IDS to the list of blocks depending
        # on the missing blocks
        self.pending_blocks = {}

        starting_block = obj.get('startingBlock')
        if starting_block:
            self.set_genesis_block(starting_block)

        # Setting up listeners to receive messages from other clients.
        self.on(bc_module.Blockchain.PROOF_FOUND, self.receive_block)
        self.on(bc_module.Blockchain.MISSING_BLOCK, self.provide_missing_block)

    # The genesis block can only be set if the client does not already
    # have the genesis block.
    def set_genesis_block(self, starting_block):
        if hasattr(self, 'last_block') and self.last_block:
            raise RuntimeError("Cannot set genesis block for existing blockchain.")

        # Transactions from this block or older are assumed to be confirmed,
        # and therefore are spendable by the client. The transactions could
        # roll back, but it is unlikely.
        self.last_confirmed_block = starting_block

        # The last block seen. Any transactions after lastConfirmedBlock
        # up to lastBlock are considered pending.
        self.last_block = starting_block
        self.blocks[starting_block.id] = starting_block

    # Generate client address using mnemonic set for the blockchain
    def generate_address(self, mnemonic):
        if mnemonic is None:
            raise RuntimeError("mnemonic not set")
        self.key_pair = utils.generate_keypair_from_mnemonic(mnemonic, self.password)
        self.address = utils.calc_address(self.key_pair['public'])
        print(f"{self.name}'s address is: {self.address}")

    # The amount of gold available to the client, not counting any pending
    # transactions. This getter looks at the last confirmed block, since
    # transactions in new blocks may roll back.
    @property
    def confirmed_balance(self):
        return self.last_confirmed_block.balance_of(self.address)

    # Any gold received in the last confirmed block or before is considered
    # spendable, but any gold received more recently is not yet available.
    # However, any gold given by the client to other clients in unconfirmed
    # transactions is treated as unavailable.
    @property
    def available_gold(self):
        pending_spent = sum(tx.total_output() for tx in self.pending_outgoing_transactions.values())
        return self.confirmed_balance - pending_spent

    # Broadcasts a transaction from the client giving gold to the clients
    # specified in 'outputs'. A transaction fee may be specified, which can
    # be more or less than the default value.
    def post_transaction(self, outputs, fee = None):
        if fee is None:
            fee = bc_module.Blockchain.DEFAULT_TX_FEE

        total_payments = sum(o['amount'] for o in outputs) + fee
        if total_payments > self.available_gold:
            raise RuntimeError(
                f"Requested {total_payments}, but account only has {self.available_gold}."
            )
        return self.post_generic_transaction({'outputs': outputs, 'fee': fee})

    # Broadcasts a transaction from the client. No validation is performed,
    # so the transaction might be rejected by other miners.

    # This method is useful for handling special transaction with unique
    # parameters required, but generally should not be called directly by clients.
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

    # Validates and adds a block to the list of blocks, possibly updating the head
    # of the blockchain. Any transactions in the block are rerun in order to
    # update the gold balances for all clients. If any transactions are found to be
    # invalid due to lack of funds, the block is rejected and 'null' is returned to
    # indicate failure.

    # If any blocks cannot be connected to an existing block but seem otherwise valid,
    # they are added to a list of pending blocks and a request is sent out to get the
    # missing blocks from other clients.
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

    # Request the previous block from the network.
    def request_missing_block(self, block):
        self.log(f"Asking for missing block: {block.prev_block_hash}")
        msg = {'from': self.address, 'missing': block.prev_block_hash}
        self.net.broadcast(bc_module.Blockchain.MISSING_BLOCK, msg)

    # Resend any transactions in the pending list.
    def resend_pending_transactions(self):
        for tx in self.pending_outgoing_transactions.values():
            self.net.broadcast(bc_module.Blockchain.POST_TRANSACTION, tx)

    # Takes an object representing a requesst for a missing block.
    # If the client has the block, it will send the block to the
    # client that requested it.
    def provide_missing_block(self, msg):
        if msg['missing'] in self.blocks:
            self.log(f"Providing missing block {msg['missing']}")
            block = self.blocks[msg['missing']]
            self.net.send_message(msg['from'], bc_module.Blockchain.PROOF_FOUND, block)

    # Sets the last confirmed block according to the most recently accepted block,
    # also updating pending transactions according to this block.
    # Note that the genesis block is always considered to be confirmed.
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

    # Utility method that displays all confirmed balances for all clients,
    # according to the client's own perspective of the network.
    def show_all_balances(self):
        bc = bc_module.Blockchain.get_instance()
        self.log("Showing balances:")
        for addr, balance in self.last_confirmed_block.balances.items():
            name = bc.get_client_name(addr)
            if name:
                print(f" {addr} ({name}): {balance}")
            else:
                print(f" {addr}: {balance}")

    # Print out the blocks in the blockchain from the current head
    # to the genesis block. Only the Block IDs are printed.
    def show_blockchain(self):
        block = self.last_block
        print("BLOCKCHAIN:")
        while block is not None:
            print(block.id)
            block = self.blocks.get(block.prev_block_hash)

    # Log messages, including the name to make debugging easier.
    # If the client does not have a name, then one is calculated from the
    # client's address.
    def log(self, msg):
        name = self.name or self.address[:10]
        print(f"{name}: {msg}")