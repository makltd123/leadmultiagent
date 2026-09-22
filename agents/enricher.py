import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from config import nvidia_client, NVIDIA_MODEL

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)

SUMMARY_SYSTEM_PROMPT = """Ты — аналитик B2B-лидов. На основе собранных данных о пользователе напиши краткое резюме.
Отвечай ТОЛЬКО валидным JSON без пояснений."""

SUMMARY_PROMPT_TEMPLATE = """Данные о пользователе:
Имя: {name}
Username: {username}
Bio: {bio}
Последние сообщения в чате: {recent_messages}
Сайт: {website_text}

Сформируй JSON:
{{
  "company": "предположительное название компании или null",
  "role": "предположительная должность или null",
  "email": "email если найден или null",
  "summary": "2-3 предложения: кто этот человек и почему он потенциальный клиент"
}}"""


def _fetch_website(url: str) -> str:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        text = resp.text[:3000]
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1000]
    except Exception:
        return ""


async def enrich(sender_id: int, message, client) -> dict:
    result = {
        "name": None, "username": None, "bio": None,
        "company": None, "role": None, "website": None,
        "email": None, "context": None, "summary": None,
    }

    try:
        user = await client.get_users(sender_id)
        result["name"] = f"{user.first_name or ''} {user.last_name or ''}".strip()
        result["username"] = f"@{user.username}" if user.username else None
        result["bio"] = user.bio or None

        url_match = re.search(r"https?://\S+|\b[\w-]+\.\w{2,}\b", user.bio or "")
        website_url = url_match.group(0) if url_match else None
        result["website"] = website_url

        email_match = re.search(r"[\w.+-]+@[\w-]+\.\w+", user.bio or "")
        result["email"] = email_match.group(0) if email_match else None
    except Exception as e:
        logger.exception("Enricher: ошибка получения профиля %d", sender_id)

    recent_messages_text = ""
    try:
        chat_id = message.chat.id
        msgs = []
        async for msg in client.get_chat_history(chat_id, limit=100):
            if msg.from_user and msg.from_user.id == sender_id and msg.text:
                msgs.append(msg.text[:200])
                if len(msgs) >= 20:
                    break
        recent_messages_text = "\n".join(msgs)
        result["context"] = recent_messages_text[:500] if recent_messages_text else None
    except Exception as e:
        logger.exception("Enricher: ошибка получения истории сообщений")

    website_text = ""
    if result["website"]:
        try:
            website_text = await asyncio.get_event_loop().run_in_executor(
                _executor, _fetch_website, result["website"]
            )
        except Exception:
            pass

    try:
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            name=result["name"] or "",
            username=result["username"] or "",
            bio=result["bio"] or "",
            recent_messages=recent_messages_text[:300],
            website_text=website_text[:300],
        )
        for attempt in range(3):
            try:
                response = await nvidia_client.chat.completions.create(
                    model=NVIDIA_MODEL,
                    messages=[
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=256,
                )
                raw = response.choices[0].message.content.strip()
                summary_data = json.loads(raw)
                result.update(summary_data)
                break
            except json.JSONDecodeError:
                logger.error("Enricher: ошибка парсинга JSON (попытка %d)", attempt + 1)
            except Exception:
                logger.exception("Enricher: ошибка API (попытка %d)", attempt + 1)
            await asyncio.sleep(2 ** attempt)
    except Exception:
        logger.exception("Enricher: ошибка резюме")

    return result
