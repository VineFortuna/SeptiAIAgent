from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _get_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    # Render provides postgres:// but psycopg2 requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def get_connection():
    """Return a psycopg2 connection, or None if DATABASE_URL is not set."""
    url = _get_url()
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except Exception as exc:
        logger.warning("Could not connect to database: %s", exc)
        return None


def init_db() -> bool:
    """Create the leads table if it does not exist. Returns True if DB is available."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    phone        TEXT PRIMARY KEY,
                    stage        TEXT NOT NULL DEFAULT 'greeted',
                    lang         TEXT NOT NULL DEFAULT 'en',
                    created_at   TEXT,
                    updated_at   TEXT,
                    data         JSONB NOT NULL DEFAULT '{}'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    phone      TEXT PRIMARY KEY,
                    history    JSONB NOT NULL DEFAULT '[]',
                    updated_at TEXT
                )
            """)
        conn.commit()
        logger.info("Database initialised successfully")
        return True
    except Exception as exc:
        logger.warning("Could not initialise database: %s", exc)
        return False
    finally:
        conn.close()


def load_leads() -> dict[str, Any]:
    """Load all leads from the database. Returns empty dict on failure."""
    conn = get_connection()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT phone, data FROM leads")
            rows = cur.fetchall()
        result: dict[str, Any] = {}
        for phone, data in rows:
            lead = data if isinstance(data, dict) else json.loads(data)
            lead["phone"] = phone
            result[phone] = lead
        return result
    except Exception as exc:
        logger.warning("Could not load leads from database: %s", exc)
        return {}
    finally:
        conn.close()


def save_lead(phone: str, lead: dict[str, Any]) -> bool:
    """Upsert a single lead. Returns True on success."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (phone, stage, lang, created_at, updated_at, data)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone) DO UPDATE SET
                    stage      = EXCLUDED.stage,
                    lang       = EXCLUDED.lang,
                    updated_at = EXCLUDED.updated_at,
                    data       = EXCLUDED.data
                """,
                (
                    phone,
                    lead.get("stage", "greeted"),
                    lead.get("lang", "en"),
                    lead.get("created_at"),
                    lead.get("updated_at"),
                    json.dumps(lead, ensure_ascii=False),
                ),
            )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not save lead %s: %s", phone, exc)
        return False
    finally:
        conn.close()


def save_all_leads(leads: dict[str, Any]) -> bool:
    """Upsert all leads in a single transaction. Returns True on success."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            for phone, lead in leads.items():
                cur.execute(
                    """
                    INSERT INTO leads (phone, stage, lang, created_at, updated_at, data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (phone) DO UPDATE SET
                        stage      = EXCLUDED.stage,
                        lang       = EXCLUDED.lang,
                        updated_at = EXCLUDED.updated_at,
                        data       = EXCLUDED.data
                    """,
                    (
                        phone,
                        lead.get("stage", "greeted"),
                        lead.get("lang", "en"),
                        lead.get("created_at"),
                        lead.get("updated_at"),
                        json.dumps(lead, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not bulk-save leads: %s", exc)
        return False
    finally:
        conn.close()


def delete_all_leads() -> bool:
    """Wipe every lead from the database. Returns True on success."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM leads")
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not delete leads: %s", exc)
        return False
    finally:
        conn.close()


def load_history(phone: str) -> list[dict[str, str]]:
    """Load conversation history for a specific phone number. Returns empty list on failure."""
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT history FROM conversation_history WHERE phone = %s", (phone,))
            row = cur.fetchone()
        if not row:
            return []
        history = row[0] if isinstance(row[0], list) else json.loads(row[0])
        return history
    except Exception as exc:
        logger.warning("Could not load history for %s: %s", phone, exc)
        return []
    finally:
        conn.close()


def save_history(phone: str, history: list) -> bool:
    """Upsert conversation history for a phone number. Returns True on success."""
    conn = get_connection()
    if not conn:
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_history (phone, history, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (phone) DO UPDATE SET
                    history    = EXCLUDED.history,
                    updated_at = EXCLUDED.updated_at
                """,
                (phone, json.dumps(history, ensure_ascii=False), now),
            )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not save history for %s: %s", phone, exc)
        return False
    finally:
        conn.close()


def delete_all_history() -> bool:
    """Wipe all conversation history from the database. Returns True on success."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversation_history")
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Could not delete history: %s", exc)
        return False
    finally:
        conn.close()
