# ===========================================================
# RajanTradeAutomation – Main.py (Phase 2.6 CSV production-ready)
# Replace existing Main.py in Render with this file.
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback, csv, io

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment Variables ----------
WEBAPP_EXEC_URL  = os.getenv("WEBAPP_EXEC_URL")        # required
CHARTINK_TOKEN   = os.getenv("CHARTINK_TOKEN", "RAJAN123")
SCANNER_NAME     = os.getenv("SCANNER_NAME", "Rocket Rajan Scanner")
SCANNER_URL      = os.getenv("SCANNER_URL", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MODE             = os.getenv("MODE", "SYNC").upper()   # CSV or SYNC
CSV_TIMEOUT_SECS = int(os.getenv("CSV_TIMEOUT_SECS", "10"))
USER_AGENT       = os.getenv("USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64)")

# ---------- Helpers ----------
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.status_code, r.text)
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

# ---------- CSV download helper ----------
def download_chartink_csv(scanner_url: str):
    """
    Try to construct Chartink export URL and download CSV.
    Returns CSV text or None.
    """
    try:
        if not scanner_url:
            return None
        # Build export path
        if "/screener/" in scanner_url and "/screener/export/" not in scanner_url:
            csv_url = scanner_url.replace("/screener/", "/screener/export/")
        else:
            csv_url = scanner_url
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

# ---------- CSV parse helper ----------
def parse_csv_text(csv_text: str):
    """
    Parse CSV text into list of dicts with keys:
    symbol, price (float or None), change_pct (float or None), volume (int or None)
    """
    try:
        f = io.StringIO(csv_text)
        reader = csv.reader(f)
        rows = list(reader)
        if not rows:
            return []
        header = [h.strip().lower() for h in rows[0]]
        # find indices
        symbol_idx = None
        price_idx = None
        chg_idx = None
        vol_idx = None
        for i, col in enumerate(header):
            c = col.lower()
            if c in ("symbol", "ticker", "code"):
                symbol_idx = i
            if "price" in c or c == "ltp" or c == "last":
                price_idx = i
            if "%ch" in c or "%chg" in c or "change" in c:
                chg_idx = i
            if "volume" in c:
                vol_idx = i
        stocks = []
        for row in rows[1:]:
            if not row or all([not c.strip() for c in row]):
                continue
            # symbol
            sym = None
            if symbol_idx is not None and symbol_idx < len(row):
                sym = row[symbol_idx].strip().replace('"','')
            else:
                # fallback: try column C (third) as csv screenshot shows symbol at C
                if len(row) >= 3 and row[2].strip():
                    sym = row[2].strip().replace('"','')
            if not sym:
                continue
            # price
            price = None
            if price_idx is not None and price_idx < len(row):
                try:
                    price = float(row[price_idx].replace(",","").replace('"','').strip())
                except:
                    price = None
            # change %
            change_pct = None
            if chg_idx is not None and chg_idx < len(row):
                try:
                    change_pct = float(row[chg_idx].replace("%","").replace(",","").replace('"','').strip())
                except:
                    change_pct = None
            # volume
            volume = None
            if vol_idx is not None and vol_idx < len(row):
                try:
                    volume = int(row[vol_idx].replace(",","").replace('"','').strip())
                except:
                    volume = None
            stocks.append({
                "symbol": sym,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
        return stocks
    except Exception as e:
        print("CSV parse exception:", e)
        return []

# ---------- helper to get detected count from incoming payload ----------
def detect_count_from_payload(d):
    try:
        s = d.get("stocks")
        if isinstance(s, list): return len(s)
        if isinstance(s, dict): return len(s.keys())
        if isinstance(s, str): return len([x for x in s.split(",") if x.strip()])
    except:
        pass
    return 0

# ---------- Chartink Alert Receiver (CSV / SYNC safe) ----------
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

        incoming_detected = detect_count_from_payload(data)

        # Try CSV path if requested
        if MODE == "CSV":
            csv_text = download_chartink_csv(SCANNER_URL)
            if csv_text:
                parsed = parse_csv_text(csv_text)
                if parsed:
                    payload = {
                        "action": "chartink_import",
                        "payload": {
                            "stocks": parsed,
                            "detected_count": incoming_detected or len(parsed),
                            "scanner_name": SCANNER_NAME,
                            "scanner_url": SCANNER_URL,
                            "source": "csv"
                        }
                    }
                    res = gs_post(payload)
                    imported = 0
                    try:
                        if isinstance(res, dict) and "count" in res:
                            imported = int(res.get("count", 0))
                    except:
                        imported = 0
                    if imported == 0:
                        imported = len(parsed)
                    diff = (incoming_detected or len(parsed)) - imported
                    send_telegram(f"📊 SmartCountSync (CSV)\nDetected: {incoming_detected or len(parsed)}\nImported: {imported}\nDiff: {diff}")
                    return jsonify({"ok": True, "mode": "CSV", "detected": incoming_detected or len(parsed), "imported": imported})
                else:
                    print("CSV parsed 0 stocks; falling back to SYNC")
            else:
                print("CSV download failed; falling back to SYNC")

        # SYNC fallback
        res = gs_post({"action": "chartink_import", "payload": data})
        imported = 0
        try:
            if isinstance(res, dict) and "count" in res:
                imported = int(res.get("count", 0))
        except:
            imported = 0

        send_telegram(f"📥 Chartink alert received — forwarded to WebApp.\n✅ {incoming_detected} stocks detected.\nImported: {imported}")
        return jsonify({"ok": True, "mode": "SYNC", "detected": incoming_detected, "imported": imported})

    except Exception as e:
        err = traceback.format_exc()
        send_telegram(f"❌ Render webhook error:\n{str(e)[:300]}")
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Manual test route ----------
@app.get("/test-connection")
def test_connection():
    try:
        if not WEBAPP_EXEC_URL:
            return "WEBAPP_EXEC_URL missing in environment", 500
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

# ---------- Entry Point ----------
if __name__ == "__main__":
    print("🚀 RajanTradeAutomation Render Service starting... MODE=", MODE)
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
