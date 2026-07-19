# src/profiles/gdpr_seo.py
import re
import json

URL_PATTERN = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

def enforce_gdpr_seo_compliance(payload_str: str) -> dict:
    """Scans for GDPR compliance and validates SEO/AEO metadata payload specifications."""
    violations = []
    sanitized = payload_str
    
    # 1. GDPR Check: Prevent raw IP logging
    ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    if re.search(ip_pattern, sanitized):
        violations.append("GDPR_RAW_IP_ADDRESS_EXPOSURE")
        sanitized = re.sub(ip_pattern, "[REDACTED_IP_ADDRESS]", sanitized)
        
    # 2. AEO/SEO Check: Validate metadata structures
    try:
        data = json.loads(payload_str)
        if "seo_meta" in data:
            meta = data["seo_meta"]
            title = meta.get("title", "")
            desc = meta.get("description", "")
            canonical = meta.get("canonical_url", "")
            
            # Boundary rules
            if len(title) > 60:
                violations.append("SEO_AEO_TITLE_EXCEEDS_60_CHARACTERS")
            if len(desc) > 150:
                violations.append("SEO_AEO_DESCRIPTION_EXCEEDS_150_CHARACTERS")
            if canonical and not re.match(URL_PATTERN, canonical):
                violations.append("SEO_AEO_INVALID_CANONICAL_URL_FORMAT")
    except Exception:
        pass
        
    return {
        "profile": "GDPR_SEO_AEO_COMPLIANCE",
        "status": "COMPLIANCE_ALERTS_TRIGGERED" if violations else "COMPLIANT",
        "violations_found": violations,
        "payload": sanitized
    }
