import os
import sys
import json
import re
import datetime
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
CREDENTIALS_FILE = HERE / "credentials.json"
TOKEN_FILE = HERE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]

auth_code = None
server_error = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code, server_error
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            auth_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Jarvis - Google Tasks Connected</title></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 60px 20px; background: #0b0f19; color: #f1f5f9;">
                <div style="max-width: 500px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <div style="font-size: 50px; margin-bottom: 20px;">&#x2705;</div>
                    <h1 style="color: #38bdf8; margin: 0 0 15px; font-size: 26px;">Google Tasks Connected!</h1>
                    <p style="color: #94a3b8; font-size: 16px; line-height: 1.5; margin: 0 0 25px;">
                        Jarvis has successfully authenticated with your Google Tasks. You can now close this tab and return to Jarvis.
                    </p>
                    <div style="font-size: 13px; color: #64748b;">Jarvis AI Assistant &bull; Desktop Widget</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        elif "error" in query:
            server_error = query.get("error_description", query["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h3>Authentication error: {server_error}</h3>".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request.")

    def log_message(self, format, *args):
        pass


def run_oauth_flow():
    if not CREDENTIALS_FILE.exists():
        print("=" * 70)
        print("[!] Credentials file not found: credentials.json")
        print("=" * 70)
        print("To connect Google Tasks:")
        print(" 1. Go to Google Cloud Console: https://console.cloud.google.com/")
        print(" 2. Enable the 'Google Tasks API'.")
        print(" 3. Go to 'Credentials' -> 'Create Credentials' -> 'OAuth client ID'.")
        print(" 4. Choose Application type: 'Web application'.")
        print(" 5. Add Authorized redirect URI: http://localhost:5678/rest/oauth2-credential/callback")
        print(" 6. Download the JSON, rename it to 'credentials.json', and place it in this folder.")
        print(" (See credentials.json.example for reference structure.)")
        print("=" * 70)
        return False

    from google_auth_oauthlib.flow import Flow

    cred_data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    key_name = list(cred_data.keys())[0]
    redirect_uris = cred_data[key_name].get("redirect_uris", [])
    redirect_uri = redirect_uris[0] if redirect_uris else "http://localhost:5678/rest/oauth2-credential/callback"

    parsed_uri = urlparse(redirect_uri)
    port = parsed_uri.port or 5678
    host = parsed_uri.hostname or "localhost"

    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    print("=" * 70)
    print("JARVIS GOOGLE TASKS SETUP")
    print("=" * 70)
    print("Opening browser for Google Tasks authorization...")
    print(f"URL: {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer((host, port), OAuthCallbackHandler)
    print(f"Waiting for authorization on {host}:{port}...")

    # Handle incoming redirect
    server.handle_request()
    server.server_close()

    if not auth_code:
        print(f"[Error] No authorization code received. {server_error or ''}")
        return False

    print("Exchanging code for access token...")
    flow.fetch_token(code=auth_code)
    creds = flow.credentials

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print(f"[Success] token.json saved to: {TOKEN_FILE}")

    # Test query
    test_google_tasks()
    return True


def test_google_tasks():
    if not TOKEN_FILE.exists():
        print("[Test] No token.json found.")
        return

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    service = build("tasks", "v1", credentials=creds, cache_discovery=False)

    print("\n[Google Tasks API Test]")
    lists_res = service.tasklists().list(maxResults=10).execute()
    task_lists = lists_res.get("items", [])
    print(f"Found {len(task_lists)} Task List(s):")
    for tl in task_lists:
        print(f" - List: '{tl['title']}' (ID: {tl['id']})")
        tasks_res = service.tasks().list(tasklist=tl['id'], showCompleted=False, maxResults=50).execute()
        items = tasks_res.get("items", [])
        print(f"   Active Tasks: {len(items)}")
        for t in items:
            due = t.get("due", "No due date")
            print(f"     * {t.get('title')} (due: {due})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_google_tasks()
    else:
        run_oauth_flow()
