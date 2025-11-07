# ===========================================================
# RajanTradeAutomation – Phase 2.2 (Stable, Single Telegram, Correct Count)
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment ----------
WEBAPP_EXEC_URL  = os.getenv("WEBAPP_EXEC_URL")           # GAS WebApp exec URL
CHARTINK_TOKEN   = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------- Helpers ----------
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=25)
    r.raise_for_status()
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}

# ---------- Health ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "ts": int(time.time())})

@app.get("/test-connection")
def test_connection():
    try:
        if not WEBAPP_EXEC_URL:
            return "WEBAPP_EXEC_URL missing in environment", 500
        r = requests.post(WEBAPP_EXEC_URL, json={"action": "get_settings"}, timeout=25)
        return r.text, 200, {"Content-Type": "application/json"}
    except Exception as e:
        return traceback.format_exc(), 500

# ---------- Chartink Webhook ----------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid token"}), 403

        # 1) Parse incoming JSON (robust)
        raw = request.get_json(force=True, silent=True) or {}
        stocks = []

        if isinstance(raw, dict) and "stocks" in raw:
            stocks = raw["stocks"]
        elif isinstance(raw, list):
            stocks = raw
        elif isinstance(raw, str):
            stocks = [{"symbol": s.strip()} for s in raw.split(",") if s.strip()]

        # 2) Clean symbols
        clean_stocks = []
        for s in stocks:
            if isinstance(s, dict) and ("symbol" in s or "nsecode" in s):
                sym = (s.get("symbol") or s.get("nsecode") or "").strip().upper()
                if sym and len(sym) < 15:
                    clean_stocks.append({"symbol": sym})

        # 3) Forward to GAS (IMPORTANT: keep cleaned stocks, override raw)
        #    NOTE: order matters → {**raw, "stocks": clean_stocks}
        payload_to_gas = {"action": "chartink_import", "payload": {**(raw if isinstance(raw, dict) else {}), "stocks": clean_stocks}}
        res = gs_post(payload_to_gas)

        # 4) Single source of truth for Telegram: use GAS response count (not guessed here)
        gas_count = None
        try:
            gas_count = int(res.get("count"))
        except Exception:
            gas_count = None

        if gas_count is not None:
            # Optional: send final confirmation from Render (WebApp already sends one; keep OFF to avoid duplicates)
            # send_telegram(f"📊 Chartink import complete — {gas_count} stocks imported.")
            pass

        return jsonify({"ok": True, "forwarded": True, "count_from_gas": gas_count, "gas_response": res})

    except Exception as e:
        # Try to log to GAS
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Entry ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
