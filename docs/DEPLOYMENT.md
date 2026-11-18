# Deployment guide

The app is one stateless-ish Python web process (Flask served by gunicorn) plus an optional SQLite file for history. No build step, no external services required.

**Verification status:** the Docker image and the gunicorn/Procfile start command were built and run locally. The hosted-platform and VM/nginx steps below are standard recipes that have **not** been run on those platforms; menu names on hosting sites change, so treat them as a checklist.

## Read this first

1. **There is no authentication.** Anyone who can reach the URL can run analyses and, if a real provider is configured, spend *your* API quota.
   - Safest public setup: deploy in **demo mode** (no provider keys). It costs nothing and cannot leak anything.
   - With real keys: put the app behind authentication (platform access control, or nginx basic auth in Option C) or keep it on a private network/VPN.
2. **Secrets go in the platform's environment-variable settings**, never in the repo or the image. Rotate any key that is ever committed or pasted somewhere public.
3. **History storage:** SQLite lives in a file. On platforms with ephemeral disks it resets on every deploy/restart. Either attach a persistent volume, or set `HISTORY_ENABLED=false`.
4. Incident text is stored locally (if history is on) and sent to the chosen provider (if live). Keep that in mind for compliance.

## Environment variables

All optional. See `.env.example` for the full list.

| Variable | Purpose |
|---|---|
| `PORT` | Port to listen on (set automatically by most platforms) |
| `DEFAULT_PROVIDER` | `demo` (default), `openai`, `gemini`, `anthropic`, `bedrock` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | Provider keys |
| `OPENAI_MODEL` / `GEMINI_MODEL` / `ANTHROPIC_MODEL` / `BEDROCK_MODEL_ID` | Model names; check they exist for your account |
| `BEDROCK_REGION` | Needed for Bedrock (credentials come from an IAM role or AWS env vars) |
| `DATABASE_PATH` | SQLite file (default `data/incidents.db`; the Docker image uses `/app/data/incidents.db`) |
| `HISTORY_ENABLED` | `false` stores nothing |

## Option A: Docker (any machine or server)

```bash
docker build -t ai-incident-intelligence .
# add --build-arg INSTALL_AWS=1 if you will use Bedrock

# Demo mode, history kept in a named volume:
docker run -d --name incident-intel -p 8000:8000 -v incident-data:/app/data ai-incident-intelligence
# Open http://localhost:8000

# Real provider: pass secrets at run time (never bake them into the image)
docker run -d --name incident-intel -p 8000:8000 -v incident-data:/app/data \
  --env-file ./prod.env ai-incident-intelligence       # prod.env is NOT committed
```

The container runs as a non-root user, listens on `$PORT` (default 8000), and contains no `.env`. If you use a bind mount instead of a named volume, make the host folder writable by the container user (uid of `app`).

## Option B: an existing hosting site (Render, Railway, Heroku-style, Fly.io, etc.)

Any platform that deploys from a GitHub repo works with either method.

**Method 1: Python build (uses `Procfile`)**
1. Create a new *Web Service* from this GitHub repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn -w 2 -b 0.0.0.0:$PORT "incident_intel.app:create_app()"` (this is the `Procfile`; Heroku-style platforms read it automatically).
4. Add environment variables in the platform dashboard (none are needed for demo mode).
5. Set `HISTORY_ENABLED=false`, or attach a persistent disk and set `DATABASE_PATH` to a path on it.
6. Deploy, then open the URL.

**Method 2: Docker:** choose "Deploy from Dockerfile" instead; the platform builds the `Dockerfile` in the repo root. Set the same environment variables.

Use a Python version supported by your platform (3.9 or newer; the Docker image uses 3.12).

## Option C: manual Linux server (VM)

```bash
# 1. Install
sudo apt update && sudo apt install -y python3-venv nginx
sudo useradd --system --create-home --shell /usr/sbin/nologin incident
sudo -u incident git clone <your-repo-url> /home/incident/app
cd /home/incident/app
sudo -u incident python3 -m venv .venv
sudo -u incident .venv/bin/pip install -r requirements.txt        # add -r requirements-aws.txt for Bedrock

# 2. Secrets file, readable only by the service user (only if using a real provider)
sudo install -m 600 -o incident /dev/null /etc/incident-intel.env
sudo nano /etc/incident-intel.env          # e.g. DEFAULT_PROVIDER=... and the matching *_API_KEY, *_MODEL
```

`/etc/systemd/system/incident-intel.service`:

```ini
[Unit]
Description=AI Incident Intelligence
After=network.target

[Service]
User=incident
WorkingDirectory=/home/incident/app
EnvironmentFile=-/etc/incident-intel.env
Environment=PORT=8000 DATABASE_PATH=/home/incident/app/data/incidents.db
ExecStart=/home/incident/app/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 "incident_intel.app:create_app()"
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now incident-intel
curl http://127.0.0.1:8000/api/health
```

nginx reverse proxy with TLS and basic auth (`/etc/nginx/sites-available/incident-intel`):

```nginx
server {
    server_name incidents.example.com;
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;     # sudo apt install apache2-utils; sudo htpasswd -c /etc/nginx/.htpasswd youruser
    client_max_body_size 64k;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 90s;                    # real LLM calls can take a while
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/incident-intel /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d incidents.example.com   # HTTPS
```

Bedrock on a server: attach an IAM role with `bedrock:InvokeModel` (the permission the Converse API is authorized under) instead of storing AWS keys, set `BEDROCK_REGION` and `BEDROCK_MODEL_ID`, and enable model access in the Bedrock console.

## After deploying: smoke test

```bash
curl -s https://YOUR-URL/api/health                       # {"ok":true,...}
curl -s https://YOUR-URL/api/providers                    # configured: true only for what you set; no secrets shown
curl -s -X POST https://YOUR-URL/api/analyze -H 'Content-Type: application/json' \
  -d '{"description":"Payment processing is failing for multiple customers and timing out."}'
```

Then open the URL and run a sample incident. In demo mode the result carries a `SIMULATED` badge.

## Updating and operating

- **Update:** `git pull`, reinstall requirements if they changed, restart (`systemctl restart incident-intel`, or redeploy on the platform). Database migrations are applied automatically at startup.
- **Logs:** gunicorn writes to stdout/journal. They contain provider, severity and timing, not incident text or keys.
- **Scaling:** `-w 2` is plenty for light use. SQLite is fine for a few workers on one machine; for multiple servers you would need a shared database (not implemented).
- **Back up** the SQLite file if you keep history.
