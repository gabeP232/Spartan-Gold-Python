import json
import utils

TX_CONST = "TX"

# For single transactions
# In JS it uses destructured params for the constructor signature
# For Python we receive a plain obj or an existing instance of a tx
class Transaction:
    def __init__(self, obj):
        # Copies the constructor
        if isinstance(obj, Transaction):
            self.from_addr = obj.from_addr
            self.nonce = obj.nonce
            self.pub_key = obj.pub_key
            self.sig = obj.sig
            self.fee = obj.fee
            self.outputs = [dict(o) for o in obj.outputs]
            self.data = dict(obj.data)
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
        tx_data = {
            'from': self.from_addr,
            'nonce': self.nonce,
            'pub_key': self.pub_key,
            'outputs': self.outputs,
            'fee': self.fee,
            'data': self.data,
        }
        return utils.hash(TX_CONST + json.dumps(tx_data, separators = (',', ':')))

    def sign(self, priv_key):
        self.sig = utils.sign(priv_key, self.id)

    def valid_signature(self):
        return (
            self.sig is not None
            and utils.address_matches_key(self.from_addr, self.pub_key)
            and utils.verify_signatures(self.pub_key, self.id, self.sig)
        )

    def sufficient_funds(self, block):
        return self.total_output() <= block.balance_of(self.from_addr)

    def total_output(self):
        return sum(o['amount'] for o in self.outputs) + self.fee

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