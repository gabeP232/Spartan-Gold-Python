import hashlib
import json
import base64

# sha256 Difference from NodeJS and Python 
# In JS, 'sha256' is built in from the 'crypto' module
# In python, 'sha256' is built in from its 'hashlib' standard library
HASH_ALG = 'sha256'


# Hash a string using the 'sha256' alg
def hash(s, encoding = 'hex'):
    
    # since python requires an explicit string, instead of any implicit val like js
    # We have to encode with 'utf-8' first to get the bytes then hash    
    if not isinstance(s, str):
        s = str(s)
    h = hashlib.sha256(s.encode('utf-8')).digest()
    if encoding == 'hex':
        return h.hex()
    elif encoding == 'base64':
        return base64.b64encode(h).decode('utf-8')
    # fallback for if encoding isn't hex or base64, return raw bytes
    return h


# Deterministically gens an RSA key pair using a BIP-39 Mnemonic and password
#
# JS: JS uses the const prng random instance that is seeded directly with the hex and strng.
# In js, it generates 512-bit keys while we used 1024 bit keys for better security.
# 
# Python : PYthon uses raw seed bytes here and feeds it into each SHA-256 block, 
# the PyCryptodome's randfunc simulates the seeded prng.
# The 'mnemonic' library from Python maps to the bip39 package like in JS
# this way we can still do mnemonic-to-seed-derivation.
# 
def generate_keypair_from_mnemonic(mnemonic_phrase, password = ''):
    from mnemonic import Mnemonic
    from Crypto.PublicKey import RSA

    mnemo = Mnemonic("english")
    # to_seed() from mnemonic, returns raw bytes, just like BIP-39s mnemonicToSeedSync
    seed = mnemo.to_seed(mnemonic_phrase, password)

    # We simulate a seeded PRNG by hashing the seed and then adding an incrementing counter
    # In JS, node-forge has a built in seeded PRNG, in python's case we use RSA.generate(),
    # since we also use a custom randfunc it's the same determinism.
    counter = [0]

    def randfunc(n):
        result = b""
        while len(result) < n:
            h = hashlib.sha256(seed + counter[0].to_bytes(8, 'big')).digest()
            result += h
            counter[0] += 1
        return result[:n]
    # 1024 bit key
    key = RSA.generate(1024, randfunc = randfunc)
    # once again decode with utf-8 to get the strings
    return {
        'public': key.publickey().export_key('PEM').decode('utf-8'),
        'private': key.export_key('PEM').decode('utf-8'),
    }

# Nondeterministic RSA key pair generation
#
# Similar differences from generating a mnemonic key pair; JS uses 512 bit, our Python proj uses 1024 bit.
# Similarly, as seen earlier Python has a 'Crypto' library equivalent to JS.
# 
# JS encodes the public key as SPKI and private keys as PKSC8, in python export_key('PEM') creates it as
# a type PKSC1 but our sign and verify funcs take any of those so it should be equivalent
def generate_keypair():
    from Crypto.PublicKey import RSA
    key = RSA.generate(1024)
    return {
        # functionally the same as in JS
        'public': key.publickey().export_key('PEM').decode('utf-8'),
        'private': key.export_key('PEM').decode('utf-8'),
    }

# Sign msg with the RSA priv key, then return the sig as a hex string
#
# Differences:
# JS uses createSign(sha256) this is the RSA + PKCS1 on sha256
# Python does the same, but has to import pkcs1_15 then adds the sha256
#
# JS checks if "msg===obj(msg)" to find objects, python does the same with isInstance.
#
# 
# Similarities:
# Both serialize the objs to jsons before signingm then return the sig as hex string.
# 
def sign(priv_key, msg):
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA

    if isinstance(msg, (dict, list)):
        msg_str = json.dumps(msg, separators = (',', ':'))
    else:
        msg_str = str(msg)

    key = RSA.import_key(priv_key)
    h = SHA256.new(msg_str.encode('utf-8'))
    signature = pkcs1_15.new(key).sign(h)
    
    return signature.hex()  # Return hex string to match JS output

# Verify the RSA-sha256 signature on a msg and public key
#
# Differences:
# Similar differences and similarities as the sign func above
# In JS it passes the hex sig directly into the .verify func
# In Python we have to decode the hex to bytes first.
#
def verify_signatures(pub_key, msg, sig):
    from Crypto.Signature import pkcs1_15
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA
    
    
    if isinstance(msg, (dict, list)):
        msg_str = json.dumps(msg, separators=(',', ':'))
    else:
        msg_str = str(msg)
 
    try:
        key = RSA.import_key(pub_key)
        h = SHA256.new(msg_str.encode('utf-8'))
        pkcs1_15.new(key).verify(h, bytes.fromhex(sig))
        return True
    except Exception:
        return False
    

# Derives wallet address from a pub key by hashing it to base64.
# Both Python and JS go about it identically, same with address_matches_key
def calc_address(key):
    return hash(str(key), 'base64')

# Checks if a wallet address exists from the pubkey given.
def address_matches_key(addr, pubkey):
    return addr == calc_address(pubkey)