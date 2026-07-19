# src/core_validator.py
import re
import json

# Standard OWASP Top 10 Injection Vectors
SQL_INJECTION_PATTERN = r"UNION\s+SELECT|SELECT\s+.*\s+FROM|--|/\*|\*/"
COMMAND_INJECTION_PATTERN = r";\s*rm\s+-rf|;\s*bash|\|\s*sh|>\s*/dev/null"
PATH_TRAVERSAL_PATTERN = r"\.\./\.\./|/etc/passwd|/windows/win\.ini"

def scan_universal_security(proposed_json: str) -> dict:
    """Scans payloads for raw credential leakage, SQLi, command execution, and path traversal."""
    violations = []
    sanitized_json = proposed_json
    
    # Credential Sanitization
    credential_patterns = {
        "Bearer_Token": r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*",
        "API_Key": r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9\-\._~]{16,}['\"]"
    }
    
    for name, pattern in credential_patterns.items():
        if re.search(pattern, sanitized_json, re.IGNORECASE):
            violations.append(f"LEAKED_CREDENTIAL_{name.upper()}")
            sanitized_json = re.sub(pattern, f"[REDACTED_{name.upper()}]", sanitized_json, flags=re.IGNORECASE)
            
    # Injection Scans
    if re.search(SQL_INJECTION_PATTERN, sanitized_json, re.IGNORECASE):
        violations.append("SQL_INJECTION_VECTOR")
    if re.search(COMMAND_INJECTION_PATTERN, sanitized_json, re.IGNORECASE):
        violations.append("COMMAND_INJECTION_VECTOR")
    if re.search(PATH_TRAVERSAL_PATTERN, sanitized_json, re.IGNORECASE):
        violations.append("PATH_TRAVERSAL_VECTOR")
        
    return {
        "status": "REJECTED" if any("INJECTION" in v for v in violations) else ("SANITIZED" if violations else "CLEAN"),
        "violations": violations,
        "payload": sanitized_json
    }
