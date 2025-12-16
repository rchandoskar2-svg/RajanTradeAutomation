from datetime import datetime, time as dtime

def fetch_first_3_candles():
    print("Fetching 9:15–9:30 historical candles...")

    data = {
        "symbol": SYMBOL,
        "resolution": "5",
        "date_format": "1",
        "range_from": "2025-12-16",
        "range_to": "2025-12-16",
        "cont_flag": "1"
    }

    resp = fyers.history(data)
    candles = resp.get("candles", [])

    target = []

    for c in candles:
        ts = datetime.fromtimestamp(c[0])
        t = ts.time()

        # 🎯 STRICT TIME FILTER
        if dtime(9, 15) <= t < dtime(9, 30):
            if c[5] > 0:  # volume check
                target.append({
                    "time": ts.strftime("%H:%M:%S"),
                    "open": c[1],
                    "high": c[2],
                    "low": c[3],
                    "close": c[4],
                    "volume": c[5]
                })

    # sort just in case
    target.sort(key=lambda x: x["time"])

    print("Filtered candles:", target)

    # ✅ FINAL SAFETY CHECK
    if len(target) != 3:
        print("❌ ERROR: Expected 3 candles, got", len(target))
        return

    for candle in target:
        print("HIST:", candle)
        push_candle(candle)
        time.sleep(1)

    print("✅ 9:15–9:30 historical candles DONE")
