from datetime import datetime, timezone


def keyword_score(text: str, config: dict) -> int:
    score = 0
    text_lower = text.lower()

    for signal in config.get("intent_signals", []):
        if signal.lower() in text_lower:
            score += 2

    for keyword in config.get("keywords", []):
        if keyword.lower() in text_lower:
            score += 1

    for anti in config.get("anti_signals", []):
        if anti.lower() in text_lower:
            score -= 3

    return score


def is_too_short(text: str) -> bool:
    return len(text.strip()) < 20


def is_old_message(message_date: datetime) -> bool:
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - message_date).total_seconds()
    return age_seconds > 86400  # 24 часа


def passes_prefilter(text: str, message_date: datetime, is_bot: bool, config: dict, min_score: int) -> bool:
    if is_bot:
        return False
    if is_too_short(text):
        return False
    if is_old_message(message_date):
        return False
    if keyword_score(text, config) < min_score:
        return False
    return True
