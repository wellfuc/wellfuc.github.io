INSERT INTO categories (name, slug, sort_order) VALUES
('Productivity', 'productivity', 1),
('Engineering', 'engineering', 2),
('People Ops', 'people-ops', 3),
('Finance', 'finance', 4),
('Security', 'security', 5),
('Design', 'design', 6);

INSERT INTO apps (name, slug, type, description, status, owner_team, support_contact, web_url, tags, featured, created_at, updated_at)
VALUES
('Launchpad', 'launchpad', 'web', 'Unified launch surface for internal tooling.', 'active', 'IT Ops', 'it@example.com', 'https://launchpad.internal', ARRAY['launcher','portal'], true, NOW(), NOW()),
('Pulse Metrics', 'pulse-metrics', 'web', 'Executive dashboards and KPI storytelling.', 'active', 'Analytics', 'analytics@example.com', 'https://pulse.internal', ARRAY['metrics','dashboard'], true, NOW(), NOW()),
('Relay Desktop', 'relay-desktop', 'desktop', 'Secure chat client for staff communications.', 'active', 'IT Ops', 'it@example.com', NULL, ARRAY['chat','desktop'], false, NOW(), NOW()),
('Atlas Deploy', 'atlas-deploy', 'web', 'Deployment pipeline status and approvals.', 'active', 'Platform', 'platform@example.com', 'https://deploy.internal', ARRAY['devops','release'], false, NOW(), NOW()),
('Nimbus HR', 'nimbus-hr', 'web', 'HR self-service for benefits and onboarding.', 'active', 'People Ops', 'people@example.com', 'https://hr.internal', ARRAY['hr','benefits'], false, NOW(), NOW()),
('LedgerDesk', 'ledgerdesk', 'both', 'Finance reporting and reconciliations suite.', 'active', 'Finance', 'finance@example.com', 'https://ledger.internal', ARRAY['finance','reporting'], true, NOW(), NOW()),
('PatchGuard', 'patchguard', 'web', 'Patch compliance reporting and tracking.', 'active', 'Security', 'security@example.com', 'https://patchguard.internal', ARRAY['security','patching'], false, NOW(), NOW()),
('SketchFlow', 'sketchflow', 'desktop', 'Design prototype handoff tool.', 'maintenance', 'Design', 'design@example.com', NULL, ARRAY['design','prototype'], false, NOW(), NOW()),
('Fleet Ops', 'fleet-ops', 'web', 'Device inventory and lifecycle management.', 'active', 'IT Ops', 'it@example.com', 'https://fleet.internal', ARRAY['devices','inventory'], false, NOW(), NOW()),
('OnCall Compass', 'oncall-compass', 'web', 'Escalation policies and on-call rotations.', 'active', 'SRE', 'sre@example.com', 'https://oncall.internal', ARRAY['oncall','incident'], false, NOW(), NOW());

INSERT INTO app_categories (app_id, category_id)
SELECT a.id, c.id
FROM apps a
JOIN categories c ON (
  (a.slug IN ('launchpad','fleet-ops') AND c.slug = 'productivity') OR
  (a.slug IN ('atlas-deploy','oncall-compass') AND c.slug = 'engineering') OR
  (a.slug IN ('nimbus-hr') AND c.slug = 'people-ops') OR
  (a.slug IN ('ledgerdesk') AND c.slug = 'finance') OR
  (a.slug IN ('patchguard') AND c.slug = 'security') OR
  (a.slug IN ('sketchflow') AND c.slug = 'design')
);

INSERT INTO releases (app_id, version, release_date, notes, changelog, created_at)
SELECT id, '1.0.0', NOW() - INTERVAL '7 days', 'Initial release.', 'Initial release notes.', NOW() FROM apps;

INSERT INTO releases (app_id, version, release_date, notes, changelog, created_at)
SELECT id, '1.1.0', NOW() - INTERVAL '1 day', 'Minor improvements and stability fixes.', 'Bug fixes and minor improvements.', NOW() FROM apps WHERE slug IN ('launchpad','ledgerdesk','fleet-ops');

INSERT INTO files (release_id, platform, arch, filename, stored_path, size_bytes, sha256, mime_type, download_count, created_at)
SELECT r.id, 'windows', 'x64', a.slug || '-setup.exe', '/var/www/apphub/storage/files/' || a.slug || '-setup.exe', 120000000, md5(random()::text), 'application/octet-stream', 0, NOW()
FROM releases r
JOIN apps a ON a.id = r.app_id
WHERE a.type IN ('desktop','both');

INSERT INTO media (app_id, type, stored_path, caption, sort_order)
SELECT id, 'screenshot', '/var/www/apphub/storage/media/' || slug || '-hero.png', 'Main dashboard view', 1 FROM apps;

INSERT INTO announcements (title, body, starts_at, ends_at, priority, created_at)
VALUES
('New AppHub launch', 'Welcome to the new internal AppHub. Browse, download, and launch tools in one place.', NOW() - INTERVAL '1 day', NOW() + INTERVAL '14 days', 10, NOW());
