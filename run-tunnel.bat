@echo off
REM Cloudflare quick tunnel — exposes local Django (port 8000) on a public HTTPS URL.
REM Prereq once:  winget install --id Cloudflare.cloudflared
REM
REM Steps to use:
REM   1. In one terminal: python manage.py runserver
REM   2. In another terminal: run-tunnel.bat
REM   3. Cloudflared prints a URL like https://xxxx-xxxx.trycloudflare.com
REM   4. Paste that URL (no trailing slash) into Vercel:
REM        Project Settings -> Environment Variables -> VITE_API_URL
REM      Then redeploy the frontend (Deployments -> Redeploy).
REM   5. Set the same URL in your local .env as BACKEND_BASE_URL if you use OAuth callbacks.
REM
REM Note: quick tunnel URLs rotate on every restart. For a stable URL, register a
REM domain on Cloudflare and use a named tunnel instead (cloudflared tunnel create).

echo ============================================================
echo  Microchore quick tunnel
echo  Pointing at http://localhost:8000
echo  Copy the trycloudflare URL printed below into Vercel VITE_API_URL
echo ============================================================
echo.

cloudflared tunnel --url http://localhost:8000
