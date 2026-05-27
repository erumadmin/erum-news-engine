"""Optional persistence for editorial pipeline entities (MariaDB)."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional


def ensure_editorial_tables(execute: Callable[[str], None]) -> None:
    execute(
        """
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    execute(
        """
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    execute(
        """
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    execute(
        """
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def insert_raw_source(cur, raw: dict[str, Any], research: dict[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO raw_sources (
            source_type, source_url, source_title, source_body,
            source_published_at, raw_html, image_candidates_json, source_hash
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
        """,
        (
            raw.get("source_type", ""),
            raw.get("url", ""),
            raw.get("title", ""),
            raw.get("body", ""),
            raw.get("source_published_at"),
            raw.get("raw_html", ""),
            json.dumps([raw.get("image")] if raw.get("image") else [], ensure_ascii=False),
            raw.get("source_hash", ""),
        ),
    )
    raw_id = cur.lastrowid
    for ev in research.get("evidence", []):
        cur.execute(
            """
            INSERT INTO source_evidence (
                raw_source_id, evidence_type, url, title, body_excerpt,
                reliability_rank, collected_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                raw_id,
                ev.get("evidence_type", ""),
                ev.get("url", ""),
                ev.get("title", ""),
                ev.get("body_excerpt", ""),
                ev.get("reliability_rank", 0),
            ),
        )
    return raw_id


def insert_research_packet(
    cur,
    raw_source_id: int,
    site: str,
    packet: dict[str, Any],
    publish_grade: str,
    placement: Any,
) -> int:
    cur.execute(
        """
        INSERT INTO research_packets (
            raw_source_id, assigned_site, packet_json, publish_grade,
            placement_hint, image_asset_tier
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            raw_source_id,
            site,
            json.dumps(packet, ensure_ascii=False),
            publish_grade,
            placement.slot if hasattr(placement, "slot") else packet.get("placement_hint"),
            packet.get("image_asset_tier", "none"),
        ),
    )
    return cur.lastrowid
