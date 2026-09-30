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


def classify_action_tier(command: str) -> int:
    """
    Classifies a proposed command into an integer policy tier:
    - 1 for TIER_1_READ_ONLY (permitted for automated execution)
    - 2 for TIER_2_MUTATING (flagged for human escalation)
    """
    tier = classify_command(command)
    return 2 if tier == ActionTier.TIER_2_MUTATING else 1


def is_auto_executable(command: str) -> bool:
    """
    Returns True if the command is Tier 1 (Read-Only) and safe for automatic execution.
    Returns False if the command is Tier 2 (Mutating) which must block server-side auto-execution.
    """
    return classify_command(command) == ActionTier.TIER_1_READ_ONLY


def requires_human_escalation(command: str) -> bool:
    """
    Returns True if the command is Tier 2 (Mutating) and requires human escalation.
    """
    return classify_command(command) == ActionTier.TIER_2_MUTATING

