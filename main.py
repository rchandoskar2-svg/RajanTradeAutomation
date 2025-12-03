# ----------------------------------------------------
# ----------- CHARTINK DEBUG ROUTE -------------------
# ----------------------------------------------------
@app.post("/debug-chartink")
def debug_chartink():
    print("""
========== RAW CHARTINK ALERT (DEBUG) ==========
""")
    print("Headers:", dict(request.headers))
    print("Body:", request.data.decode(errors="ignore"))
    print("""
===============================================
""")
    return {"ok": True, "msg": "debug logged"}, 200


# ----------------------------------------------------
# ----------- MAIN CHARTINK ALERT ROUTE --------------
# ----------------------------------------------------
@app.route("/chartink-alert", methods=["GET", "POST"])
def chartink_alert():
    """
    Chartink webhook endpoint.
    """
    print("""
====== CHARTINK ALERT HIT ======
""")
    print("Method:", request.method)
    print("Query args:", dict(request.args))

    # ---- Token validation (query param) ----
    incoming_token = request.args.get("token", "").strip()
    if CHARTINK_TOKEN and incoming_token != CHARTINK_TOKEN:
        print("❌ Invalid token:", incoming_token)
        return {"ok": False, "error": "Invalid token"}, 403

    # ---- Handle GET pings ----
    if request.method == "GET":
        print("GET ping received on /chartink-alert → returning pong")
        print("""
============================================
""")
        return {"ok": True, "msg": "pong"}, 200

    # ---- POST: actual alert ----
    try:
        body_raw = request.data.decode(errors="ignore")
        print("RAW BODY:", body_raw or "[EMPTY]")

        # Try JSON first
        data = json.loads(body_raw) if body_raw else {}

    except Exception as e:
        print("❌ JSON parse error:", str(e))
        return {"ok": False, "error": "Invalid JSON"}, 400

    if not isinstance(data, dict) or "stocks" not in data:
        print("❌ Invalid payload structure, 'stocks' missing")
        print("""
============================================
""")
        return {"ok": False, "error": "Invalid payload (no stocks)"}, 400

    # ---- Forward to Google Apps Script ----
    if not WEBAPP_URL:
        print("❌ WEBAPP_URL not configured")
        return {"ok": False, "error": "WEBAPP_URL not set"}, 500

    try:
        res = requests.post(WEBAPP_URL, json=data, timeout=10)
        print("Forward Response status:", res.status_code)
        print("Forward Response body:", res.text)

    except Exception as e:
        print("❌ FORWARD ERROR:", str(e))
        print("""
============================================
""")
        return {"ok": False, "error": "Forward failed"}, 500

    print("""
====== CHARTINK ALERT PROCESSED SUCCESSFULLY ======
""")
    return {"ok": True}, 200
