# optimize_ai/config/constants.py
"""
Configuration constants for CAI3 compression features.
"""

# CAI3 Dense FLOW Configuration Flags
# These flags control ultra-dense compression features for achieving 70-90% token reduction

# Dense FLOW syntax flags (enabled by default for MEDIUM tier when include_all_methods=True)
DENSE_FLOW_ASCII_OPS = True  # Use ASCII operators like ≠, ≤, ≥, ∈, ∉ instead of words
DENSE_FLOW_NO_SPACES = True  # Remove spaces in expressions: x=y+z instead of x = y + z
DENSE_FLOW_INLINE_BLOCKS = True  # Allow {…} and ; separators for compact blocks
DENSE_FLOW_ALIAS_CHAINS = True  # Emit D: alias dictionary for chained references
DENSE_FLOW_POOL_STRINGS_MIN_LEN = 3  # Pool strings >= this length (was 5, now more aggressive)

# LITE table and CID optimization flags
LITE_FLAT_TABLE = True  # Put entire table on one line for ultra-compact format
LITE_CID_ALIAS_MAP = True  # Emit X: short-CID map + use #k instead of full CIDs
LITE_KEEP_E_TERMINATOR = True  # Keep 'E' terminators for safer parsing (can drop later)

# Additional compression settings
CAI3_MAX_EDIT_SCOPE_METHODS = 2  # Maximum methods with full bodies in MEDIUM tier
CAI3_MIN_BUG_SCORE = 10  # Minimum score threshold for method inclusion
CAI3_AGGRESSIVE_NAME_COMPRESSION = True  # Use single/double char name compression
CAI3_POOL_CONSTANTS = True  # Pool repeated constants and strings
