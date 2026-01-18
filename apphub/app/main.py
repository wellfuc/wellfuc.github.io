from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.audit import log_action
from app.auth import get_identity
from app.config import settings
from app.csrf import csrf_token, set_csrf_cookie, validate_csrf
from app.db import get_cursor
from app.rbac import require_role
from app.uploads import save_upload
from app.util import get_client_ip, parse_tags, slugify

app = FastAPI(root_path=settings.apphub_root)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        await validate_csrf(request)
    response = await call_next(request)
    token = csrf_token(request)
    set_csrf_cookie(response, token)
    return response


@app.get("/", response_class=HTMLResponse)
def portal_home(request: Request):
    user = get_identity(request)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, MAX(r.release_date) AS latest_release
            FROM apps a
            LEFT JOIN releases r ON r.app_id = a.id AND r.deleted_at IS NULL
            WHERE a.deleted_at IS NULL AND a.featured = TRUE
            GROUP BY a.id
            ORDER BY latest_release DESC NULLS LAST
            LIMIT 6
            """
        )
        featured_apps = cur.fetchall()
        cur.execute(
            """
            SELECT a.*, MAX(r.release_date) AS latest_release
            FROM apps a
            LEFT JOIN releases r ON r.app_id = a.id AND r.deleted_at IS NULL
            WHERE a.deleted_at IS NULL
            GROUP BY a.id
            ORDER BY latest_release DESC NULLS LAST
            LIMIT 6
            """
        )
        recent_apps = cur.fetchall()
        cur.execute("SELECT * FROM categories ORDER BY sort_order, name")
        categories = cur.fetchall()
        cur.execute(
            "SELECT * FROM announcements WHERE (starts_at IS NULL OR starts_at <= NOW()) AND (ends_at IS NULL OR ends_at >= NOW()) ORDER BY priority DESC, created_at DESC"
        )
        announcements = cur.fetchall()
    return templates.TemplateResponse(
        "portal/home.html",
        {
            "request": request,
            "user": user,
            "featured_apps": featured_apps,
            "recent_apps": recent_apps,
            "categories": categories,
            "announcements": announcements,
            "csrf_token": csrf_token(request),
        },
    )


@app.get("/apps", response_class=HTMLResponse)
def apps_list(request: Request, q: str | None = None, category: str | None = None):
    user = get_identity(request)
    query = "%" + (q or "") + "%"
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT a.*
            FROM apps a
            LEFT JOIN app_categories ac ON ac.app_id = a.id
            LEFT JOIN categories c ON c.id = ac.category_id
            WHERE a.deleted_at IS NULL
              AND (a.name ILIKE %s OR a.description ILIKE %s OR %s = ANY(a.tags))
              AND (%s IS NULL OR c.slug = %s)
            ORDER BY a.featured DESC, a.updated_at DESC
            """,
            (query, query, q or "", category, category),
        )
        apps = cur.fetchall()
        cur.execute("SELECT * FROM categories ORDER BY sort_order, name")
        categories = cur.fetchall()
    return templates.TemplateResponse(
        "portal/apps_list.html",
        {
            "request": request,
            "user": user,
            "apps": apps,
            "categories": categories,
            "query": q or "",
            "selected_category": category or "",
            "csrf_token": csrf_token(request),
        },
    )


@app.get("/apps/{slug}", response_class=HTMLResponse)
def app_detail(request: Request, slug: str):
    user = get_identity(request)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM apps WHERE slug = %s AND deleted_at IS NULL", (slug,))
        app_row = cur.fetchone()
        if not app_row:
            raise HTTPException(status_code=404)
        cur.execute(
            "SELECT * FROM releases WHERE app_id = %s AND deleted_at IS NULL ORDER BY release_date DESC",
            (app_row["id"],),
        )
        releases = cur.fetchall()
        cur.execute("SELECT * FROM media WHERE app_id = %s ORDER BY sort_order", (app_row["id"],))
        media = cur.fetchall()
        cur.execute(
            """
            SELECT f.*, r.version
            FROM files f
            JOIN releases r ON r.id = f.release_id
            WHERE r.app_id = %s AND f.deleted_at IS NULL AND r.deleted_at IS NULL
            ORDER BY r.release_date DESC, f.created_at DESC
            """,
            (app_row["id"],),
        )
        files = cur.fetchall()
    return templates.TemplateResponse(
        "portal/app_detail.html",
        {
            "request": request,
            "user": user,
            "app": app_row,
            "releases": releases,
            "media": media,
            "files": files,
            "csrf_token": csrf_token(request),
        },
    )


