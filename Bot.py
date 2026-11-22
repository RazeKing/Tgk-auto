
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

# --- НАСТРОЙКИ (лучше задавать через переменные окружения Secrets/Env) ---
RSS_URL = os.environ.get("RSS_URL", "https://habr.com/ru/rss/all/all/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8629939031:AAGWA33Z0lnMPtuVbJDNQqscpJc5U1Y7uGo")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "@experttest10")  # Например: @my_channel или -1001234567890
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
STATE_FILE = "posted_links.json"


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_posted_links() -> set:
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def save_posted_links(links: set) -> None:
    # Храним последние 300 ссылок, чтобы файл не разрастался
    trimmed = list(links)[-300:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def fetch_latest_unposted_item(rss_url: str, posted: set) -> dict | None:
    req = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TelegramNewsBot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_data = resp.read()

    root = ET.fromstring(xml_data)

    # Поддержка стандартного RSS (<item>) и Atom (<entry>)
    items = root.findall(".//item")
    entries = []

    if items:
        for item in items:
            title = clean_html(item.findtext("title", ""))
            desc = clean_html(item.findtext("description", ""))
            link = (item.findtext("link") or item.findtext("guid") or "").strip()
            entries.append({"title": title, "desc": desc, "link": link})
    else:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = clean_html(entry.findtext("atom:title", "", ns))
            summary = clean_html(entry.findtext("atom:summary", "", ns))
            link_el = entry.find("atom:link", ns)
            link = (link_el.attrib.get("href", "") if link_el is not None else "").strip()
            entries.append({"title": title, "desc": summary, "link": link})

    for entry in entries:
        unique_id = entry["link"] or entry["title"]
        if unique_id and unique_id not in posted:
            entry["id"] = unique_id
            return entry

    return None


def rewrite_with_groq(title: str, desc: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("Не задан GROQ_API_KEY")

    prompt = (
        "Напиши короткий живой пост для Telegram-канала (до 700 символов) на основе этой новости. "
        "Сделай цепляющий заголовок, убери воду и канцелярит, разбей на 2-3 абзаца, "
        "в конце задай 1 короткий вопрос подписчикам. Не используй звездочки и решетки.\n\n"
        f"Заголовок: {title}\n"
        f"Описание: {desc[:1500]}"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    content = result["choices"][0]["message"]["content"].strip()
    if not content:
        raise RuntimeError("Groq вернул пустой ответ")
    return content


def send_to_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        tg_result = json.loads(resp.read().decode("utf-8"))

    if not tg_result.get("ok"):
        raise RuntimeError(f"Ошибка Telegram API: {tg_result}")


def main() -> None:
    posted = load_posted_links()
    item = fetch_latest_unposted_item(RSS_URL, posted)

    if not item:
        print("Новых записей в RSS не найдено.")
        return

    print(f"Обрабатываю новость: {item['title']}")
    post_text = rewrite_with_groq(item["title"], item["desc"])
    send_to_telegram(post_text)

    posted.add(item["id"])
    save_posted_links(posted)
    print("Пост успешно опубликован!")


if __name__ == "__main__":
    main()
  
