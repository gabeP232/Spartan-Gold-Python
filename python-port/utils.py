import hashlib
import json
import base64

HASH_ALG = 'sha256'

def hash(s, encoding = 'hex'):
    if not isinstance(s, str):
        s = str(s)
    h = hashlib.sha256(s.encode('utf-8')).digest()
    if encoding == 'hex':
        return h.hex()
    elif encoding == 'base64':
        return base64.b64encode(h).decode('utf-8')
    return h

def generate_keypair_from_mnemonic(mnemonic_phrase, password = ''):
    from mnemonic import Mnemonic
    from Crypto.PublicKey import RSA

    mnemo = Mnemonic("english")
    seed = mnemo.to_seed(mnemonic_phrase, password)

    counter = [0]

    def randfunc(n):
        result = b""
        while len(result) < n:
            h = hashlib.sha256(seed + counter[0].to_bytes(8, 'big')).digest()
            result += h
            counter[0] += 1
        return result[:n]

    key = RSA.generate(1024, randfunc = randfunc)
    return {
        'public': key.publickey().export_key('PEM').decode('utf-8'),
        'private': key.export_key('PEM').decode('utf-8'),
    }

def generate_keypair():
    from Crypto.PublicKey import RSA
    key = RSA.generate(1024)
    return {
        'public': key.publickey().export_key('PEM').decode('utf-8'),
        'private': key.export_key('PEM').decode('utf-8'),
    }

def sign(priv_key, msg):
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA

    if isinstance(msg, (dict, list)):
        msg_str = json.dumps(msg, separators = (',', ':'))
    else:
        msg_str = str(msg)

    try:
        key = RSA.import_key(pub_key)
        h = SHA256.new(msg_str.encode('utf-8'))
        pkcs1_15.new(key).verify(h, bytes.fromhex(sig))
        return True
    except Exception:
        return False

def calc_address(key):
    return hash(str(key), 'base64')

def address_matches_key(addr, pubkey):
    return addr == calc_address(pubkey)