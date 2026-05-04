
# Network msg constants
MISSING_BLOCK = "MISSING_BLOCK"
POST_TRANSACTION = "POST_TRANSACTION"
PROOF_FOUND = "PROOF_FOUND"
START_MINING = "START_MINING"

# num of hash attempts a miner can make per turn
NUM_ROUNDS_MINING = 2000

# pow target
POW_BASE_TARGET = int("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16)
POW_LEADING_ZEROES = 15

# mining rewards and tx fee
COINBASE_AMT_ALLOWED = 25
DEFAULT_TX_FEE = 1

# If block is 6 blocks older than curr block, confirm it. 
# Genesis block always confirmed
CONFIRMED_DEPTH = 6


###### Dynamic Difficulty Adjustment constants ####### additional feature num 1.
#
# every 10 blocks solved increase difficulty
DIFFICULTY_ADJUSTMENT_INTERVAL = 10 
# Time in ms per block (10sec)
TARGET_BLOCK_TIME = 10000

###### Fixed Block Size constant #####
#
# 1 mb like Bitcoins
MAX_BLOCK_SIZE_BYTES = 1000000


# Instead of static getter methods like JS does, Python uses @property to work on instances
# this gives class-level access without calling a method.
class BlockchainMeta(type):
    @property
    def POW_TARGET(cls):
        return cls.get_instance().pow_target

    @property
    def COINBASE_AMT_ALLOWED(cls):
        return cls.get_instance().coinbase_reward

    @property
    def DEFAULT_TX_FEE(cls):
        return cls.get_instance().default_tx_fee

    @property
    def CONFIRMED_DEPTH(cls):
        return cls.get_instance().confirmed_depth

# We use a 'metaclass' here which allows us to define the properties on the class itself
# Unlike in JS where it stores the instances on the class itself
# Python uses a private class variable to enforce the global blockchain config object
class Blockchain(metaclass = BlockchainMeta):
    # plain class attributes are fine here because these are constants
    _instance = None

    MISSING_BLOCK = MISSING_BLOCK
    POST_TRANSACTION = POST_TRANSACTION
    PROOF_FOUND = PROOF_FOUND
    START_MINING = START_MINING
    NUM_ROUNDS_MINING = NUM_ROUNDS_MINING
    # Add max block size constant
    MAX_BLOCK_SIZE_BYTES = MAX_BLOCK_SIZE_BYTES

    # Singleton accessors, implemented the same pretty much as in JS.
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("The blockchain has not been initialized.")
        return cls._instance

    @classmethod
    def has_instance(cls):
        return cls._instance is not None

    @classmethod
    def reset_instance(cls):
        cls._instance = None


    # Production methods
    @classmethod
    def create_instance(cls, cfg):
        cls._instance = Blockchain(cfg)
        cls._instance.genesis = cls.make_genesis()
        return cls._instance

    # create genesis block
    # python 'dict' is slightly faster to iterate than JS 'map' for a small amt of clients
    @classmethod
    def make_genesis(cls):
        bc = cls.get_instance()
        g = cls.make_block()
        g.balances = dict(bc.initial_balances)
        for client in bc.clients:
            client.set_genesis_block(g)
        return g

    # args unpacking here is equivalent to js (...args)
    @classmethod
    def make_block(cls, *args):
        return cls.get_instance()._make_block(*args)

    @classmethod
    def make_transaction(cls, o):
        return cls.get_instance()._make_transaction(o)


    # Deserialize block
    #
    # In JS it uses 'new this.instance.BlockClass()' which gets the constrcutor normally
    # without any args
    # In Python constructors can't be called as easily so we use '__new__' to allocate
    # the objm then set the attributes by hand, this bypasses '__init__'
    #
    @classmethod
    def deserialize_block(cls, o):
        bc = cls.get_instance()
        # if already of right type, return
        if isinstance(o, bc.block_class):
            return o

        # allocate with an empty constrcutor class
        b = bc.block_class.__new__(bc.block_class)
        b.balances = {}
        b.next_nonce = {}
        b.transactions = {}
        b.proof = None
        b.prev_block_hash = None
        b.reward_addr = None
        b.target = bc.pow_target
        b.coinbase_reward = bc.coinbase_reward

        # key matches block.to_json() 
        b.chain_length = int(o['chainLength'])
        b.timestamp = o['timestamp']

        # Python equivalent to o.balances.forEach(([clientID,amount]) => {b.balances.set(clientID, amount);
        if b.is_genesis_block():
            for client_id, amount in o['balances']:
                b.balances[client_id] = amount
            # Genesis blocks have no transactions so the Merkle root is always empty.
            from merkleTree import MerkleTree
            b.merkle_root = MerkleTree.EMPTY_HASH
        else:
            b.prev_block_hash = o['prevBlockHash']
            b.proof = o['proof']
            b.reward_addr = o['rewardAddr']
            b.transactions = {}
            
            #### Deserialization for Merkle Root #######
            # Since header only contains the merkle Root
            # the full tx is transmitted with to_json() to verify and rerun bals
            #
            # After deserializing, verify the received txs produce the actual merkle root
            # If it doesn't then a tx was tampered with.
            from merkleTree import MerkleTree

            # Restore the serialized target so that dynamic difficulty is preserved.
            b.target = int(o['target'], 16)
            
            # assign to actual merkle root
            b.merkle_root = o.get('merkleRoot', MerkleTree([]).get_root())
            
            # Continue with usual deserialization, receive the txs
            for tx_id, tx_json in (o.get('transactions') or []):
                tx = cls.make_transaction(tx_json)
                b.transactions[tx_id] = tx
            
            # Verify if the received transactions match the merkle root structure
            buildRoot = MerkleTree(list(b.transactions.keys())).get_root()
            if buildRoot != b.merkle_root:
                raise ValueError(
                    f"Merkle root mismatch at block {b.chain_length},"
                    f"Got {buildRoot}, expected {b.merkle_root}"
                )

        return b

    # constructor
    # Unlike JS, Pythong uses a cfg dict because it doesn't support destructured parameters.
    def __init__(self, cfg):
        import block as block_module
        import transaction as tx_module
        import client as client_module
        import miner as miner_module
        
        # this allows us to inject custom subclasses
        # this is useful for implementing the fixed blocksize and 
        self.block_class = cfg.get('blockClass') or block_module.Block
        self.transaction_class = cfg.get('transactionClass') or tx_module.Transaction
        self.client_class = cfg.get('clientClass') or client_module.Client
        self.miner_class = cfg.get('minerClass') or miner_module.Miner

        self.clients = []
        self.miners = []
        
        self.client_address_map = {}
        self.client_name_map = {}
        self.net = cfg.get('net')

        pow_leading_zeroes = cfg.get('powLeadingZeroes', POW_LEADING_ZEROES)
        self.coinbase_reward = cfg.get('coinbaseAmount', COINBASE_AMT_ALLOWED)
        self.default_tx_fee = cfg.get('defaultTxFee', DEFAULT_TX_FEE)
        self.confirmed_depth = cfg.get('confirmedDepth', CONFIRMED_DEPTH)
        
        # In python '>>' int right shift is equivalent without BigInt
        self.pow_target = POW_BASE_TARGET >> pow_leading_zeroes

        self.initial_balances = dict(cfg.get('startingBalances', {}))

        # use mnemoic library to get bip-39
        mnemonic = cfg.get('mnemonic')
        if mnemonic is None:
            from mnemonic import Mnemonic
            mnemo = Mnemonic("english")
            self.mnemonic = mnemo.generate(strength = 256)
        else:
            self.mnemonic = mnemonic

        # Register each client in the config, using a for loop instead of for each like in JS
        for client_cfg in cfg.get('clients', []):
            print(f"Adding client {client_cfg['name']}")
            
            password = client_cfg.get('password', client_cfg['name'] + '_pswd')
            if client_cfg.get('mining'):
                c = self.miner_class({
                    'name': client_cfg['name'],
                    'password': password,
                    'net': self.net,
                    'miningRounds': client_cfg.get('miningRounds'),
                })
                c.generate_address(self.mnemonic)
                self.miners.append(c)
            else:
                c = self.client_class({
                    'name': client_cfg['name'],
                    'password': password,
                    'net': self.net,
                })
                c.generate_address(self.mnemonic)

            self.client_address_map[c.address] = c
            if c.name:
                self.client_name_map[c.name] = c
            self.clients.append(c)
            self.net.register(c)
            self.initial_balances[c.address] = client_cfg['amount']
    
    
    ### Implementing Dynamic Difficulty for POW Target ###
    @classmethod
    def calculate_target(cls, prev_block):
        bc = cls.get_instance()
        interval = DIFFICULTY_ADJUSTMENT_INTERVAL

        # IF not enough history, keep the parent block's target
        if prev_block.chain_length < interval:
            return prev_block.target

        window_start = prev_block

        # Get the block that is exactly 'interval' steps behind the prev_block
        for _ in range(interval - 1):
            parent_hash = window_start.prev_block_hash
            if parent_hash is None:
                return prev_block.target

            # look up blocks from the first miner
            if bc.miners:
                window_start = bc.miners[0].blocks.get(parent_hash)
            else:
                window_start = None

            if window_start is None:
                return prev_block.target

        actual_time_ms = prev_block.timestamp - window_start.timestamp
        expected_time_ms = interval * TARGET_BLOCK_TIME

        # To avoid division by 0 if the timestamps might be identical
        if actual_time_ms <= 0:
            actual_time_ms = 1

        # Derive from the parent block's embedded target (immutable chain state),
        # not the mutable bc.pow_target. Two miners racing to produce the same
        # adjustment block will both read the same prev_block.target and compute
        # the same new_target without interfering with each other.
        old_target = prev_block.target

        # if actual time is bigger, the target increases, and mining is easier
        # if the expected time was exceeded then relax the difficulty
        new_target = old_target * actual_time_ms // expected_time_ms

        # Bitcoin clamps it so it doesnt increase by more than 4 in either direction at a time
        new_target = max(new_target, old_target // 4)
        new_target = min(new_target, old_target * 4)

        new_target = min(new_target, POW_BASE_TARGET)

        return new_target


    
    def _make_block(self, *args):
        return self.block_class(*args)

    def _make_transaction(self, o):
        if isinstance(o, self.transaction_class):
            return o
        return self.transaction_class(o)

    def show_balances(self, name = None):
        client = self.client_name_map.get(name) if name else (self.clients[0] if self.clients else None)
        if not client:
            raise RuntimeError("No client found.")
        client.show_all_balances()

    def start(self, ms = None, callback = None):
        import threading
        for miner in self.miners:
            miner.initialize()

        if ms is not None:
            def _stop():
                if callback:
                    callback()
                import os
                os._exit(0)
            threading.Timer(ms / 1000, _stop).start()

    def get_clients(self, *names):
        return [self.client_name_map.get(n) for n in names]

    # Uses a for loop and dict assigments instead of for each
    def register(self, *clients):
        for c in clients:
            self.client_address_map[c.address] = c
            if c.name:
                self.client_name_map[c.name] = c
            self.clients.append(c)
            if isinstance(c, self.miner_class):
                self.miners.append(c)
            c.net = self.net
            self.net.register(c)

    def get_client_name(self, address):
        c = self.client_address_map.get(address)
        return c.name if c else None
