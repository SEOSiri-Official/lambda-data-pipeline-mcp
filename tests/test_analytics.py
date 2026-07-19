# tests/test_analytics.py
import json
import os
import sys
import sqlite3

# Force the project root directory into the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main_server import (
    ingest_realtime_webhook, 
    ingest_batch_api_poll, 
    process_lambda_pipeline, 
    sanitize_and_validate_payload,
    export_to_data_warehouse,
    retrieve_analytical_summary,
    COLD_DB_PATH
)

def test_universal_sql_injection():
    result_raw = sanitize_and_validate_payload("SELECT * FROM users; --", "universal")
    result = json.loads(result_raw)
    assert result["status"] == "REJECTED"
    assert "SQL_INJECTION_VECTOR" in result["details"]

def test_biorobotics_interlock_remediation_in_pipeline():
    # Out of boundary coordinate: X=240.0 (Max is 200.0), F=2000 (Max is 1500)
    result_raw = sanitize_and_validate_payload("G1 X240.0 Y10.0 F2000", "biorobotics")
    result = json.loads(result_raw)
    assert result["status"] == "REMEDIATED"
    assert "DECK_LIMIT_X_EXCEEDED" in result["violations_detected"]
    assert result["payload"] == "G1 X200.0 Y10.0 F500.0"

def test_lambda_pipeline_id_stitching_and_dw_export():
    # Programmatically wipe the tables instead of deleting the file to prevent Windows PermissionErrors
    if os.path.exists(COLD_DB_PATH):
        conn = sqlite3.connect(COLD_DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM cold_archive")
            cursor.execute("DELETE FROM identity_registry")
            conn.commit()
        except sqlite3.OperationalError:
            pass # Tables do not exist yet, safe to proceed
        finally:
            conn.close()

    # 1. Ingest real-time event to Hot Tier (RAM) containing Social and Email PII
    hot_payload = json.dumps({
        "social_user_id": "twitter_badhan",
        "email": "momenul@seosiri.com",
        "event": "retweet"
    })
    hot_res = json.loads(ingest_realtime_webhook("social_mention", hot_payload, "twitter"))
    assert hot_res["status"] == "HOT_INGEST_SUCCESS"
    
    # 2. Ingest batch REST poll directly to Cold Storage (Disk) containing CRM and same Email PII
    batch_payload = json.dumps({
        "crm_lead_id": "hubspot_lead_99",
        "email": "momenul@seosiri.com",
        "status": "subscriber"
    })
    batch_res = json.loads(ingest_batch_api_poll("hubspot_lead_99", "momenul@seosiri.com", batch_payload, "hubspot"))
    assert batch_res["status"] == "BATCH_SYNC_SUCCESS"
    mcp_root_id = batch_res["mcp_root_id"]
    
    # 3. Execute Lambda Pipeline to migrate Hot to Cold & resolve identity stitching
    pipeline_res = json.loads(process_lambda_pipeline(max_batch_size=10))
    assert pipeline_res["status"] == "PIPELINE_RUN_COMPLETE"
    assert pipeline_res["migrated_records"] == 1
    
    # 4. Check analytical summary across both tiers (Hot should be 0, Cold should be 2)
    summary_res = json.loads(retrieve_analytical_summary("marketing_analytics"))
    summary = summary_res["data_analytics_summary"]
    assert summary["hot_tier_pending_events_count"] == 0
    assert summary["cold_tier_archived_records_count"] == 2
    assert summary["unique_stitched_identities_resolved"] == 1
    
    # 5. Export clean, anonymized dataset from Cold Storage to ClickHouse Data Warehouse
    export_res = json.loads(export_to_data_warehouse("clickhouse", max_records=10))
    assert export_res["status"] == "EXPORT_SUCCESS"
    assert export_res["destination"] == "CLICKHOUSE"
    assert export_res["exported_records_count"] == 2
    
    # Verify that the email is fully redacted at rest in the exported warehouse buffer
    payload_exported = export_res["data_stream_buffer"][0]["payload"]
    assert "momenul@seosiri.com" not in str(payload_exported)