import re
from enum import Enum


class ActionTier(str, Enum):
    TIER_1_READ_ONLY = "TIER_1_READ_ONLY"
    TIER_2_MUTATING = "TIER_2_MUTATING"


def classify_command(command: str) -> ActionTier:
    """
    Deterministically classifies a proposed command as mutating or read-only.
    Uses strict keyword pattern matching to protect against unsafe execution.
    """
    cmd_lower = command.lower()
    
    # Heuristic regex for mutative keywords representing Tier 2 actions
    mutative_keywords = r'\b(restart|delete|patch|scale|flush|kill|drop|alter|apply|create|update|rm)\b'
    
    if re.search(mutative_keywords, cmd_lower):
        return ActionTier.TIER_2_MUTATING
        
    return ActionTier.TIER_1_READ_ONLY
