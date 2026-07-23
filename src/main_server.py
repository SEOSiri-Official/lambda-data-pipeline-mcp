# src/main_server.py
import os
import sys

# Force the project root directory into the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import hmac
import hashlib
import sqlite3
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP
from src.core_validator import scan_universal_security
from src.profiles.hipaa import enforce_hipaa_compliance
from src.profiles.pci_dss import enforce_pci_compliance
from src.profiles.gdpr_seo import enforce_gdpr_seo_compliance
from src.profiles.biorobotics_guard import enforce_biorobotics_guard

mcp = FastMCP("SEOSiri-Lambda-Data-Pipeline")

# Secret key for webhook signature verification
WEBHOOK_SECRET_KEY = b"seosiri_secure_webhook_handshake_2026"

# 1. HOT TIER: High-Speed In-Memory SQLite for active routing
HOT_CONN = sqlite3.connect(":memory:", check_same_thread=False)
HOT_CURSOR = HOT_CONN.cursor()

# 2. COLD TIER: On-Disk SQLite for permanent, historical, anonymized archives
COLD_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cold_storage.db")
COLD_CONN = sqlite3.connect(COLD_DB_PATH, check_same_thread=False)
COLD_CURSOR = COLD_CONN.cursor()

def init_databases():
    # Hot Tier In-Memory Queue
    HOT_CURSOR.execute("""
        CREATE TABLE IF NOT EXISTS hot_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            payload_data TEXT,
            source_platform TEXT
        )
    """)
    HOT_CONN.commit()
    
    # Cold Tier On-Disk Archive
    COLD_CURSOR.execute("""
        CREATE TABLE IF NOT EXISTS cold_archive (
            mcp_root_id TEXT,
            timestamp TEXT,
            event_type TEXT,
            anonymized_payload TEXT,
            priority_score REAL,
            allocation_route TEXT,
            status TEXT,
            PRIMARY KEY(mcp_root_id, timestamp, event_type)
        )
    """)
    
    # Identity Stitching Registry
    COLD_CURSOR.execute("""
        CREATE TABLE IF NOT EXISTS identity_registry (
            mcp_root_id TEXT PRIMARY KEY,
            hashed_email TEXT UNIQUE,
            crm_lead_id TEXT UNIQUE,
            social_user_id TEXT UNIQUE
        )
    """)
    COLD_CONN.commit()

init_databases()

def hash_pii(raw_identifier: str) -> str:
    if not raw_identifier:
        return "NONE"
    return hashlib.sha256(raw_identifier.strip().lower().encode('utf-8')).hexdigest()

