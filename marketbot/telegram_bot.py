from __future__ import annotations
import time
import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def split_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        candidate = line if not cur else cur + "\n" + line
        if len(candidate) <= limit:
            cur = candidate
        else:
            if cur:
                chunks.append(cur)
            # a single over-long line: hard-split
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            cur = line
    if cur:
        chunks.append(cur)
    return chunks


def send_message(token: str, chat_ids: list[str], text: str,
                 parse_mode: str | None = None, retries: int = 3,
                 backoff: float = 2.0, session: requests.Session | None = None) -> None:
    sess = session or requests.Session()
    url = API.format(token=token)
    for chat_id in chat_ids:
        for chunk in split_message(text):
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            _post_with_retry(sess, url, payload, retries, backoff)


def _post_with_retry(sess, url, payload, retries, backoff) -> None:
    last = None
    for attempt in range(retries):
        try:
            resp = sess.post(url, data=payload, timeout=30)
            if resp.status_code == 200 and resp.json().get("ok", False):
                return
            last = f"status={resp.status_code} body={resp.json()}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < retries - 1 and backoff:
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Telegram send failed after {retries} attempts: {last}")
