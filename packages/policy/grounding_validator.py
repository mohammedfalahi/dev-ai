import re

from packages.contracts.ico import IncidentContextObject
from packages.policy.tier import ActionTier, classify_command


class GroundingValidator:
    """
    Validates actions and spoken text against the strict Grounding Contract.
    """
    
    @staticmethod
    def validate_action(candidate_command: str, ico: IncidentContextObject) -> tuple[bool, str]:
        """
        Validates that a proposed command matches verbatim text from an eligible, verified runbook chunk.
        """
        is_found = False
        found_chunk_id = None
        
        # Grounding check: The command must exist exactly within the retrieved runbook chunk content
        for runbook in ico.candidate_runbooks:
            if candidate_command.strip() in runbook.content:
                is_found = True
                found_chunk_id = runbook.chunk_id
                break
                
        if not is_found:
            return False, "UNSUPPORTED_COMMAND: Command not found in retrieved runbook chunks."
            
        tier = classify_command(candidate_command)
        
        # For mutating actions, ensure we have properly audited the specific chunk it originated from
        if tier == ActionTier.TIER_2_MUTATING:
            if not found_chunk_id:
                return False, "UNSUPPORTED_COMMAND: Mutating action requires a valid chunk_id for audit logging."
                
        return True, f"VALID: Command is authorized under {tier.value} from chunk {found_chunk_id}."

    @staticmethod
    def validate_voice_brief(brief_text: str, ico: IncidentContextObject) -> bool:
        """
        Ensures the spoken text doesn't contain unsafe formatting artifacts like Markdown or JSON 
        that would severely degrade the TTS experience or violate generation boundaries.
        """
        # Reject markdown backticks
        if "`" in brief_text:
            return False
            
        # Reject raw JSON literals / brackets
        if re.search(r'\{.*\}', brief_text):
            return False
            
        return True