@app.get("/categories/{slug}", response_class=HTMLResponse)
def category_detail(request: Request, slug: str):
    user = get_identity(request)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM categories WHERE slug = %s", (slug,))
        category = cur.fetchone()
        if not category:
            raise HTTPException(status_code=404)
        cur.execute(
            """
            SELECT a.*
            FROM apps a
            JOIN app_categories ac ON ac.app_id = a.id
            WHERE ac.category_id = %s AND a.deleted_at IS NULL
            ORDER BY a.updated_at DESC
            """,
            (category["id"],),
        )
        apps = cur.fetchall()
    return templates.TemplateResponse(
        "portal/category.html",
        {
            "request": request,
            "user": user,
            "category": category,
            "apps": apps,
            "csrf_token": csrf_token(request),
        },
    )


@app.get("/download/{file_id}")
def download_file(request: Request, file_id: int):
    user = get_identity(request)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.*, r.app_id
            FROM files f
            JOIN releases r ON r.id = f.release_id
            WHERE f.id = %s AND f.deleted_at IS NULL AND r.deleted_at IS NULL
            """,
            (file_id,),
        )
        file_row = cur.fetchone()
        if not file_row:
            raise HTTPException(status_code=404)
        cur.execute("UPDATE files SET download_count = download_count + 1 WHERE id = %s", (file_id,))
    storage_root = Path(settings.storage_root).resolve()
    stored_path = Path(file_row["stored_path"]).resolve()
    if storage_root not in stored_path.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    internal_path = "/apphub_internal/" + str(stored_path.relative_to(storage_root))
    response = Response(status_code=200)
    response.headers["X-Accel-Redirect"] = internal_path
    response.headers["Content-Disposition"] = f"attachment; filename=\"{file_row['filename']}\""
    return response


@app.get("/media/{media_id}")
def media_file(request: Request, media_id: int):
    user = get_identity(request)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM media WHERE id = %s", (media_id,))
        media_row = cur.fetchone()
        if not media_row:
            raise HTTPException(status_code=404)
    storage_root = Path(settings.storage_root).resolve()
    stored_path = Path(media_row["stored_path"]).resolve()
    if storage_root not in stored_path.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    internal_path = "/apphub_internal/" + str(stored_path.relative_to(storage_root))
    response = Response(status_code=200)
    response.headers["X-Accel-Redirect"] = internal_path
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM apps WHERE deleted_at IS NULL")
        app_count = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) AS count FROM releases WHERE deleted_at IS NULL")
        release_count = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) AS count FROM files WHERE deleted_at IS NULL")
        file_count = cur.fetchone()["count"]
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "app_count": app_count,
            "release_count": release_count,
            "file_count": file_count,
            "csrf_token": csrf_token(request),
        },
    )


@app.get("/admin/apps", response_class=HTMLResponse)
def admin_apps(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM apps WHERE deleted_at IS NULL ORDER BY updated_at DESC")
        apps = cur.fetchall()
    return templates.TemplateResponse(
        "admin/apps_list.html",
        {"request": request, "user": user, "apps": apps, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/apps/new", response_class=HTMLResponse)
def admin_app_new(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM categories ORDER BY sort_order, name")
        categories = cur.fetchall()
    return templates.TemplateResponse(
        "admin/app_edit.html",
        {
            "request": request,
            "user": user,
            "app": None,
            "categories": categories,
            "selected_categories": [],
            "csrf_token": csrf_token(request),
        },
    )


@app.post("/admin/apps/new")
def admin_app_create(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(""),
    status: str = Form("active"),
    owner_team: str = Form(""),
    support_contact: str = Form(""),
    web_url: str = Form(""),
    tags: str = Form(""),
    featured: str | None = Form(None),
    categories: list[int] = Form([]),
):
    user = get_identity(request)
    require_role(user, "editor")
    now = datetime.now(timezone.utc)
    slug = slugify(name)
    tag_list = parse_tags(tags)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO apps (name, slug, type, description, status, owner_team, support_contact, web_url, tags, featured, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                slug,
                type,
                description,
                status,
                owner_team,
                support_contact,
                web_url,
                tag_list,
                featured == "on",
                now,
                now,
            ),
        )
        app_id = cur.fetchone()["id"]
        for category_id in categories:
            cur.execute(
                "INSERT INTO app_categories (app_id, category_id) VALUES (%s, %s)",
                (app_id, category_id),
            )
    log_action(
        actor=user,
        action="create",
        entity_type="app",
        entity_id=app_id,
        before=None,
        after={"name": name, "slug": slug},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/apps", status_code=303)


@app.get("/admin/apps/{app_id}", response_class=HTMLResponse)
def admin_app_edit(request: Request, app_id: int):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM apps WHERE id = %s", (app_id,))
        app_row = cur.fetchone()
        if not app_row:
            raise HTTPException(status_code=404)
        cur.execute("SELECT * FROM categories ORDER BY sort_order, name")
        categories = cur.fetchall()
        cur.execute("SELECT category_id FROM app_categories WHERE app_id = %s", (app_id,))
        selected = [row["category_id"] for row in cur.fetchall()]
    return templates.TemplateResponse(
        "admin/app_edit.html",
        {
            "request": request,
            "user": user,
            "app": app_row,
            "categories": categories,
            "selected_categories": selected,
            "csrf_token": csrf_token(request),
        },
    )


@app.post("/admin/apps/{app_id}")
def admin_app_update(
    request: Request,
    app_id: int,
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(""),
    status: str = Form("active"),
    owner_team: str = Form(""),
    support_contact: str = Form(""),
    web_url: str = Form(""),
    tags: str = Form(""),
    featured: str | None = Form(None),
    categories: list[int] = Form([]),
):
    user = get_identity(request)
    require_role(user, "editor")
    now = datetime.now(timezone.utc)
    slug = slugify(name)
    tag_list = parse_tags(tags)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM apps WHERE id = %s", (app_id,))
        before = cur.fetchone()
        cur.execute(
            """
            UPDATE apps
            SET name = %s, slug = %s, type = %s, description = %s, status = %s,
                owner_team = %s, support_contact = %s, web_url = %s, tags = %s, featured = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                name,
                slug,
                type,
                description,
                status,
                owner_team,
                support_contact,
                web_url,
                tag_list,
                featured == "on",
                now,
                app_id,
            ),
        )
        cur.execute("DELETE FROM app_categories WHERE app_id = %s", (app_id,))
        for category_id in categories:
            cur.execute(
                "INSERT INTO app_categories (app_id, category_id) VALUES (%s, %s)",
                (app_id, category_id),
            )
    log_action(
        actor=user,
        action="update",
        entity_type="app",
        entity_id=app_id,
        before=before,
        after={"name": name, "slug": slug},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/apps", status_code=303)


@app.post("/admin/apps/{app_id}/delete")
def admin_app_delete(request: Request, app_id: int):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM apps WHERE id = %s", (app_id,))
        before = cur.fetchone()
        cur.execute("UPDATE apps SET deleted_at = NOW() WHERE id = %s", (app_id,))
    log_action(
        actor=user,
        action="delete",
        entity_type="app",
        entity_id=app_id,
        before=before,
        after=None,
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/apps", status_code=303)


@app.get("/admin/categories", response_class=HTMLResponse)
def admin_categories(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM categories ORDER BY sort_order, name")
        categories = cur.fetchall()
    return templates.TemplateResponse(
        "admin/categories_list.html",
        {"request": request, "user": user, "categories": categories, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/categories/new", response_class=HTMLResponse)
def admin_category_new(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    return templates.TemplateResponse(
        "admin/category_edit.html",
        {"request": request, "user": user, "category": None, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/categories/new")
def admin_category_create(request: Request, name: str = Form(...), sort_order: int = Form(0)):
    user = get_identity(request)
    require_role(user, "editor")
    slug = slugify(name)
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO categories (name, slug, sort_order) VALUES (%s, %s, %s) RETURNING id",
            (name, slug, sort_order),
        )
        category_id = cur.fetchone()["id"]
    log_action(
        actor=user,
        action="create",
        entity_type="category",
        entity_id=category_id,
        before=None,
        after={"name": name},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/categories", status_code=303)


@app.get("/admin/categories/{category_id}", response_class=HTMLResponse)
def admin_category_edit(request: Request, category_id: int):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
        category = cur.fetchone()
        if not category:
            raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "admin/category_edit.html",
        {"request": request, "user": user, "category": category, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/categories/{category_id}")
def admin_category_update(
    request: Request,
    category_id: int,
    name: str = Form(...),
    sort_order: int = Form(0),
):
    user = get_identity(request)
    require_role(user, "editor")
    slug = slugify(name)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
        before = cur.fetchone()
        cur.execute(
            "UPDATE categories SET name = %s, slug = %s, sort_order = %s WHERE id = %s",
            (name, slug, sort_order, category_id),
        )
    log_action(
        actor=user,
        action="update",
        entity_type="category",
        entity_id=category_id,
        before=before,
        after={"name": name},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/categories", status_code=303)


@app.get("/admin/releases", response_class=HTMLResponse)
def admin_releases(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.*, a.name AS app_name
            FROM releases r
            JOIN apps a ON a.id = r.app_id
            WHERE r.deleted_at IS NULL
            ORDER BY r.release_date DESC
            """
        )
        releases = cur.fetchall()
    return templates.TemplateResponse(
        "admin/releases_list.html",
        {"request": request, "user": user, "releases": releases, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/releases/new", response_class=HTMLResponse)
def admin_release_new(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT id, name FROM apps WHERE deleted_at IS NULL ORDER BY name")
        apps = cur.fetchall()
    return templates.TemplateResponse(
        "admin/release_edit.html",
        {"request": request, "user": user, "release": None, "apps": apps, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/releases/new")
def admin_release_create(
    request: Request,
    app_id: int = Form(...),
    version: str = Form(...),
    release_date: str = Form(...),
    notes: str = Form(""),
    changelog: str = Form(""),
):
    user = get_identity(request)
    require_role(user, "editor")
    release_dt = datetime.fromisoformat(release_date)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO releases (app_id, version, release_date, notes, changelog, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (app_id, version, release_dt, notes, changelog, datetime.now(timezone.utc)),
        )
        release_id = cur.fetchone()["id"]
    log_action(
        actor=user,
        action="create",
        entity_type="release",
        entity_id=release_id,
        before=None,
        after={"version": version},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/releases", status_code=303)


@app.get("/admin/releases/{release_id}", response_class=HTMLResponse)
def admin_release_edit(request: Request, release_id: int):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM releases WHERE id = %s", (release_id,))
        release = cur.fetchone()
        if not release:
            raise HTTPException(status_code=404)
        cur.execute("SELECT id, name FROM apps WHERE deleted_at IS NULL ORDER BY name")
        apps = cur.fetchall()
    return templates.TemplateResponse(
        "admin/release_edit.html",
        {"request": request, "user": user, "release": release, "apps": apps, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/releases/{release_id}")
def admin_release_update(
    request: Request,
    release_id: int,
    app_id: int = Form(...),
    version: str = Form(...),
    release_date: str = Form(...),
    notes: str = Form(""),
    changelog: str = Form(""),
):
    user = get_identity(request)
    require_role(user, "editor")
    release_dt = datetime.fromisoformat(release_date)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM releases WHERE id = %s", (release_id,))
        before = cur.fetchone()
        cur.execute(
            """
            UPDATE releases
            SET app_id = %s, version = %s, release_date = %s, notes = %s, changelog = %s
            WHERE id = %s
            """,
            (app_id, version, release_dt, notes, changelog, release_id),
        )
    log_action(
        actor=user,
        action="update",
        entity_type="release",
        entity_id=release_id,
        before=before,
        after={"version": version},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/releases", status_code=303)


@app.post("/admin/releases/{release_id}/delete")
def admin_release_delete(request: Request, release_id: int):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM releases WHERE id = %s", (release_id,))
        before = cur.fetchone()
        cur.execute("UPDATE releases SET deleted_at = NOW() WHERE id = %s", (release_id,))
    log_action(
        actor=user,
        action="delete",
        entity_type="release",
        entity_id=release_id,
        before=before,
        after=None,
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/releases", status_code=303)


@app.get("/admin/files", response_class=HTMLResponse)
def admin_files(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.*, r.version, a.name AS app_name
            FROM files f
            JOIN releases r ON r.id = f.release_id
            JOIN apps a ON a.id = r.app_id
            WHERE f.deleted_at IS NULL
            ORDER BY f.created_at DESC
            """
        )
        files = cur.fetchall()
    return templates.TemplateResponse(
        "admin/files_list.html",
        {"request": request, "user": user, "files": files, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/media", response_class=HTMLResponse)
def admin_media(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT m.*, a.name AS app_name
            FROM media m
            JOIN apps a ON a.id = m.app_id
            ORDER BY m.sort_order, m.id DESC
            """
        )
        media = cur.fetchall()
    return templates.TemplateResponse(
        "admin/media_list.html",
        {"request": request, "user": user, "media": media, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/media/upload", response_class=HTMLResponse)
def admin_media_upload_form(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT id, name FROM apps WHERE deleted_at IS NULL ORDER BY name")
        apps = cur.fetchall()
    return templates.TemplateResponse(
        "admin/media_upload.html",
        {"request": request, "user": user, "apps": apps, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/media/upload")
def admin_media_upload(
    request: Request,
    app_id: int = Form(...),
    type: str = Form(...),
    caption: str = Form(""),
    sort_order: int = Form(0),
    upload: UploadFile = Form(...),
):
    user = get_identity(request)
    require_role(user, "editor")
    result = save_upload(upload, Path(settings.storage_root) / "media", settings.allowed_media_extensions)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO media (app_id, type, stored_path, caption, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (app_id, type, result.stored_path, caption, sort_order),
        )
        media_id = cur.fetchone()["id"]
    log_action(
        actor=user,
        action="create",
        entity_type="media",
        entity_id=media_id,
        before=None,
        after={"filename": result.filename},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/media", status_code=303)


@app.post("/admin/media/{media_id}/delete")
def admin_media_delete(request: Request, media_id: int):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM media WHERE id = %s", (media_id,))
        before = cur.fetchone()
        cur.execute("DELETE FROM media WHERE id = %s", (media_id,))
    log_action(
        actor=user,
        action="delete",
        entity_type="media",
        entity_id=media_id,
        before=before,
        after=None,
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/media", status_code=303)


@app.get("/admin/files/upload", response_class=HTMLResponse)
def admin_file_upload_form(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.version, a.name AS app_name
            FROM releases r
            JOIN apps a ON a.id = r.app_id
            WHERE r.deleted_at IS NULL
            ORDER BY r.release_date DESC
            """
        )
        releases = cur.fetchall()
    return templates.TemplateResponse(
        "admin/file_upload.html",
        {"request": request, "user": user, "releases": releases, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/files/upload")
def admin_file_upload(
    request: Request,
    release_id: int = Form(...),
    platform: str = Form(...),
    arch: str = Form(...),
    upload: UploadFile = Form(...),
):
    user = get_identity(request)
    require_role(user, "editor")
    result = save_upload(upload, Path(settings.storage_root) / "files", settings.allowed_upload_extensions)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO files (release_id, platform, arch, filename, stored_path, size_bytes, sha256, mime_type, download_count, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            RETURNING id
            """,
            (
                release_id,
                platform,
                arch,
                result.filename,
                result.stored_path,
                result.size_bytes,
                result.sha256,
                result.mime_type,
                datetime.now(timezone.utc),
            ),
        )
        file_id = cur.fetchone()["id"]
    log_action(
        actor=user,
        action="create",
        entity_type="file",
        entity_id=file_id,
        before=None,
        after={"filename": result.filename},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/files", status_code=303)


@app.post("/admin/files/{file_id}/delete")
def admin_file_delete(request: Request, file_id: int):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM files WHERE id = %s", (file_id,))
        before = cur.fetchone()
        cur.execute("UPDATE files SET deleted_at = NOW() WHERE id = %s", (file_id,))
    log_action(
        actor=user,
        action="delete",
        entity_type="file",
        entity_id=file_id,
        before=before,
        after=None,
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/files", status_code=303)


@app.get("/admin/announcements", response_class=HTMLResponse)
def admin_announcements(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM announcements ORDER BY priority DESC, created_at DESC")
        announcements = cur.fetchall()
    return templates.TemplateResponse(
        "admin/announcements_list.html",
        {"request": request, "user": user, "announcements": announcements, "csrf_token": csrf_token(request)},
    )


@app.get("/admin/announcements/new", response_class=HTMLResponse)
def admin_announcement_new(request: Request):
    user = get_identity(request)
    require_role(user, "editor")
    return templates.TemplateResponse(
        "admin/announcement_edit.html",
        {"request": request, "user": user, "announcement": None, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/announcements/new")
def admin_announcement_create(
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    starts_at: str | None = Form(None),
    ends_at: str | None = Form(None),
    priority: int = Form(0),
):
    user = get_identity(request)
    require_role(user, "editor")
    starts = datetime.fromisoformat(starts_at) if starts_at else None
    ends = datetime.fromisoformat(ends_at) if ends_at else None
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO announcements (title, body, starts_at, ends_at, priority, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (title, body, starts, ends, priority, datetime.now(timezone.utc)),
        )
        announcement_id = cur.fetchone()["id"]
    log_action(
        actor=user,
        action="create",
        entity_type="announcement",
        entity_id=announcement_id,
        before=None,
        after={"title": title},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/announcements", status_code=303)


@app.get("/admin/announcements/{announcement_id}", response_class=HTMLResponse)
def admin_announcement_edit(request: Request, announcement_id: int):
    user = get_identity(request)
    require_role(user, "editor")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
        announcement = cur.fetchone()
        if not announcement:
            raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "admin/announcement_edit.html",
        {"request": request, "user": user, "announcement": announcement, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/announcements/{announcement_id}")
def admin_announcement_update(
    request: Request,
    announcement_id: int,
    title: str = Form(...),
    body: str = Form(""),
    starts_at: str | None = Form(None),
    ends_at: str | None = Form(None),
    priority: int = Form(0),
):
    user = get_identity(request)
    require_role(user, "editor")
    starts = datetime.fromisoformat(starts_at) if starts_at else None
    ends = datetime.fromisoformat(ends_at) if ends_at else None
    with get_cursor() as cur:
        cur.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
        before = cur.fetchone()
        cur.execute(
            """
            UPDATE announcements
            SET title = %s, body = %s, starts_at = %s, ends_at = %s, priority = %s
            WHERE id = %s
            """,
            (title, body, starts, ends, priority, announcement_id),
        )
    log_action(
        actor=user,
        action="update",
        entity_type="announcement",
        entity_id=announcement_id,
        before=before,
        after={"title": title},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/announcements", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
    return templates.TemplateResponse(
        "admin/users_list.html",
        {"request": request, "user": user, "users": users, "csrf_token": csrf_token(request)},
    )


@app.post("/admin/users/{user_id}/role")
def admin_user_role(request: Request, user_id: int, role: str = Form(...)):
    user = get_identity(request)
    require_role(user, "admin")
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        before = cur.fetchone()
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
    log_action(
        actor=user,
        action="update",
        entity_type="user",
        entity_id=user_id,
        before=before,
        after={"role": role},
        ip=get_client_ip(request),
    )
    return RedirectResponse(f"{settings.apphub_root}/admin/users", status_code=303)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "errors/403.html", {"request": request, "detail": exc.detail}, status_code=403
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse("errors/500.html", {"request": request}, status_code=500)
