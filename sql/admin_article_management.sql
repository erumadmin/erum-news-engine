-- Admin article management schema
-- Target: MariaDB / MySQL-compatible

ALTER TABLE published_articles
    ADD COLUMN source_published_at DATETIME DEFAULT NULL AFTER media;

ALTER TABLE article_attempts
    ADD COLUMN source_published_at DATETIME DEFAULT NULL AFTER media;

CREATE TABLE IF NOT EXISTS article_rules (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    url_id VARCHAR(512) DEFAULT NULL,
    source_url VARCHAR(2048) DEFAULT NULL,
    title_hash CHAR(64) DEFAULT NULL,
    rule_type VARCHAR(20) NOT NULL,
    expires_at DATETIME DEFAULT NULL,
    note TEXT,
    created_by VARCHAR(100) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_article_rules_url_id (url_id),
    KEY idx_article_rules_title_hash (title_hash),
    KEY idx_article_rules_type_expires (rule_type, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_url_id VARCHAR(512) DEFAULT NULL,
    before_state LONGTEXT DEFAULT NULL,
    after_state LONGTEXT DEFAULT NULL,
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_logs_target_url_id (target_url_id),
    KEY idx_audit_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

