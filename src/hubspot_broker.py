# src/hubspot_broker.py
import os
import requests
import json
import logging

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
HUBSPOT_CLIENT_ID = "b2e60e83-2de8-41a6-b51d-318d8a339c49"
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")

# Format Supabase URL
if SUPABASE_URL and not SUPABASE_URL.startswith("http"):
    SUPABASE_URL = f"https://{SUPABASE_URL}"

def get_active_token() -> str:
    """
    Retrieves the active HubSpot access token from Supabase.
    If expired, automatically triggers a refresh with HubSpot and updates the database.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("Supabase environment variables are missing.")

    # 1. Fetch credentials from Supabase
    endpoint = f"{SUPABASE_URL}/rest/v1/integration_credentials?platform=eq.HUBSPOT"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
        if response.status_code != 200 or not response.json():
            raise ValueError("No active integration found in Supabase.")

        creds = response.json()[0]
        access_token = creds.get("access_token")
        refresh_token = creds.get("refresh_token")
    except Exception as e:
        logging.error(f"[Broker Error] Failed to retrieve tokens: {e}")
        return ""

    # 2. Test the active token with a lightweight HubSpot API call
    test_url = "https://api.hubapi.com/crm/v3/objects/contacts?limit=1"
    test_headers = {"Authorization": f"Bearer {access_token}"}
    test_res = requests.get(test_url, headers=test_headers, timeout=5)

    if test_res.status_code == 200:
        return access_token

    # 3. If token is expired, trigger an automatic OAuth refresh
    print("[Broker] Token expired. Triggering automatic refresh...")
    refresh_url = "https://api.hubapi.com/oauth/v1/token"
    refresh_data = {
        "grant_type": "refresh_token",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "refresh_token": refresh_token
    }

    try:
        ref_res = requests.post(refresh_url, data=refresh_data, timeout=10)
        if ref_res.status_code == 200:
            new_creds = ref_res.json()
            new_access_token = new_creds.get("access_token")
            new_refresh_token = new_creds.get("refresh_token")
            expires_in = new_creds.get("expires_in")

            update_headers = {
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            }
            update_payload = {
                "platform": "HUBSPOT",
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": expires_in
            }
            update_res = requests.post(endpoint, headers=update_headers, json=update_payload, timeout=10)

            if update_res.status_code in (200, 201):
                print("[Broker] Tokens refreshed and synchronized successfully.")
                return new_access_token
            else:
                print(f"[Broker Error] Failed to persist refreshed token: {update_res.status_code} - {update_res.text}")
                return ""
        else:
            print(f"[Broker Error] HubSpot token refresh failed: {ref_res.text}")
            return ""
    except Exception as e:
        print(f"[Broker Exception] Failed to refresh tokens: {e}")
        return ""