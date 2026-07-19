# src/profiles/hipaa.py
import re

# Standard HIPAA PHI Regex patterns
SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"
DOB_PATTERN = r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/(19|20)\d{2}\b"

def enforce_hipaa_compliance(payload_str: str) -> dict:
    """Scans and scrubs HIPAA-protected PII/PHI before external transit."""
    sanitized = payload_str
    violations = []
    
    if re.search(SSN_PATTERN, sanitized):
        violations.append("PHI_SOCIAL_SECURITY_NUMBER")
        sanitized = re.sub(SSN_PATTERN, "[REDACTED_SSN]", sanitized)
        
    if re.search(DOB_PATTERN, sanitized):
        violations.append("PHI_DATE_OF_BIRTH")
        sanitized = re.sub(DOB_PATTERN, "[REDACTED_DOB]", sanitized)
        
    return {
        "profile": "HIPAA_HEALTHCARE",
        "status": "PII_REDACTED" if violations else "COMPLIANT",
        "violations_found": violations,
        "payload": sanitized
    }
