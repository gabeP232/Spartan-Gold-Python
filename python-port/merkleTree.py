import utils

# Implementation for a Bitcoin like Merkle Tree
#
# In the original Spartan Gold, transacs are stored as a map
# and that map is serialized into the block header.
#
# We implement a Merkle tree for all transactions ids and it stores only the 
# 32-byte root hash in the header. 
# 
# This allows for a fixed header that is compact in size 
# Also any transaction can be proven to be in the block by calculating the merkle proof (log2(n))
# 
# Block.py imports this MerkleTree to replace the tx list in the 
# serialized header with the merkle root.

class MerkleTree:
    # 32 zero bytes in hex, for empty blocks
    EMPTY_HASH = '0' * 64
    
    # Store original list so the 'includes_transactions()' can reject IDS not in the tree
    def __init__(self, tx_ids):
        self._tx_ids = list(tx_ids)
        
    # Return merkle root hash
    def get_root(self):
        return
    
    # Checks if tx in in the tree, return true if it is.
    def includes_transaction(self, tx_id):
        return
    
    # Return the merkle proof for a path from a given tx_id
    def get_proof(self, tx_id):
        return
    
    # Verify merkle proof
    def verify_proof(tx_id, proof, root):
        return
    
    # Build the merkle tree from the bottom up
    @staticmethod
    def _build(tx_ids):
        return