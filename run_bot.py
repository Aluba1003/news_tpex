import requests
import datetime
import os
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_to_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

def fetch_announcements():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # 民國日期
    roc_today = today.year - 1911
    roc_yesterday = yesterday.year - 1911

    start_date = f"{roc_yesterday}/{yesterday.month:02d}/{yesterday.day:02d}"
    end_date = f"{roc_today}/{today.month:02d}/{today.day:02d}"

    url = f"https://www.tpex.org.tw/www/zh-tw/margin/announce?startDate={start_date}&endDate={end_date}&id=&response=json"
    resp = requests.get(url)
    data = resp.json()

    messages = []
    tables = data.get("tables", [])
    for table in tables:
        for row in table.get("data", []):
            roc_date = row[0]
            text = row[1]

            # 民國轉西元
            parts = roc_date.split("/")
            year = int(parts[0]) + 1911
            full_date = f"{year}-{parts[1]}-{parts[2]}"

            messages.append(f"{full_date}\n{text}")

    return messages

if __name__ == "__main__":
    announcements = fetch_announcements()
    if announcements:
        for msg in announcements:   # 每則公告獨立推播
            send_to_telegram(msg)
    else:
        send_to_telegram("信用交易公告沒有新的公告。")
