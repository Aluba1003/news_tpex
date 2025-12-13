import os
import time
import requests
import feedparser
import yaml
import json
from dotenv import load_dotenv
from collections import OrderedDict

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PUSHED_FILE = "pushed.json"
MAX_RECORDS = 1000  # 限制最多保留 1000 筆紀錄

def load_pushed_records():
    if os.path.exists(PUSHED_FILE):
        try:
            with open(PUSHED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return OrderedDict(data)
        except Exception as e:
            print(f"❌ 無法讀取 {PUSHED_FILE}: {e}")
    return OrderedDict()

def save_pushed_records(records):
    while len(records) > MAX_RECORDS:
        records.popitem(last=False)  # 刪掉最舊的
    try:
        with open(PUSHED_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 無法寫入 {PUSHED_FILE}: {e}")

pushed_records = load_pushed_records()

def send_telegram(text: str, delay: int):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ 缺少 TELEGRAM_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    })
    if resp.status_code != 200:
        data = resp.json()
        print("❌ 推播失敗:", data)
        if data.get("error_code") == 429:
            retry_after = data["parameters"]["retry_after"]
            print(f"⏸ 等待 {retry_after} 秒後重試...")
            time.sleep(retry_after)
            return send_telegram(text, delay)
    else:
        print("✅ 推播成功")
    time.sleep(delay)

def fetch_rss(source_name, url, keywords, match_mode="any"):
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title, link = entry.title, entry.link
            summary = getattr(entry, "summary", getattr(entry, "description", ""))
            text_to_check = f"{title} {summary}"

            # ✅ 不排除任何標題，全部抓取
            if keywords:
                if match_mode == "any" and any(kw in text_to_check for kw in keywords):
                    results.append((source_name, title, link))
                elif match_mode == "all" and all(kw in text_to_check for kw in keywords):
                    results.append((source_name, title, link))
            else:
                results.append((source_name, title, link))
    except Exception as e:
        results.append((source_name, f"【抓取失敗: {e}】", ""))
    return results

def load_config():
    config = {}
    if os.path.exists("sources.yml"):
        with open("sources.yml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    return config

def main():
    config = load_config()
    if not config:
        raise ValueError("❌ 沒有找到任何設定 sources.yml")

    keywords = config.get("keywords", [])
    match_mode = config.get("match_mode", "any")
    delay = config.get("delay", 1)

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            print(f"⏸ 跳過來源: {source['name']}")
            continue
        name = source["name"]
        url = source["url"]
        results = fetch_rss(name, url, keywords, match_mode)

        for src, title, link in results:
            prev_title = pushed_records.get(link)
            if prev_title is None:
                pushed_records[link] = title
                message = f"{src}\n{title}\n{link}"
                send_telegram(message, delay)
                save_pushed_records(pushed_records)
            elif prev_title != title:
                pushed_records[link] = title
                message = f"{src}\n{title}\n{link}"
                send_telegram(message, delay)
                save_pushed_records(pushed_records)
            else:
                print(f"⏸ 跳過重複: {title} ({link})")

if __name__ == "__main__":
    main()
