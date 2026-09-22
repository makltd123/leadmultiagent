import asyncio
import logging
import random
import re
import time
from datetime import datetime, timezone, timedelta

from pyrogram.raw import functions as raw_functions

from config import groq_client, GROQ_MODEL, MAX_CHATS
from database import save_chat, chat_exists, get_chat_count

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "бизнес", "предприниматели", "маркетинг", "продажи", "логистика",
    "строительство", "IT бизнес", "финансы", "HR", "производство",
    "ритейл", "автоматизация бизнеса", "CRM", "1С", "бухгалтерия",
    "юристы бизнес", "стартап", "e-commerce", "интернет магазин",
    "поставщики", "тендеры", "оптовая торговля", "франшиза",
    "управление персоналом", "реклама", "SEO", "SMM",
    "медицина бизнес", "клиника", "юридические услуги",
    "аутсорсинг", "IT решения", "цифровизация",
]

JOINS_PER_HOUR = 50
_join_timestamps: list[float] = []


def _can_join() -> bool:
    now = time.time()
    cutoff = now - 3600
    global _join_timestamps
    _join_timestamps = [t for t in _join_timestamps if t > cutoff]
    return len(_join_timestamps) < JOINS_PER_HOUR


def _record_join() -> None:
    _join_timestamps.append(time.time())


async def _categorize_chat(title: str, description: str) -> str:
    try:
        response = await groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": (
                f"Определи одним словом категорию бизнес-чата.\n"
                f"Название: {title}\nОписание: {description[:200]}\n\n"
                f"Варианты: IT, логистика, строительство, ритейл, финансы, HR, производство, "
                f"маркетинг, продажи, медицина, юристы, общий_бизнес\n"
                f"Ответь только одним словом из списка."
            )}],
            temperature=0,
            max_tokens=10,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "общий_бизнес"


async def _try_add_chat(client, chat) -> bool:
    try:
        chat_id = chat.id

        if await chat_exists(chat_id):
            return False

        if not hasattr(chat, 'members_count') or not chat.members_count:
            return False

        if chat.members_count < 300:
            return False

        if not hasattr(chat, 'type') or chat.type.name not in ("GROUP", "SUPERGROUP"):
            return False

        if not _can_join():
            logger.info("Scout: лимит вступлений, жду 60 сек...")
            await asyncio.sleep(60)

        username = getattr(chat, 'username', None)
        title = getattr(chat, 'title', '') or ''

        try:
            if username:
                await client.join_chat(username)
            else:
                await client.join_chat(chat_id)
        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err:
                wait = int(''.join(filter(str.isdigit, err.split("FLOOD_WAIT_")[-1][:5])) or "30")
                logger.info("Scout: flood wait %d сек", wait)
                await asyncio.sleep(wait + 2)
            return False

        _record_join()

        category = await _categorize_chat(title, getattr(chat, 'description', '') or '')
        await save_chat({
            "chat_id": chat_id,
            "username": username,
            "title": title,
            "description": getattr(chat, 'description', None),
            "member_count": chat.members_count,
            "category": category,
            "city": None,
        })
        logger.info("Scout: вступил в '%s' (%d участников, %s)", title, chat.members_count, category)

        await asyncio.sleep(random.uniform(30, 60))
        return True

    except Exception as e:
        logger.error("Scout: ошибка добавления чата: %s", e)
        return False


async def _try_add_chat_by_username(client, username: str) -> None:
    try:
        if await get_chat_count() >= MAX_CHATS:
            return
        await asyncio.sleep(random.uniform(8, 15))
        chat = await client.get_chat(username)

        class FakeChat:
            pass

        fake = FakeChat()
        fake.id = chat.id
        fake.username = username
        fake.title = getattr(chat, 'title', '')
        fake.description = getattr(chat, 'description', None)
        fake.members_count = getattr(chat, 'members_count', 0) or 0
        fake.type = type('T', (), {'name': 'SUPERGROUP'})()
        await _try_add_chat(client, fake)
    except Exception:
        pass


async def run(client) -> None:
    current_count = await get_chat_count()
    if current_count >= MAX_CHATS:
        logger.info("Scout: лимит чатов достигнут (%d)", current_count)
        return

    logger.info("Scout: начинаю поиск чатов (текущих: %d)", current_count)
    joined = 0

    # Сначала пробуем известные username'ы из файла
    try:
        with open("tgstat_chats.txt", encoding="utf-8") as f:
            known = [line.strip() for line in f if line.strip()]
        logger.info("Scout: загружено %d username'ов из tgstat_chats.txt", len(known))
        for username in known:
            if await get_chat_count() >= MAX_CHATS:
                break
            try:
                await asyncio.sleep(random.uniform(10, 20))
                chat = await client.get_chat(username)
                class FakeChat:
                    pass
                fake = FakeChat()
                fake.id = chat.id
                fake.username = username
                fake.title = chat.title
                fake.description = getattr(chat, 'description', None)
                fake.members_count = getattr(chat, 'members_count', 0) or 0
                fake.type = type('T', (), {'name': 'SUPERGROUP'})()
                success = await _try_add_chat(client, fake)
                if success:
                    joined += 1
            except Exception as e:
                err = str(e)
                if "FLOOD_WAIT" in err:
                    try:
                        wait = int(re.search(r'FLOOD_WAIT_(\d+)', err).group(1))
                    except Exception:
                        wait = 60
                    logger.info("Scout: flood wait %d сек, жду...", wait)
                    await asyncio.sleep(wait + 5)
    except FileNotFoundError:
        pass

    for query in SEARCH_QUERIES:
        if await get_chat_count() >= MAX_CHATS:
            break

        try:
            logger.info("Scout: ищу по запросу '%s'", query)
            await asyncio.sleep(random.uniform(2, 4))

            result = await client.invoke(
                raw_functions.contacts.Search(q=query, limit=50)
            )

            chats = {c.id: c for c in result.chats}

            for peer in result.my_results + result.results:
                if await get_chat_count() >= MAX_CHATS:
                    break

                peer_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None)
                if not peer_id:
                    continue

                raw_chat = chats.get(peer_id)
                if not raw_chat:
                    continue

                if not getattr(raw_chat, 'megagroup', False) and not getattr(raw_chat, 'gigagroup', False):
                    if hasattr(raw_chat, 'broadcast') and raw_chat.broadcast:
                        continue

                members = getattr(raw_chat, 'participants_count', 0) or 0
                if members < 300:
                    continue

                username = getattr(raw_chat, 'username', None)
                title = getattr(raw_chat, 'title', '') or ''

                class FakeChat:
                    pass

                fake = FakeChat()
                fake.id = -1000000000000 - peer_id if hasattr(peer, 'channel_id') else -peer_id
                fake.username = username
                fake.title = title
                fake.description = None
                fake.members_count = members
                fake.type = type('T', (), {'name': 'SUPERGROUP'})()

                success = await _try_add_chat(client, fake)
                if success:
                    joined += 1

        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err:
                wait = int(''.join(filter(str.isdigit, err.split("FLOOD_WAIT_")[-1][:5])) or "30")
                logger.info("Scout: flood wait %d сек при поиске", wait)
                await asyncio.sleep(wait + 2)
            else:
                logger.error("Scout: ошибка поиска '%s': %s", query, e)

    logger.info("Scout: завершён, вступил в %d новых чатов", joined)
