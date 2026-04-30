import json
import utils

TX_CONST = "TX"

# For single transactions
# In JS it uses destructured params for the constructor signature
# For Python we receive a plain obj or an existing instance of a tx
class Transaction:
    def __init__(self, obj):
        # Copies the constructor if an instance exists
        if isinstance(obj, Transaction):
            self.from_addr = obj.from_addr
            self.nonce = obj.nonce
            self.pub_key = obj.pub_key
            self.sig = obj.sig
            self.fee = obj.fee
            self.outputs = [dict(o) for o in obj.outputs]
            self.data = dict(obj.data)
        
        # Construct from a plain dict 
        # doing obj.get(key, default) is equivalent to JS constructor ({from, nonce, pubkey, sig, etc..})
        else:
            self.from_addr = obj.get('from')
            self.nonce = obj.get('nonce')
            self.pub_key = obj.get('pubKey')
            self.sig = obj.get('sig')
            self.fee = obj.get('fee', 0)
            self.data = obj.get('data') or {}
            raw_outputs = obj.get('outputs') or []
            self.outputs = []
            
            for o in raw_outputs:
                amount = o.get('amount', 0)
                if not isinstance(amount, int):
                    amount = int(amount)
                self.outputs.append({'amount': amount, 'address': o['address']})

    @property
    def id(self):
        # Gets the unique tx id, serialize to keep the same JSON format
        tx_data = {
            'from': self.from_addr,
            'nonce': self.nonce,
            'pubkey': self.pub_key,
            'outputs': self.outputs,
            'fee': self.fee,
            'data': self.data,
        }
        return utils.hash(TX_CONST + json.dumps(tx_data, separators = (',', ':')))

    # Signs the tx id with the senders privKey
    def sign(self, priv_key):
        self.sig = utils.sign(priv_key, self.id)

    # Checks signature exists, matches address, and the signature is valid
    def valid_signature(self):
        return (
            self.sig is not None
            and utils.address_matches_key(self.from_addr, self.pub_key)
            and utils.verify_signatures(self.pub_key, self.id, self.sig)
        )

    # Check if senders balance has enough for the total output
    def sufficient_funds(self, block):
        return self.total_output() <= block.balance_of(self.from_addr)

    # In Python Sum used like this is equivalent to JS .reduce
    def total_output(self):
        return sum(o['amount'] for o in self.outputs) + self.fee

    # Serialize the tx to a plain dict for JSON format
    # In JS objects are already plain dicts so its passsed to stringify
    # In Python it needs a method to serialize, so this matches the JS field names
    def to_dict(self):
        return {
            'from': self.from_addr,
            'nonce': self.nonce,
            'pubKey': self.pub_key,
            'sig': self.sig,
            'fee': self.fee,
            'outputs': self.outputs,
            'data': self.data,
        }
    
    # Helper method to return the serialized size of the tx in bytes
    # this is used to help enforce a Max Block Size in bytes
    # i.e. helps in implementing the 'FIXED BLOCK SIZE'
    def byte_size(self):
        return len(json.dumps(self.to_dict(), separators=(',',':')).encode('utf-8'))