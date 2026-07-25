# api/index.py
import os
import json
import logging
import secrets
import base64
import hashlib
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="SEOSiri HubSpot OAuth Gateway")

# Configure logging to capture errors securely in Vercel cloud logs
logging.basicConfig(level=logging.INFO)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Auto-fix missing https:// scheme
if SUPABASE_URL and not SUPABASE_URL.startswith("http"):
    SUPABASE_URL = f"https://{SUPABASE_URL}"

HUBSPOT_CLIENT_ID = "b2e60e83-2de8-41a6-b51d-318d8a339c49"
HUBSPOT_REDIRECT_URI = "https://hubappapi.seosiri.com/oauth/callback"
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")


def generate_pkce_pair():
    """Generates a fresh, RFC 7636-compliant PKCE verifier/challenge pair."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


def _supabase_headers(extra: dict = None) -> dict:
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _utc_now_iso() -> str:
    """Explicit UTC timestamp — DEFAULT NOW() on the column only fires on
    INSERT, not on ON CONFLICT DO UPDATE merges, so every write here sets
    updated_at explicitly instead of relying on the column default."""
    return datetime.now(timezone.utc).isoformat()


@app.get("/oauth/install")
async def oauth_install():
    """
    Starts the OAuth 2.1 + PKCE handshake. Generates a fresh verifier/challenge
    pair, persists the verifier in Supabase keyed by a one-time `state` value,
    and redirects the user to HubSpot's authorize URL with the matching challenge.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured in Vercel.")

    state = secrets.token_urlsafe(24)
    code_verifier, code_challenge = generate_pkce_pair()

    pkce_endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/oauth_pkce_sessions"
    try:
        res = requests.post(
            pkce_endpoint,
            headers=_supabase_headers({"Prefer": "resolution=merge-duplicates"}),
            json={"state": state, "code_verifier": code_verifier},
            timeout=10,
        )
        if res.status_code not in (200, 201):
            logging.error(f"Failed to persist PKCE session: {res.status_code} - {res.text}")
            raise HTTPException(status_code=500, detail="Could not initialize PKCE session in Supabase.")
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Exception while persisting PKCE session")
        raise HTTPException(status_code=500, detail=f"PKCE session error: {str(e)}")

    authorize_url = (
        "https://mcp.hubspot.com/oauth/authorize/user"
        f"?client_id={HUBSPOT_CLIENT_ID}"
        f"&redirect_uri={HUBSPOT_REDIRECT_URI}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        "&code_challenge_method=S256"
    )
    return RedirectResponse(authorize_url)


@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None, alias="error"),
    error_description: str = Query(None, alias="error_description"),
):
    """
    Production SaaS OAuth Gateway: Receives HubSpot's temporary authorization code,
    looks up the matching PKCE verifier by `state`, exchanges the code for tokens,
    and upserts them directly into Supabase PostgreSQL.
    """
    if error:
        logging.error(f"HubSpot returned OAuth error: {error} - {error_description}")
        raise HTTPException(status_code=400, detail=f"HubSpot Authorization Error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code parameter.")

    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter; cannot verify PKCE session.")

    # 0. Check Supabase variables
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logging.error("Supabase environment variables are missing.")
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured in Vercel.")

    # 1. Look up the code_verifier that matches this state (set during /oauth/install)
    pkce_endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/oauth_pkce_sessions?state=eq.{state}"
    try:
        pkce_res = requests.get(pkce_endpoint, headers=_supabase_headers(), timeout=10)
        pkce_rows = pkce_res.json() if pkce_res.status_code == 200 else []
    except Exception as e:
        logging.exception("Exception while fetching PKCE session")
        raise HTTPException(status_code=500, detail=f"PKCE lookup error: {str(e)}")

    if not pkce_rows:
        raise HTTPException(
            status_code=400,
            detail="No matching PKCE session found for this state. Start the flow again at /oauth/install.",
        )

    code_verifier = pkce_rows[0]["code_verifier"]

    # 2. Exchange temporary code for active tokens via HubSpot API (with the real PKCE verifier)
    token_url = "https://api.hubapi.com/oauth/v1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "client_id": HUBSPOT_CLIENT_ID,
        "client_secret": HUBSPOT_CLIENT_SECRET,
        "redirect_uri": HUBSPOT_REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
    }

    try:
        token_res = requests.post(token_url, headers=headers, data=data, timeout=10)
        if token_res.status_code != 200:
            # THIS WILL PRINT HUBSPOT'S EXACT ERROR REASON DIRECTLY ON YOUR BROWSER SCREEN
            return f"""
            <html>
                <body style="font-family: sans-serif; padding: 40px; background: #1e293b; color: #f8fafc;">
                    <h2 style="color: #dc2626;">HubSpot 400 Error Details</h2>
                    <p><strong>Redirect URI Sent:</strong> {HUBSPOT_REDIRECT_URI}</p>
                    <p><strong>Raw HubSpot Response:</strong></p>
                    <pre style="background: #0f172a; padding: 20px; border-radius: 6px; color: #f87171; overflow-x: auto;">{token_res.text}</pre>
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

    # 3. Securely UPSERT into Supabase PostgreSQL via PostgREST API
    supabase_endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/integration_credentials"
    sb_headers = _supabase_headers({"Prefer": "resolution=merge-duplicates"})

    payload = {
        "platform": "HUBSPOT",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "updated_at": _utc_now_iso(),
    }

    try:
        response = requests.post(supabase_endpoint, headers=sb_headers, json=payload, timeout=10)
        if response.status_code not in [200, 201]:
            logging.error(f"Supabase write failed: {response.status_code} - {response.text}")
            return """
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

    # 4. Clean up the used PKCE session (one-time use)
    try:
        requests.delete(
            f"{SUPABASE_URL.rstrip('/')}/rest/v1/oauth_pkce_sessions?state=eq.{state}",
            headers=_supabase_headers(),
            timeout=10,
        )
    except Exception:
        logging.warning("Failed to clean up PKCE session row; non-fatal.")

    # 5. Display professional success screen
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