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
        
        self._levels = self.build(self._tx_ids)
        
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
    # tx_ids is the list of tx id strings
    # returns all levels of the tree
    # index 0 is leaves, index -1 is root, [] is empty
    @staticmethod
    def _build(tx_ids):
        if not tx_ids:
            return[]
        
        # leaf level, hashes each tx_id once
        curr_level = [utils.hash(tx_id) for tx_id in tx_ids]
        levels = [curr_level]
        
        while len(curr_level ) > 1:
            next_level = []
            
            # Get pairs, duplicate the last node if the count is odd
            for i in range(0, len(curr_level), 2):
                left = curr_level[i]
                
                # If i + 1 is out of range, duplicate the left node.
                if i + 1 < len(curr_level):
                    right = curr_level[i+1]
                else:
                    right = left
                next_level.append(utils.hash(left+right))
            curr_level = next_level
            levels.append(curr_level)
    
        
        return levels