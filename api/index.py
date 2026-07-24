# api/index.py
import os
import sys
import traceback
import requests
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="SEOSiri HubSpot OAuth Gateway")

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = Query(None), error: str = Query(None)):
    try:
        if error:
            return f"<h1>HubSpot Error</h1><pre>{error}</pre>"
        if not code:
            return "<h1>Error</h1><p>Missing authorization code parameter.</p>"

        # Read environment variables
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
        HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")
        
        # Check for missing configuration
        missing = []
        if not SUPABASE_URL: missing.append("SUPABASE_URL")
        if not SUPABASE_ANON_KEY: missing.append("SUPABASE_ANON_KEY")
        if not HUBSPOT_CLIENT_SECRET: missing.append("HUBSPOT_CLIENT_SECRET")
        
        if missing:
            return f"""
            <html>
                <body style="font-family: sans-serif; padding: 40px; background: #1e293b; color: #f8fafc;">
                    <h2 style="color: #f59e0b;">Configuration Error</h2>
                    <p>Your Vercel project is missing the following Environment Variables:</p>
                    <ul style="color: #fca5a5; font-size: 18px; font-weight: bold;">
                        {''.join([f"<li>{m}</li>" for m in missing])}
                    </ul>
                    <p>Please add them in your Vercel Dashboard under Settings -> Environment Variables, then Redeploy.</p>
                </body>
            </html>
            """

        # 1. Exchange temporary code for active tokens via HubSpot API
        token_url = "https://api.hubapi.com/oauth/v1/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "authorization_code",
            "client_id": "b2e60e83-2d8-41a6-b51d-318d8a339c49",
            "client_secret": HUBSPOT_CLIENT_SECRET,
            "redirect_uri": "https://hubappapi.seosiri.com/oauth/callback",
            "code": code
        }
        
        token_res = requests.post(token_url, headers=headers, data=data, timeout=10)
        if token_res.status_code != 200:
            return f"""
            <html>
                <body style="font-family: sans-serif; padding: 40px; background: #1e293b; color: #f8fafc;">
                    <h2 style="color: #dc2626;">HubSpot Token Exchange Failed ({token_res.status_code})</h2>
                    <pre style="background: #0f172a; padding: 20px; border-radius: 6px; color: #f87171; overflow-x: auto;">{token_res.text}</pre>
                </body>
            </html>
            """
            
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        # 2. Securely UPSERT into Supabase PostgreSQL
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
        
        sb_res = requests.post(supabase_endpoint, headers=sb_headers, json=payload, timeout=10)
        if sb_res.status_code not in [200, 201]:
            return f"""
            <html>
                <body style="font-family: sans-serif; padding: 40px; background: #1e293b; color: #f8fafc;">
                    <h2 style="color: #dc2626;">Supabase Database Write Failed ({sb_res.status_code})</h2>
                    <pre style="background: #0f172a; padding: 20px; border-radius: 6px; color: #f87171; overflow-x: auto;">{sb_res.text}</pre>
                </body>
            </html>
            """

        # 3. Success Screen
        return """
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f8fafc;">
                <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 8px; background-color: #1e293b; border: 1px solid #334155;">
                    <h2 style="color: #34d399; margin-bottom: 0.5em;">Connection Successful</h2>
                    <p style="color: #94a3b8; line-height: 1.5;">Credentials successfully saved to Supabase PostgreSQL cluster!</p>
                </div>
            </body>
        </html>
        """
        
    except Exception:
        # Print the exact Python traceback directly on the browser screen for instant debugging
        err_trace = traceback.format_exc()
        return f"""
        <html>
            <body style="font-family: sans-serif; padding: 40px; background: #1e293b; color: #f8fafc;">
                <h2 style="color: #dc2626;">Serverless Function Exception Traceback</h2>
                <pre style="background: #0f172a; padding: 20px; border-radius: 6px; overflow-x: auto; color: #f87171; line-height: 1.4;">{err_trace}</pre>
            </body>
        </html>
        """