def resolve_mcp_identity(email: str = None, crm_id: str = None, social_id: str = None) -> str:
    """Stitches email, crm, and social handles into a single mcp_root_id."""
    import hashlib
    h_email = hash_pii(email) if email else None
    
    query_parts = []
    params = []
    if h_email:
        query_parts.append("hashed_email = ?")
        params.append(h_email)
    if crm_id:
        query_parts.append("crm_lead_id = ?")
        params.append(crm_id)
    if social_id:
        query_parts.append("social_user_id = ?")
        params.append(social_id)
        
    if query_parts:
        query = f"SELECT mcp_root_id FROM identity_registry WHERE {' OR '.join(query_parts)}"
        COLD_CURSOR.execute(query, params)
        row = COLD_CURSOR.fetchone()
        if row:
            return row[0]
            
    # Generate new identifier if no link exists
    new_root_id = hashlib.sha1(f"{h_email}:{crm_id}:{social_id}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
    COLD_CURSOR.execute("""
        INSERT INTO identity_registry (mcp_root_id, hashed_email, crm_lead_id, social_user_id)
        VALUES (?, ?, ?, ?)
    """, (new_root_id, h_email, crm_id, social_id))
    COLD_CONN.commit()
    return new_root_id

# =====================================================================
# TOOL 1: REAL-TIME WEBHOOK INGESTION (`ingest_realtime_webhook`)
# =====================================================================
@mcp.tool()
def ingest_realtime_webhook(event_type: str, payload_json: str, source_platform: str, hmac_signature: str = "") -> str:
    """
    Ingests high-velocity, real-time events (CMS, email opens, social mentions) 
    directly into the Hot Tier. Verifies webhook authenticity via HMAC-SHA256.
    """
    # Backpressure Check: Throttle if Hot Tier memory queue exceeds 10,000 records
    HOT_CURSOR.execute("SELECT COUNT(*) FROM hot_queue")
    queue_size = HOT_CURSOR.fetchone()[0]
    if queue_size > 10000:
        return json.dumps({"status": "BACKPRESSURE_LIMIT_EXCEEDED", "action": "THROTTLE_INGESTION_RATE"})
        
    # Webhook Security Handshake Check
    if hmac_signature:
        expected_sig = hmac.new(WEBHOOK_SECRET_KEY, payload_json.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, hmac_signature):
            return json.dumps({"status": "REJECTED", "reason": "SECURITY_SIGNATURE_MISMATCH"})
            
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    HOT_CURSOR.execute("""
        INSERT INTO hot_queue (timestamp, event_type, payload_data, source_platform)
        VALUES (?, ?, ?, ?)
    """, (timestamp, event_type.upper().strip(), payload_json, source_platform.upper().strip()))
    HOT_CONN.commit()
    
    return json.dumps({"status": "HOT_INGEST_SUCCESS", "timestamp": timestamp, "current_queue_size": queue_size + 1})

# =====================================================================
# TOOL 2: BATCH DATA SYNC (`ingest_batch_api_poll`)
# =====================================================================
@mcp.tool()
def ingest_batch_api_poll(crm_lead_id: str, email_address: str, payload_json: str, source_platform: str) -> str:
    """
    Ingests heavy, non-real-time data (CRM profiles) directly to on-disk Cold Storage.
    Executes PII redaction and maps unique stitched identities instantly.
    """
    mcp_root_id = resolve_mcp_identity(email=email_address, crm_id=crm_lead_id)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    clean_payload = payload_json.replace(email_address, "[REDACTED_PII_EMAIL]")
    
    COLD_CURSOR.execute("""
        INSERT OR REPLACE INTO cold_archive (mcp_root_id, timestamp, event_type, anonymized_payload, priority_score, allocation_route, status)
        VALUES (?, ?, 'BATCH_SYNC', ?, 1.0, 'COLD_STORAGE_DISK', 'ARCHIVED')
    """, (mcp_root_id, timestamp, clean_payload))
    COLD_CONN.commit()
    
    return json.dumps({
        "status": "BATCH_SYNC_SUCCESS",
        "mcp_root_id": mcp_root_id,
        "source": source_platform.upper()
    })

# =====================================================================
# TOOL 3: LAMBDA PIPELINE PROCESSOR (`process_lambda_pipeline`)
# =====================================================================
@mcp.tool()
def process_lambda_pipeline(max_batch_size: int = 100) -> str:
    """
    Migrates Hot Tier events to Cold Storage, executing ID stitching, 
    PII anonymization, and priority scoring.
    """
    HOT_CURSOR.execute("SELECT id, timestamp, event_type, payload_data, source_platform FROM hot_queue LIMIT ?", (max_batch_size,))
    rows = HOT_CURSOR.fetchall()
    
    migrated_count = 0
    for row_id, ts, event_type, payload_data, platform in rows:
        try:
            data = json.loads(payload_data)
            email = data.get("email")
            crm_id = data.get("crm_lead_id")
            social_id = data.get("social_user_id")
            
            mcp_root_id = resolve_mcp_identity(email=email, crm_id=crm_id, social_id=social_id)
            
            clean_payload = payload_data
            if email:
                clean_payload = clean_payload.replace(email, "[REDACTED_PII_EMAIL]")
                
            score = 1.0
            if "alert" in payload_data.lower() or "conversion" in payload_data.lower():
                score += 5.0
                
            COLD_CURSOR.execute("""
                INSERT OR REPLACE INTO cold_archive (mcp_root_id, timestamp, event_type, anonymized_payload, priority_score, allocation_route, status)
                VALUES (?, ?, ?, ?, ?, 'COLD_DISK_STORE', 'ARCHIVED')
            """, (mcp_root_id, ts, event_type, clean_payload, score))
            
            HOT_CURSOR.execute("DELETE FROM hot_queue WHERE id = ?", (row_id,))
            migrated_count += 1
        except Exception:
            pass
            
    HOT_CONN.commit()
    COLD_CONN.commit()
    return json.dumps({"status": "PIPELINE_RUN_COMPLETE", "migrated_records": migrated_count})

# =====================================================================
# TOOL 4: ENTERPRISE WAREHOUSE EXPORTER (`export_to_data_warehouse`)
# =====================================================================
@mcp.tool()
def export_to_data_warehouse(target_warehouse: str, max_records: int = 100) -> str:
    """
    Simulates exporting the anonymized, prioritized, and stitched historical 
    dataset from the Cold Storage DB directly to an enterprise data warehouse (Snowflake/ClickHouse/BigQuery).
    """
    warehouse = target_warehouse.upper().strip()
    if warehouse not in ["SNOWFLAKE", "CLICKHOUSE", "BIGQUERY"]:
        return json.dumps({"error": "Unsupported warehouse destination. Use SNOWFLAKE, CLICKHOUSE, or BIGQUERY."})
        
    COLD_CURSOR.execute("""
        SELECT mcp_root_id, timestamp, event_type, anonymized_payload, priority_score 
        FROM cold_archive 
        WHERE status = 'ARCHIVED' 
        LIMIT ?
    """, (max_records,))
    rows = COLD_CURSOR.fetchall()
    
    exported_rows = []
    for mcp_id, ts, event, payload, score in rows:
        # Update status to exported
        COLD_CURSOR.execute("""
            UPDATE cold_archive 
            SET status = 'EXPORTED', allocation_route = ? 
            WHERE mcp_root_id = ? AND timestamp = ?
        """, (warehouse, mcp_id, ts))
        exported_rows.append({
            "mcp_root_id": mcp_id,
            "timestamp": ts,
            "event_type": event,
            "payload": json.loads(payload),
            "priority_score": score
        })
        
    COLD_CONN.commit()
    return json.dumps({
        "status": "EXPORT_SUCCESS",
        "destination": warehouse,
        "exported_records_count": len(exported_rows),
        "data_stream_buffer": exported_rows
    })

# =====================================================================
# TOOL 5: DUAL-TIER ANALYTICAL SUMMARY (`retrieve_analytical_summary`)
# =====================================================================
@mcp.tool()
def retrieve_analytical_summary(subject_segment: str) -> str:
    """Queries and aggregates statistics across both Hot Tier (RAM) and Cold Tier (Disk)."""
    HOT_CURSOR.execute("SELECT COUNT(*) FROM hot_queue")
    hot_size = HOT_CURSOR.fetchone()[0]
    
    COLD_CURSOR.execute("SELECT COUNT(*) FROM cold_archive")
    cold_size = COLD_CURSOR.fetchone()[0]
    
    COLD_CURSOR.execute("SELECT COUNT(DISTINCT mcp_root_id) FROM cold_archive")
    unique_identities = COLD_CURSOR.fetchone()[0]
    
    return json.dumps({
        "data_analytics_summary": {
            "source_segment": subject_segment.upper().strip(),
            "hot_tier_pending_events_count": hot_size,
            "cold_tier_archived_records_count": cold_size,
            "unique_stitched_identities_resolved": unique_identities,
            "status": "ANALYTICS_RESOLVED"
        }
    })

# =====================================================================
# TOOL 6: UNIVERSAL SECURITY GATEKEEPER (`sanitize_and_validate_payload`)
# =====================================================================
@mcp.tool()
def sanitize_and_validate_payload(proposed_payload: str, active_profiles_csv: str = "universal") -> str:
    """Universal Security Gatekeeper: Validates proposed payloads against OWASP rules and compliance profiles."""
    scan_result = scan_universal_security(proposed_payload)
    if scan_result["status"] == "REJECTED":
        return json.dumps({
            "status": "REJECTED",
            "reason": "SECURITY_VULNERABILITY_DETECTION",
            "details": scan_result["violations"],
            "payload": scan_result["payload"]
        })
        
    profiles = [p.strip().lower() for p in active_profiles_csv.split(",")]
    current_payload = scan_result["payload"]
    triggered_violations = list(scan_result["violations"])
    active_runs = []
    dynamic_recommendations = []
    
    if "hipaa" in profiles:
        res = enforce_hipaa_compliance(current_payload)
        current_payload = res["payload"]
        triggered_violations.extend(res["violations_found"])
        active_runs.append("HIPAA")
        
    if "pci" in profiles:
        res = enforce_pci_compliance(current_payload)
        current_payload = res["payload"]
        triggered_violations.extend(res["violations_found"])
        active_runs.append("PCI_DSS")
        
    if "seo" in profiles or "gdpr" in profiles:
        res = enforce_gdpr_seo_compliance(current_payload)
        current_payload = res["payload"]
        triggered_violations.extend(res["violations_found"])
        active_runs.append("GDPR_SEO_AEO")
        
    if "biorobotics" in profiles:
        res = enforce_biorobotics_guard(current_payload)
        current_payload = res["payload"]
        triggered_violations.extend(res["violations_found"])
        dynamic_recommendations.extend(res["recommendations"])
        active_runs.append("BIOROBOTICS_SAFETY_INTERLOCK")
        
    return json.dumps({
        "status": "REMEDIATED" if dynamic_recommendations else ("AUTHORIZED_WITH_REDACTIONS" if triggered_violations else "AUTHORIZED"),
        "active_profiles": active_runs,
        "violations_detected": triggered_violations,
        "remediation_recommendations": dynamic_recommendations,
        "payload": current_payload
    })

if __name__ == "__main__":
    import time
    time.sleep(0.5)
    mcp.run(transport='stdio')