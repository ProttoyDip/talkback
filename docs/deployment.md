# Deployment notes (plan.md X9)

Status: notes only. Nothing here has been run on a Nebius VM yet.

## One URL

The backend can serve the built frontend, so one process and one URL is enough:

```bash
cd frontend && npm ci && npm run build          # makes frontend/dist
cd ../backend
# in .env: FRONTEND_DIST=../frontend/dist  (and the keys, SESSION_SECRET, ALLOWED_ORIGINS)
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

`ALLOWED_ORIGINS` must list the public origin exactly (for example `https://talkback.example.com`). The WebSocket checks it (SECURITY.md T7).

## HTTPS

Browsers need HTTPS for the microphone on any address except `localhost`. Put a reverse proxy in front (Caddy is the shortest):

```
talkback.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy gets the certificate by itself and passes WebSockets through. Keep uvicorn on `127.0.0.1` so only the proxy can reach it.

## Nebius VM

1. Create a CPU VM for the app. The H100 VM is only needed for the VoiceChat container (X7, not built); the plan B cascade engine calls hosted NVIDIA speech models and needs no GPU.
2. Open only ports 80 and 443 to the internet. Do not expose port 8000 or the GPU container.
3. Copy `backend/.env` to the VM by hand. Never commit it. Set `SESSION_SECRET` (32+ characters).
4. Run uvicorn under systemd so it restarts, with `Restart=on-failure`.
5. Set a spending limit on every provider account before the URL is public.

## Not done yet

- **Access code for a public demo (SECURITY.md T8).** There is no gate yet: anyone with the URL can start a session and spend provider credits. Until one exists, share the URL only with judges, or keep it behind the proxy's basic auth (`basicauth` in Caddy).
- Rate limits are per connection (3 per IP, 30-minute sessions). There is no daily cost cap.
- X7 (the VoiceChat client) needs the H100 and the container; see prd.md section 13.
