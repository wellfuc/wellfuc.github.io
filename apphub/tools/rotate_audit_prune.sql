DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL '180 days';
