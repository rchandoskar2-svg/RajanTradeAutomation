# ===========================================================
# RajanTradeAutomation – Phase 2.6 (Dual-Mode: SYNC + CSV)
# Replace existing Main.py with this file (or replace chartink-alert route only)
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment Variables ----------
WEBAPP_EXEC_URL  = os.getenv("WEBAPP_EXEC_URL")        # Google Apps Script WebApp URL (keep as-is)
CHARTINK_TOKEN   = os.getenv("CHARTINK_TOKEN", "RAJAN123")
SCANNER_NAME     = os.getenv("SCANNER_NAME", "Rocket Rajan Scanner")
SCANNER_URL      = os.getenv("SCANNER_URL", "")       # your Chartink screener page URL
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MODE             = os.getenv("MODE", "SYNC").upper()  # "SYNC" or "CSV"
CSV_TIMEOUT_SECS = int(os.getenv("CSV_TIMEOUT_SECS", "10"))  # timeout for CSV download
USER_AGENT       = os.getenv("USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64)")

# ---------- Helpers ----------
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.text)
    except Exception as e:
        print("Telegram error:", e)

def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured in environment")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "raw": r.text}

# ---------- Health ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "mode": MODE, "ts": int(time.time())})

# ---------- Utility: download Chartink CSV (timestamped) ----------
def download_chartink_csv(scanner_url: str):
    """
    Attempts to build CSV export URL from screener page and download it.
    Returns CSV text on success, None on failure.
    """
    try:
        if not scanner_url:
            return None
        # Chartink export path heuristic:
        # if scanner_url ends with '/screener/<name>' => replace with '/screener/export/<name>'
        if "/screener/" in scanner_url:
            csv_url = scanner_url.replace("/screener/", "/screener/export/")
        else:
            csv_url = scanner_url
        # Add timestamp to bust caches
        csv_url = f"{csv_url}?ts={int(time.time())}"
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(csv_url, headers=headers, timeout=CSV_TIMEOUT_SECS)
        if r.status_code == 200 and r.text and len(r.text) > 10:
            return r.text
        else:
            print("CSV download failed:", r.status_code, len(r.text) if r.text else 0)
            return None
    except Exception as e:
        print("CSV download exception:", e)
        return None

# ---------- Utility: parse CSV text into list of {symbol, maybe volume} ----------
def parse_csv_to_stocks(csv_text: str):
    """
    Expects first row header with columns including Symbol and maybe Volume.
    Returns list of dicts: [{"symbol":"ABC","volume":12345}, ...]
    """
    try:
        lines = [l for l in csv_text.splitlines() if l.strip()]
        if not lines:
            return []
        # naive CSV split (sufficient for Chartink CSV which is comma-separated)
        header = [h.strip().lower() for h in lines[0].split(",")]
        symbol_idx = None
        vol_idx = None
        for i, col in enumerate(header):
            if col in ("symbol", "ticker", "code"):
                symbol_idx = i
            if "volume" in col:
                vol_idx = i
        stocks = []
        for row in lines[1:]:
            cols = [c.strip() for c in row.split(",")]
            if symbol_idx is not None and symbol_idx < len(cols):
                sym = cols[symbol_idx].replace('"', '').strip()
                if not sym:
                    continue
                vol = None
                if vol_idx is not None and vol_idx < len(cols):
                    try:
                        vol = int(cols[vol_idx].replace(",", "").replace('"', "").strip())
                    except:
                        vol = None
                stocks.append({"symbol": sym, "volume": vol})
        return stocks
    except Exception as e:
        print("CSV parse error:", e)
        return []

# ---------- Chartink Alert Receiver (Dual Mode) ----------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid Chartink token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

        # enrich
        data["scanner_name"] = SCANNER_NAME
        data["scanner_url"]  = SCANNER_URL

        # detect count robustly (list/dict/string)
        stocks_field = data.get("stocks")
        detected = 0
        if isinstance(stocks_field, list):
            detected = len(stocks_field)
        elif isinstance(stocks_field, dict):
            detected = len(stocks_field.keys())
        elif isinstance(stocks_field, str):
            detected = len([s for s in stocks_field.split(",") if s.strip()])
        else:
            detected = 0

        # MODE handling
        if MODE == "CSV":
            # Try CSV path first
            csv_text = download_chartink_csv(SCANNER_URL)
            if csv_text:
                parsed = parse_csv_to_stocks(csv_text)
                if parsed:
                    # Forward parsed (with volume) to GAS as structured payload
                    payload = {"action": "chartink_import", "payload": {"stocks": parsed, "detected_count": detected, "scanner_name": SCANNER_NAME, "scanner_url": SCANNER_URL}}
                    res = gs_post(payload)
                    imported = res.get("count", 0) if isinstance(res, dict) else 0
                    # if GAS didn't return count, fallback to parsing message text
                    if imported == 0 and isinstance(res, dict) and "msg" in res:
                        try:
                            if "imported" in str(res["msg"]).lower():
                                parts = str(res["msg"]).split("imported")[0].split()
                                imported = int([x for x in parts if x.isdigit()][-1])
                        except:
                            imported = 0
                    diff = detected - imported
                    send_telegram(f"📊 SmartCountSync (CSV)\nDetected: {detected}\nImported: {imported}\nDiff: {diff}")
                    return jsonify({"ok": True, "mode": "CSV", "detected": detected, "imported": imported, "diff": diff})
                else:
                    print("CSV parsed 0 stocks; falling back to SYNC")
            else:
                print("CSV download failed or empty; falling back to SYNC")

        # SYNC fallback (or default)
        # forward original data to GAS (existing stable flow)
        res = gs_post({"action": "chartink_import", "payload": data})
        # compute imported from response robustly
        imported = 0
        if isinstance(res, dict):
            if "count" in res:
                try:
                    imported = int(res.get("count", 0))
                except:
                    imported = 0
            elif "msg" in res and "imported" in str(res["msg"]).lower():
                try:
                    parts = str(res["msg"]).split("imported")[0].split()
                    imported = int([x for x in parts if x.isdigit()][-1])
                except:
                    imported = 0

        send_telegram(f"📥 Chartink alert received — forwarded to WebApp.\n✅ {detected} stocks detected.\nImported: {imported}")
        return jsonify({"ok": True, "mode": "SYNC", "detected": detected, "imported": imported})

    except Exception as e:
        err = traceback.format_exc()
        send_telegram(f"❌ Render webhook error:\n{e}")
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Manual test routes ----------
@app.get("/test-connection")
def test_connection():
    try:
        r = requests.post(WEBAPP_EXEC_URL, json={"action": "get_settings"}, timeout=25)
        return r.text, 200, {"Content-Type": "application/json"}
    except Exception as e:
        return traceback.format_exc(), 500

@app.get("/test-telegram")
def test_telegram():
    try:
        send_telegram("✅ Telegram test successful — RajanTradeAutomation Render connected.")
        return jsonify({"ok": True, "msg": "Telegram sent"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Entry point ----------
if __name__ == "__main__":
    print("🚀 RajanTradeAutomation Render Service starting... MODE=", MODE)
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
