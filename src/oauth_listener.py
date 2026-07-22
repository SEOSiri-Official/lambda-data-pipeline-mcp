# src/oauth_listener.py
import sqlite3
import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from src.hubspot_oauth import exchange_code_for_token

app = FastAPI(title="SEOSiri OAuth Listener")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cold_storage.db")

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(code: str = Query(None), error: str = Query(None)):
    """
    Listens on https://api.seosiri.com/oauth/callback.
    Captures the HubSpot authorization code, exchanges it, and saves tokens to Cold Storage.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"HubSpot Authorization Error: {error}")
        
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code parameter.")

    # 1. Exchange the temporary code for permanent tokens
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

    # Extract tokens
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    
    # 2. Save tokens securely to your Cold Storage on-disk database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Create table to store the integration credentials if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS integration_credentials (
                platform TEXT PRIMARY KEY,
                access_token TEXT,
                refresh_token TEXT,
                expires_in INTEGER
            )
        """)
        cursor.execute("""
            INSERT OR REPLACE INTO integration_credentials (platform, access_token, refresh_token, expires_in)
            VALUES ('HUBSPOT', ?, ?, ?)
        """, (access_token, refresh_token, expires_in))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database write failure: {str(e)}")
    finally:
        conn.close()

    # 3. Display a professional success screen to the user
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px; background-color: #0f172a; color: #f8fafc;">
            <div style="max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 8px; background-color: #1e293b; border: 1px solid #334155;">
                <h2 style="color: #34d399; margin-bottom: 0.5em;">Connection Successful</h2>
                <p style="color: #94a3b8; line-height: 1.5;">The SEOSiri Secure Data Pipeline has successfully established a cryptographic handshake with your HubSpot CRM portal.</p>
                <p style="color: #64748b; font-size: 13px; margin-top: 2em;">You can now close this window and resume your AI session.</p>
            </div>
        </body>
    </html>
    """