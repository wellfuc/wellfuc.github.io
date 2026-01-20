# AppHub (Internal App Portal + CMS)

AppHub is a production-grade internal portal + CMS for discovering web apps and distributing desktop installers. It is designed to sit behind `oauth2-proxy` with identity injected by nginx headers (`X-Auth-Email`, `X-Auth-User`, `X-Auth-Preferred-Username`).

## Stack choices

- **Backend:** FastAPI + Jinja2 templates for clear structure and low operational overhead.
- **DB:** PostgreSQL with SQL migrations.
- **Frontend:** HTML/CSS + vanilla JS.
- **Downloads:** X-Accel-Redirect for secure, authenticated file delivery.

## Folder layout

```
/apphub
  app/                # FastAPI app and templates
  db/                 # migrations + seed data
  nginx/              # minimal nginx delta snippet
  storage/            # uploaded files (files/, media/)
  systemd/            # systemd unit
  tools/              # migration/seed helpers
  .env.example
  requirements.txt
```

## Ubuntu installation (copy/paste)

### 1) Install runtime + dependencies

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql postgresql-contrib nginx
```

### 2) Create AppHub directory

```bash
sudo mkdir -p /var/www/apphub
sudo chown -R $USER:$USER /var/www/apphub
```

### 3) Copy code into place

```bash
rsync -av ./apphub/ /var/www/apphub/
```

### 4) Create virtualenv + install Python packages

```bash
cd /var/www/apphub
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 5) Create Postgres DB + user

```bash
sudo -u postgres psql <<'SQL'
CREATE USER apphub WITH PASSWORD 'apphub';
CREATE DATABASE apphub OWNER apphub;
GRANT ALL PRIVILEGES ON DATABASE apphub TO apphub;
SQL
```

### 6) Configure environment

```bash
cp .env.example .env
nano .env
```

Update:
- `SECRET_KEY`
- `DATABASE_URL`
- `APP_URL`
- `STORAGE_ROOT=/var/www/apphub/storage`

### 7) Run migrations + seed sample data

```bash
./venv/bin/python -m tools.migrate
psql "$DATABASE_URL" -f db/seed.sql
./venv/bin/python -m tools.seed_files
```

### 8) Set storage permissions

```bash
sudo mkdir -p /var/www/apphub/storage/{files,media}
sudo chown -R www-data:www-data /var/www/apphub/storage
sudo chmod -R 750 /var/www/apphub/storage
```

### 9) Configure systemd

```bash
sudo cp systemd/apphub.service /etc/systemd/system/apphub.service
sudo systemctl daemon-reload
sudo systemctl enable --now apphub.service
```

### 10) Add nginx delta

Append the contents of `nginx/apphub.nginx.delta.conf` inside your existing server block and reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Security & identity model

- **Identity source:** `X-Auth-Email` injected by nginx and derived from `oauth2-proxy` via `auth_request`.
- **Header spoofing protection:** nginx clears incoming `X-Auth-*` headers and re-injects trusted values only from the auth response (see the delta config).
- **Just-in-time provisioning:** New users are auto-created as `viewer` on their first request.
- **RBAC:** `admin`, `editor`, `viewer`.
- **CSRF protection:** double-submit cookie (cookie + form/headers).
- **Secure output:** Jinja2 auto-escapes HTML templates.

### CSP guidance

Recommended baseline CSP (tune to your environment):

```
Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'";
```

### Rate limiting guidance

At nginx:
```
limit_req_zone $binary_remote_addr zone=apphub_admin:10m rate=10r/s;
location /apphub/admin/ {
  limit_req zone=apphub_admin burst=20 nodelay;
}
location /apphub/admin/files/upload {
  limit_req zone=apphub_admin burst=5 nodelay;
}
```

### Upload security

- Files are stored in `/var/www/apphub/storage` and served by nginx via `X-Accel-Redirect`.
- File extension, size, and MIME are validated on upload.
- Optional ClamAV integration is supported via `CLAMAV_ENABLED=true` and a local clamd socket.

## Audit logging

Every admin write action stores actor email, action, entity, JSON before/after, timestamp, and IP. Use `tools/rotate_audit_prune.sql` to prune older logs:

```bash
psql "$DATABASE_URL" -f tools/rotate_audit_prune.sql
```

## Backups

- Database: nightly `pg_dump`.
- Files/media: nightly `rsync` or `tar` of `/var/www/apphub/storage`.

Example:
```bash
pg_dump "$DATABASE_URL" | gzip > /var/backups/apphub-db-$(date +%F).sql.gz
rsync -a /var/www/apphub/storage /var/backups/apphub-storage
```

## Logs & operations

- Service logs: `journalctl -u apphub.service -f`
- Update: pull new code, install deps, run migrations, restart service.

## Notes on /apphub/ subpath

The FastAPI app uses `APPHUB_ROOT=/apphub` as its `root_path`, so all templates and static assets are generated with the correct subpath.
