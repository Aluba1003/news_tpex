import requests
import datetime
import os
import json
import yfinance as yf
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
# 抓取貴金屬行情 (新增功能)
# =========================
def fetch_metal_prices():
    # 判斷星期，週末不回傳資料 (0=週一, 5=週六, 6=週日)
    weekday = datetime.datetime.now().weekday()
    if weekday >= 5:
        return None

    try:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        twd_rate = yf.Ticker("TWD=X").history(period="1d")['Close'].iloc[-1]
        
        metals = {
            "黃金": "GC=F",
            "白銀": "SI=F",
            "鉑金": "PL=F",
            "鈀金": "PA=F",
            "銅": "HG=F"
        }

        msg_lines = [f"全球金屬行情 ({now_str})", f"匯率: 1 USD = {twd_rate:.2f} TWD"]

        for name, symbol in metals.items():
            data = yf.Ticker(symbol).history(period="2d")
            if len(data) >= 2:
                current_price = data['Close'].iloc[-1]
                prev_price = data['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                sign = "+" if change_pct > 0 else ""
                
                twd = current_price * twd_rate
                
                info = f"{name} {current_price:>8.2f} USD ({sign}{change_pct:.2f}%)"
                if name == "黃金":
                    info += f"\nTWD {twd:,.0f}/盎司, {twd/8.294:,.0f}/台錢"
                elif name == "銅":
                    info += f"\nTWD {current_price*twd_rate:.2f}/磅"
                else:
                    info += f"\nTWD {twd:,.0f}/盎司"
                
                msg_lines.append(info)
        
        return "\n".join(msg_lines)
    except Exception as e:
        print(f"❌ 抓取貴金屬失敗: {e}")
        return None

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
# 抓取融資增減摘要 (上市 + 上櫃)
# =========================
def fetch_market_margin_summary():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01'
    }

    for i in range(7):
        target_date = datetime.date.today() - datetime.timedelta(days=i)
        date_str = target_date.strftime("%Y%m%d")

        twse_line = ""
        tpex_line = ""

        # --- 上市 (TWSE) ---
        try:
            url_twse = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date_str}&selectType=ALL"
            res_twse = requests.get(url_twse, headers=headers, timeout=10).json()
            if res_twse.get("stat") == "OK":
                for table in res_twse.get("tables", []):
                    if "信用交易統計" in table.get("title", ""):
                        for row in table.get("data", []):
                            if "融資" in row[0] and "金額" in row[0]:
                                diff = (int(row[-1].replace(",", "")) - int(row[-2].replace(",", ""))) / 100000
                                twse_line = f"加權指數融資增減：{diff:+.2f} 億元"
        except Exception as e:
            print(f"DEBUG: 上市抓取失敗 - {e}")

        # --- 上櫃 (TPEx) ---
        try:
            url_tpex = f"https://www.tpex.org.tw/www/zh-tw/margin/balance?date={date_str}&response=json"
            res_tpex = requests.get(url_tpex, headers=headers, timeout=10).json()
            
            # 根據你提供的 JSON 結尾，數據在 tables[0]['summary']
            # 我們直接從 tables 裡面挖
            tpex_tables = res_tpex.get("tables", [])
            if tpex_tables and "summary" in tpex_tables[0]:
                summary_data = tpex_tables[0]["summary"]
                
                # 遍歷 summary，尋找「融資金(仟元)」這一列
                for row in summary_data:
                    if "融資金" in str(row[1]):
                        # 根據你貼的數據：
                        # row[1] 是 "融資金(仟元)"
                        # row[2] 是 前日餘額 "133,446,927"
                        # row[6] 是 今日餘額 "135,866,180" (在 "74,249" 後面那個)
                        # ⚠️ 修正索引：在你的 JSON 中，融資金列的項目名稱是在 index 1
                        
                        prev_val = int(row[2].replace(",", ""))
                        today_val = int(row[6].replace(",", ""))
                        
                        diff = (today_val - prev_val) / 100000
                        tpex_line = f"櫃買指數融資增減：{diff:+.2f} 億元"
                        break
        except Exception as e:
            # print(f"解析出錯: {e}")
            pass

        # 檢查點
        if twse_line and tpex_line:
            header = f"📊 {target_date} 市場融資變動"
            msg = f"{header}\n\n{twse_line}\n{tpex_line}"
            print(f"✅ 成功組合資料：\n{msg}") # 這行會 print 在你的終端機
            return msg
        
        # 顯示哪一個沒抓到
        status = f"上市:{'OK' if twse_line else '失敗'}, 上櫃:{'OK' if tpex_line else '失敗'}"
        print(f"ℹ️ {target_date} {status}，繼續往前找...")

    return None

# =========================
# 主程式
# =========================
if __name__ == "__main__":
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- 1. 貴金屬行情 ---
    print("========== 貴金屬行情 ==========")
    metal_msg = fetch_metal_prices()
    if metal_msg:
        # 使用日期作為 Key 的一部分，確保每天推播一次
        pushed_key = f"METALS_{datetime.date.today()}"
        if pushed_records.get(pushed_key) is None:
            send_to_telegram(metal_msg)
            pushed_records[pushed_key] = now
            print(f"[{now}] 已推播貴金屬行情")
        else:
            print(f"[{now}] ⏸ 今日已推播過貴金屬行情")
    else:
        print(f"[{now}] ⚠️ 週末休市或資料獲取失敗，不執行推播。")

    # --- 2. 櫃買中心公告 ---
    print("========== 櫃買中心公告 ==========")
    announcements = fetch_announcements()
    if announcements:
        for msg in announcements:
            if pushed_records.get(msg) is None:
                pushed_records[msg] = now
                send_to_telegram(msg)
                print(f"[{now}] 已推播公告：\n{msg}\n")
            else:
                print(f"[{now}] ⏸ 跳過重複公告")
    else:
        print(f"[{now}] ⚠️ 今日沒有新的信用交易公告。")

    # --- 3. 信用交易統計 ---
    print("========== 融資變動統計 ==========")
    margin_msg = fetch_market_margin_summary()
    if margin_msg:
        if pushed_records.get(margin_msg) is None:
            send_to_telegram(margin_msg)
            pushed_records[margin_msg] = now
            print(f"[{now}] 已推播融資統計報告")
        else:
            print(f"[{now}] ⏸ 該日數據已推播過")
    else:
        print(f"[{now}] ⚠️ 無法取得融資統計資料。")

    # ✅ 保證最後一定會寫入 pushed.json
    save_pushed_records(pushed_records)