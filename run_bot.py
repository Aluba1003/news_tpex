import requests
import datetime
import os
import json
from dotenv import load_dotenv
from collections import OrderedDict

# 載入 .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PUSHED_FILE = "pushed.json"
MAX_RECORDS = 1000  # 最多保留 1000 筆紀錄

# =========================
# 確保 pushed.json 存在
# =========================
if not os.path.exists(PUSHED_FILE):
    with open(PUSHED_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# =========================
# 紀錄檔處理
# =========================
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

# =========================
# Telegram 推播
# =========================
def send_to_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ 缺少 TELEGRAM_TOKEN 或 CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("✅ 推播成功")
        else:
            print("❌ 推播失敗:", resp.text)
    except requests.RequestException as e:
        print(f"❌ 推播失敗: {e}")

# =========================
# 抓櫃買中心公告
# =========================
def fetch_announcements():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    start_date = f"{yesterday.year}/{yesterday.month:02d}/{yesterday.day:02d}"
    end_date   = f"{today.year}/{today.month:02d}/{today.day:02d}"

    url = f"https://www.tpex.org.tw/www/zh-tw/margin/announce?startDate={start_date}&endDate={end_date}&id=&response=json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"❌ 抓取公告失敗: {e}")
        return []

    messages = []
    tables = data.get("tables", [])
    for table in tables:
        for row in table.get("data", []):
            roc_date = row[0]   # 民國日期
            text = row[1]
            messages.append(f"{roc_date}\n{text}")
    return messages

# =========================
# 抓 TWSE 信用交易統計 (全市場)
# =========================
def fetch_market_balance(date=None):
    if date is None:
        today = datetime.date.today()
        date = today.strftime("%Y%m%d")

    url = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date}&selectType=ALL"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"❌ 抓取統計失敗: {e}")
        return None

    if data.get("stat") != "OK":
        return None

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
    return None

# =========================
# 主程式
# =========================
if __name__ == "__main__":
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("========== 櫃買中心公告 ==========")
    announcements = fetch_announcements()
    if announcements:
        for msg in announcements:
            if pushed_records.get(msg) is None:  # 沒推播過才推
                pushed_records[msg] = now
                send_to_telegram(msg)
                print(f"[{now}] 已推播公告：\n{msg}\n")
            else:
                print(f"[{now}] ⏸ 跳過重複公告：\n{msg}\n")
    else:
        print(f"[{now}] ⚠️ 今日沒有新的信用交易公告。")

    print("========== 信用交易統計 ==========")
    balance_msg = fetch_market_balance()
    if balance_msg:
        if pushed_records.get(balance_msg) is None:  # 沒推播過才推
            pushed_records[balance_msg] = now
            send_to_telegram(balance_msg)
            print(f"[{now}] 已推播信用交易統計：\n{balance_msg}\n")
        else:
            print(f"[{now}] ⏸ 跳過重複統計：\n{balance_msg}\n")
    else:
        print(f"[{now}] ⚠️ 今日沒有信用交易統計資料，可能是假日或尚未公布。")

    # ✅ 保證最後一定會寫入 pushed.json
    save_pushed_records(pushed_records)
