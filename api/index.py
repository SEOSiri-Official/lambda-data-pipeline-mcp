# api/index.py
import os
import json
import logging
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="SEOSiri HubSpot OAuth Gateway")

# Configure logging to capture errors securely in Vercel cloud logs
logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
HUBSPOT_CLIENT_ID = "b2e60e83-2d8-41a6-b51d-318d8a339c49"
HUBSPOT_REDIRECT_URI = "https://hubappapi.seosiri.com/oauth/callback"
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = Query(None), error: str = Query(None, alias="error"), error_description: str = Query(None, alias="error_description")):
    """
    Production SaaS OAuth Gateway: Receives HubSpot's temporary authorization code,
    exchanges it for tokens, and upserts them directly into Supabase PostgreSQL.
    """
    if error:
        logging.error(f"HubSpot returned OAuth error: {error} - {error_description}")
        raise HTTPException(status_code=400, detail=f"HubSpot Authorization Error: {error}")
        
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code parameter.")

    # 1. Exchange temporary code for active tokens via HubSpot API
    token_url = "https://api.hubapi.com/oauth/v1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "redirect_uri": HUBSPOT_REDIRECT_URI,
        "code": code
    }
    
    try:
        token_res = requests.post(token_url, headers=headers, data=data, timeout=10)
        if token_res.status_code != 200:
            logging.error(f"HubSpot Token Exchange Failed: {token_res.status_code} - {token_res.text}")
            return f"""
            <html>
                <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f8fafc;">
                    <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 8px; background-color: #1e293b; border: 1px solid #334155;">
                        <h2 style="color: #dc2626; margin-bottom: 0.5em;">Token Exchange Failed</h2>
                        <p style="color: #94a3b8; line-height: 1.5;">HubSpot returned status code {token_res.status_code}. Please verify your Client Secret in Vercel environment variables.</p>
                    </div>
                </body>
            </html>
            """
        token_data = token_res.json()
    except Exception as e:
        logging.exception("Exception during HubSpot token request")
        raise HTTPException(status_code=500, detail=f"Token request exception: {str(e)}")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    # 2. Check Supabase variables
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logging.error("Supabase environment variables are missing.")
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured in Vercel.")

    # 3. Securely UPSERT into Supabase PostgreSQL via PostgREST API
    supabase_endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/integration_credentials"
    sb_headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    
    payload = {
        "platform": "HUBSPOT",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in
    }
    
    try:
        response = requests.post(supabase_endpoint, headers=sb_headers, json=payload, timeout=10)
        if response.status_code not in [200, 201]:
            logging.error(f"Supabase write failed: {response.status_code} - {response.text}")
            return f"""
            <html>
                <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f8fafc;">
                    <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 8px; background-color: #1e293b; border: 1px solid #334155;">
                        <h2 style="color: #dc2626; margin-bottom: 0.5em;">Database Write Failed</h2>
                        <p style="color: #94a3b8; line-height: 1.5;">Could not save credentials to Supabase cluster. Please verify table permissions.</p>
                    </div>
                </body>
            </html>
            """
    except Exception as e:
        logging.exception("Exception during Supabase write request")
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

    # 4. Display professional success screen
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f8fafc;">
            <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 8px; background-color: #1e293b; border: 1px solid #334155;">
                <h2 style="color: #34d399; margin-bottom: 0.5em;">Connection Successful</h2>
                <p style="color: #94a3b8; line-height: 1.5;">The SEOSiri Secure Data Pipeline has successfully established a cryptographic handshake with your HubSpot CRM portal.</p>
                <p style="color: #64748b; font-size: 13px; margin-top: 2em;">Your credentials are saved securely in your Supabase PostgreSQL cluster. You can now close this window.</p>
            </div>
        </body>
    </html>
    """