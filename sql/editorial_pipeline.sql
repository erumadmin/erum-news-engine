-- Multi-brand editorial pipeline tables (see design spec 2026-05-16)

CREATE TABLE IF NOT EXISTS raw_sources (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_type VARCHAR(64) NOT NULL,
    source_url VARCHAR(2048) NOT NULL,
    source_title VARCHAR(1000),
    source_body LONGTEXT,
    source_published_at DATETIME DEFAULT NULL,
    raw_html LONGTEXT,
    image_candidates_json LONGTEXT,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_hash CHAR(64) NOT NULL,
    UNIQUE KEY uq_raw_sources_hash (source_hash),
    KEY idx_raw_sources_ingested (ingested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS source_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_source_id BIGINT NOT NULL,
    evidence_type VARCHAR(64),
    url VARCHAR(2048),
    title VARCHAR(1000),
    body_excerpt TEXT,
    published_at DATETIME DEFAULT NULL,
    reliability_rank INT DEFAULT 0,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_source_evidence_raw (raw_source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS research_packets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_source_id BIGINT NOT NULL,
    assigned_site VARCHAR(8) NOT NULL,
    packet_json LONGTEXT NOT NULL,
    publish_grade CHAR(1) NOT NULL,
    placement_hint VARCHAR(32),
    image_asset_tier VARCHAR(32),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_research_packets_raw (raw_source_id),
    KEY idx_research_packets_site (assigned_site)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS article_outputs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    research_packet_id BIGINT,
    site VARCHAR(8) NOT NULL,
    title VARCHAR(1000),
    excerpt TEXT,
    body LONGTEXT,
    qa_json LONGTEXT,
    article_quality_score INT DEFAULT NULL,
    editorial_rank_score INT DEFAULT NULL,
    placement_decision VARCHAR(32),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_article_outputs_packet (research_packet_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
