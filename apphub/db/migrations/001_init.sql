CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    created_at TIMESTAMPTZ NOT NULL,
    last_login TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS apps (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('web', 'desktop', 'both')),
    description TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'maintenance', 'deprecated')),
    owner_team TEXT,
    support_contact TEXT,
    web_url TEXT,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    featured BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_categories (
    app_id INT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (app_id, category_id)
);

CREATE TABLE IF NOT EXISTS releases (
    id SERIAL PRIMARY KEY,
    app_id INT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    release_date TIMESTAMPTZ NOT NULL,
    notes TEXT,
    changelog TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    release_id INT NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    arch TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    download_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS media (
    id SERIAL PRIMARY KEY,
    app_id INT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('screenshot', 'icon')),
    stored_path TEXT NOT NULL,
    caption TEXT,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    priority INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    actor_email TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INT,
    before_json JSONB,
    after_json JSONB,
    ip TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apps_updated ON apps(updated_at);
CREATE INDEX IF NOT EXISTS idx_apps_featured ON apps(featured);
CREATE INDEX IF NOT EXISTS idx_releases_app ON releases(app_id, release_date DESC);
CREATE INDEX IF NOT EXISTS idx_files_release ON files(release_id);
CREATE INDEX IF NOT EXISTS idx_media_app ON media(app_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_announcements_active ON announcements(starts_at, ends_at);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
