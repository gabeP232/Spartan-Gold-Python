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
        
        self._levels = self._build(self._tx_ids)
        
    # Return merkle root hash
    # Changing any tx changes the root, so the header hash needs to change
    # 64 char hex string
    def get_root(self):
        # no transactions so empty
        if not self._levels:
            return self.EMPTY_HASH
        
        # at the top level, get index 0, which is the root.
        return self._levels[-1][0]
    
    
    # Checks if tx in in the tree, return true if it is.
    def includes_transaction(self, tx_id):
        # check if tree exists
        if not self._levels:
            return False
        
        # Hash query first, since tree stores the hashes
        target = utils.hash(tx_id)
        # check in the leaf level
        return target in self._levels[0]
    
    
    # Return the merkle proof for a path from a given tx_id
    # Just like our lab, but in Python, same functionality
    def get_proof(self, tx_id):
        # Check if tree exists
        if not self._levels:
            return False
        
        # Get hash of leaf and check if it exists in the left level
        leaf_hash = utils.hash(tx_id)
        if leaf_hash not in self._levels[0]:
            return None
        
        proof = []
        index = self._levels[0].index(leaf_hash)
        
        # iterate through each level of the tree except the root
        for level in self._levels[:-1]:
            # even index = sibling is on the right +1
            # odd index = sibling is on the left 
            
            # Right
            if index % 2 == 0:
                sibling_index = index + 1
                
                # if node was duplicated (then its an odd count at curr level) so the sibling index is its own index
                if sibling_index >= len(level):   
                    sibling_index = index
                # Right hash
                proof.append({'hash': level[sibling_index], 'position': 'right'})
            # Left
            else:
                sibling_index = index - 1 
                proof.append({'hash': level[sibling_index], 'position': 'left'})
            
            # Move up to the next level/parent index
            index = index // 2
        
        return proof

                
    
    # Verify merkle proof without searching the full tree
    # Needs the txId, proof from get_proof(), and merkle root stored in block header
    # returns true if valid
    @staticmethod
    def verify_proof(tx_id, proof, root):
        # current leaf
        curr = utils.hash(tx_id)
        # go through tree all the way until the root
        for step in proof:
            sibling = step['hash']
            #Left
            if step['positon'] == 'right':
                curr = utils.hash(curr + sibling)
            #Right
            else:
                curr == utils.hash(sibling + curr)
        # if proof completed, but curr != root, then it isnt a valid proof
        return curr == root
    
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