# src/profiles/pci_dss.py
import re

CARD_PATTERN = r"\b(?:\d[ -]*?){13,16}\b"

def luhn_checksum_valid(card_num: str) -> bool:
    """Verifies credit card validity using the Luhn Algorithm."""
    digits = [int(c) for std in card_num if std.isdigit() for c in std]
    if not digits:
        return False
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        double = d * 2
        total += double if double < 10 else double - 9
    return total % 10 == 0

def enforce_pci_compliance(payload_str: str) -> dict:
    """Detects and redacts active credit card primary account numbers (PAN)."""
    sanitized = payload_str
    violations = []
    
    potential_cards = re.findall(CARD_PATTERN, sanitized)
    for card in potential_cards:
        clean_card = "".join(c for c in card if c.isdigit())
        if luhn_checksum_valid(clean_card):
            violations.append("PCI_PAN_CREDENTIAL_LEAK")
            sanitized = sanitized.replace(card, "[REDACTED_PCI_PAN]")
            
    return {
        "profile": "PCI_DSS_FINTECH",
        "status": "PAN_REDACTED" if violations else "COMPLIANT",
        "violations_found": violations,
        "payload": sanitized
    }
