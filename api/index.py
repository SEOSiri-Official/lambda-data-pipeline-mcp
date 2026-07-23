# api/index.py
import os
import sys
import json
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse

# Ensure the root directory is in the Python path so Vercel can locate 'src' modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hubspot_oauth import exchange_code_for_token

app = FastAPI(title="SEOSiri HubSpot OAuth Gateway")

# Read secure credentials from Vercel's Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = Query(None), error: str = Query(None)):
    """
    SaaS OAuth Gateway: Receives HubSpot's temporary authorization code,
    exchanges it, and upserts the tokens directly into your remote Supabase PostgreSQL database.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"HubSpot Authorization Error: {error}")
        
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code parameter.")

    # 1. Exchange temporary code for active tokens
    token_data = exchange_code_for_token(code)
    
    if "error" in token_data:
        return f"""
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h2 style="color: #dc2626;">Integration Failed</h2>
                <p>Error details: {token_data.get('details', 'Unknown error')}</p>
            </body>
        </html>
        """

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    # 2. Check if Supabase variables are configured
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured in Vercel.")

    # 3. Securely UPSERT into Supabase PostgreSQL via PostgREST API
    supabase_endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/integration_credentials"
    headers = {
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
        response = requests.post(supabase_endpoint, headers=headers, json=payload, timeout=10)
        if response.status_code not in [200, 201]:
            raise HTTPException(status_code=500, detail=f"Supabase write failed: {response.text}")
    except Exception as e:
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