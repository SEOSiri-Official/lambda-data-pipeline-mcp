# tests/test_analytics.py
import json
import os
import sys

# Force the project root directory into the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main_server import (
    ingest_realtime_webhook, 
    ingest_batch_api_poll, 
    process_lambda_pipeline, 
    sanitize_and_validate_payload,
    COLD_DB_PATH
)

def test_universal_sql_injection():
    result_raw = sanitize_and_validate_payload("SELECT * FROM users; --", "universal")
    result = json.loads(result_raw)
    assert result["status"] == "REJECTED"
    assert "SQL_INJECTION_VECTOR" in result["details"]

def test_lambda_pipeline_and_id_stitching():
    if os.path.exists(COLD_DB_PATH):
        try:
            os.remove(COLD_DB_PATH)
        except PermissionError:
            pass

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
