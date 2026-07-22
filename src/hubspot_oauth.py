# src/hubspot_oauth.py
import os
import json
import requests

# Official B2B CRM OAuth variables for SEOSiri-Official
HUBSPOT_CLIENT_ID = "b2e60e83-2d8-41a6-b51d-318d8a339c49"
HUBSPOT_REDIRECT_URI = "https://api.seosiri.com/oauth/callback"

# INSTRUCTIONS: Click "Show" next to Client secret in your HubSpot browser,
# copy it, and paste it here replacing the text below:
HUBSPOT_CLIENT_SECRET = "18e474dc-8dfc-4cef-94e9-dee49721093b"

def exchange_code_for_token(authorization_code: str) -> dict:
    """
    Exchanges the temporary authorization code returned by HubSpot's 
    OAuth redirect flow for an active access_token and refresh_token.
    """
    url = "https://api.hubapi.com/oauth/v1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "redirect_uri": HUBSPOT_REDIRECT_URI,
        "code": authorization_code
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            print("[OAuth] Token exchange successful.")
            return response.json() # Returns 'access_token', 'refresh_token', 'expires_in'
        
        error_data = response.json() if response.text else {}
        print(f"[OAuth Error] Exchange failed ({response.status_code}): {error_data}")
        return {"error": f"Failed. Status: {response.status_code}", "details": error_data}
    except Exception as e:
        print(f"[OAuth Exception] Connection error: {e}")
        return {"error": str(e)}

def refresh_access_token(refresh_token: str) -> dict:
    """
    Uses your saved refresh_token to automatically retrieve a fresh 
    access_token once the old one expires (after 30 minutes).
    """
    url = "https://api.hubapi.com/oauth/v1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            print("[OAuth] Token refresh successful.")
            return response.json()
        return {"error": f"Refresh failed. Status: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}