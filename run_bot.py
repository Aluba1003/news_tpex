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

# =========================
# 抓櫃買中心公告
# =========================
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

# =========================
# 抓 TWSE 信用交易統計 (全市場)
# =========================
def fetch_market_balance(date=None):
    if date is None:
        # 改成抓今天
        today = datetime.date.today()
        date = today.strftime("%Y%m%d")

    url = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date}&selectType=ALL"
    resp = requests.get(url)
    data = resp.json()

    if data.get("stat") != "OK":
        return f"{date} 沒有資料，可能是假日或尚未公布"

    for table in data.get("tables", []):
        if "信用交易統計" in table.get("title", ""):
            msg_lines = [f"📊 {date} 全市場信用交易統計"]
            for row in table.get("data", []):
                item = row[0]
                prev = int(row[-2].replace(",", ""))
                today_val = int(row[-1].replace(",", ""))
                diff = today_val - prev
                pct = (diff / prev * 100) if prev != 0 else 0
                msg_lines.append(
                    f"{item}\n  前日餘額：{prev:,}\n  今日餘額：{today_val:,}\n  增減數：{diff:+,}\n  增減百分比：{pct:+.2f}%\n"
                )
            return "\n".join(msg_lines)

    return f"{date} 找不到信用交易統計表格"

# =========================
# 主程式
# =========================
if __name__ == "__main__":
    # 1. 推播櫃買中心公告
    announcements = fetch_announcements()
    if announcements:
        for msg in announcements:
            send_to_telegram(msg)
    else:
        send_to_telegram("信用交易公告沒有新的公告。")

    # 2. 推播全市場融資融券餘額
    balance_msg = fetch_market_balance()
    send_to_telegram(balance_msg)
