LOST KINGSLAND ADMIN - PUBLIC SHARE WITH CLOUDFLARE
====================================================

FASTEST WAY
-----------
Open PowerShell in this Admin folder and run:

    .\cloud.bat

The script will:
1. Check ADMIN_TOKEN.
2. Install cloudflared through winget if needed.
3. Start a separate protected Admin instance on 127.0.0.1:8788.
4. Disable Local Owner for that public instance.
5. Protect ALL HTML/static/API routes with HTTP Basic authentication.
6. Create a temporary https://*.trycloudflare.com URL.

PUBLIC LOGIN
------------
Username: admin
Password: the current ADMIN_TOKEN value in .env

When a write action asks for ADMIN_TOKEN inside the Admin UI, enter the same
ADMIN_TOKEN. The browser stores it only in sessionStorage for that tab/session.

IMPORTANT
---------
- Keep the normal local Admin on 127.0.0.1:8787 if you want; public sharing uses 8788.
- Do NOT change ADMIN_ALLOW_REMOTE_NO_AUTH to true.
- Do NOT share ADMIN_TOKEN publicly.
- Ctrl+C in the cloud.bat window stops the tunnel.
- Quick Tunnel URLs are temporary and intended for demo/testing.

MANUAL COMMAND (if you prefer two terminals)
--------------------------------------------
Terminal 1:
    .\run_admin_public.bat

Terminal 2:
    cloudflared tunnel --url http://127.0.0.1:8788
