import aiosqlite
import json
from datetime import datetime
from typing import Optional

DB_PATH = "leads.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS product_config (
                id INTEGER PRIMARY KEY,
                product_description TEXT,
                icp TEXT,
                keywords TEXT,
                signals TEXT,
                anti_signals TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                username TEXT,
                title TEXT,
                description TEXT,
                member_count INTEGER,
                category TEXT,
                city TEXT,
                is_active INTEGER DEFAULT 1,
                joined_at TEXT,
                last_message_at TEXT,
                messages_per_day INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                message_id INTEGER,
                chat_id INTEGER,
                chat_title TEXT,
                sender_id INTEGER,
                sender_username TEXT,
                sender_name TEXT,
                message_text TEXT,
                message_url TEXT,
                relevance_score REAL,
                relevance_reason TEXT,
                enrichment TEXT,
                draft_response TEXT,
                status TEXT DEFAULT 'new',
                notified_at TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_signals (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                message_text TEXT,
                keywords_matched TEXT,
                created_at TEXT
            )
        """)
        await db.commit()


async def save_product_config(data: dict) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute("SELECT id FROM product_config LIMIT 1")
        row = await existing.fetchone()
        if row:
            await db.execute("""
                UPDATE product_config SET
                    product_description=?, icp=?, keywords=?, signals=?,
                    anti_signals=?, updated_at=?
                WHERE id=?
            """, (
                data.get("product_description"),
                json.dumps(data.get("icp", ""), ensure_ascii=False),
                json.dumps(data.get("keywords", []), ensure_ascii=False),
                json.dumps(data.get("intent_signals", []), ensure_ascii=False),
                json.dumps(data.get("anti_signals", []), ensure_ascii=False),
                now,
                row[0],
            ))
        else:
            await db.execute("""
                INSERT INTO product_config
                    (product_description, icp, keywords, signals, anti_signals, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("product_description"),
                json.dumps(data.get("icp", ""), ensure_ascii=False),
                json.dumps(data.get("keywords", []), ensure_ascii=False),
                json.dumps(data.get("intent_signals", []), ensure_ascii=False),
                json.dumps(data.get("anti_signals", []), ensure_ascii=False),
                now, now,
            ))
        await db.commit()


async def load_product_config() -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM product_config LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "product_description": row["product_description"],
            "icp": json.loads(row["icp"] or "{}"),
            "keywords": json.loads(row["keywords"] or "[]"),
            "intent_signals": json.loads(row["signals"] or "[]"),
            "anti_signals": json.loads(row["anti_signals"] or "[]"),
        }


async def save_chat(data: dict) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO chats
                (chat_id, username, title, description, member_count, category, city, joined_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["chat_id"], data.get("username"), data.get("title"),
            data.get("description"), data.get("member_count"),
            data.get("category"), data.get("city"), now,
        ))
        await db.commit()


async def chat_exists(chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM chats WHERE chat_id=?", (chat_id,))
        return await cursor.fetchone() is not None


async def get_all_active_chats() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM chats WHERE is_active=1")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_chat_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM chats WHERE is_active=1")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def save_lead(data: dict) -> int:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO leads
                (message_id, chat_id, chat_title, sender_id, sender_username,
                 sender_name, message_text, message_url, relevance_score,
                 relevance_reason, enrichment, draft_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("message_id"), data.get("chat_id"), data.get("chat_title"),
            data.get("sender_id"), data.get("sender_username"), data.get("sender_name"),
            data.get("message_text"), data.get("message_url"),
            data.get("relevance_score"), data.get("relevance_reason"),
            json.dumps(data.get("enrichment", {}), ensure_ascii=False),
            data.get("draft_response"), now,
        ))
        await db.commit()
        return cursor.lastrowid


async def update_lead_status(lead_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE leads SET status=? WHERE id=?", (status, lead_id)
        )
        await db.commit()


async def mark_lead_notified(lead_id: int) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE leads SET status='notified', notified_at=? WHERE id=?", (now, lead_id)
        )
        await db.commit()


async def get_recent_leads(n: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (n,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_lead_by_id(lead_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM leads WHERE id=?", (lead_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_leads_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        today = datetime.utcnow().date().isoformat()
        cursor = await db.execute(
            "SELECT COUNT(*) FROM leads WHERE DATE(created_at)=?", (today,)
        )
        today_count = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM leads WHERE created_at >= datetime('now', '-7 days')"
        )
        week_count = (await cursor.fetchone())[0]
        return {"today": today_count, "week": week_count}


async def save_market_signal(data: dict) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO market_signals (chat_id, message_text, keywords_matched, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            data.get("chat_id"),
            data.get("message_text"),
            json.dumps(data.get("keywords_matched", []), ensure_ascii=False),
            now,
        ))
        await db.commit()


async def get_signals_last_7_days() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM market_signals WHERE created_at >= datetime('now', '-7 days')"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
