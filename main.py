/******************************************************
   RajanTradeAutomation – SetupInitial.gs (v5.0 Final)
   FULL Auto Sheets + Headers + Settings + Daily Reset
   Compatible with Live Candle Engine (main.py v5.0)
******************************************************/

const TZ = "Asia/Kolkata";

/* =====================================================
   MAIN SETUP
===================================================== */
function setupInitial() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();

    const sheetNames = [
      "Settings",
      "Universe",
      "SectorPerf",
      "StockList",
      "CandleHistory",
      "Signals",
      "Trades",
      "LiveState",
      "PriceHistory",
      "Logs",
      "Dashboard",
      "State"
    ];

    // Delete default Sheet1
    const def = ss.getSheetByName("Sheet1");
    if (def) ss.deleteSheet(def);

    // Create missing sheets
    sheetNames.forEach(name => {
      if (!ss.getSheetByName(name)) ss.insertSheet(name);
    });

    setupHeaders_(ss);
    setupSettings_(ss);
    initDashboardTrades_(ss);

    resetTriggers_();
    createMidnightResetTrigger_();
    createRepairTrigger_();

    autoCenter_(ss);

    logInfo("Setup complete: Sheets + Headers + Settings ready.");

  } catch (err) {
    logError("setupInitial", err);
  }
}

/* =====================================================
   HEADERS
===================================================== */
function setupHeaders_(ss) {
  const headers = {
    Universe:      ["Symbol", "Name", "Sector", "IsFnO", "Enabled"],
    SectorPerf:    ["SectorName", "SectorCode", "%Chg", "Advances", "Declines"],
    StockList:     ["Symbol","DirectionBias","Sector","%Chg","LTP","Volume","Selected"],
    CandleHistory: ["Symbol","Time","Timeframe","Open","High","Low","Close","Volume","CandleIndex","LowestVolSoFar","IsSignal","Direction"],
    Signals:       ["Symbol","Direction","SignalTime","CandleIndex","Open","High","Low","Close","EntryPrice","SL","TargetPrice","RiskPerShare","RR","Status"],
    Trades:        ["Symbol","Direction","EntryPrice","SL","TargetPrice","QtyTotal","QtyExit1","Exit1Time","Exit1Price","Exit2Time","Exit2Price","PnL","Status"],
    LiveState:     ["Symbol","Direction","EntryPrice","SL","TargetPrice","QtyTotal","QtyRemaining","HalfExitDone","FullExitDone","LastUpdated"],
    PriceHistory:  ["Time","Symbol","Price"],
    Logs:          ["Timestamp","Level","Message"],
    Dashboard:     ["Symbol","Direction","EntryPrice","SL","TargetPrice","QtyTotal","QtyExit1","Exit1Time","Exit1Price","Exit2Time","Exit2Price","PnL","Status"],
    State:         ["Key","Value"]
  };

  for (const name in headers) {
    const sh = ss.getSheetByName(name);
    sh.clearContents();
    sh.appendRow(headers[name]);
    sh.getRange(1,1,1,headers[name].length)
      .setFontWeight("bold")
      .setHorizontalAlignment("center");
  }

  logInfo("All headers prepared.");
}

/* =====================================================
   SETTINGS
===================================================== */
function setupSettings_(ss) {
  const sh = ss.getSheetByName("Settings");
  sh.clearContents();

  const rows = [
    ["KEY","VALUE","DESCRIPTION"],

    ["MODE","PAPER","PAPER / LIVE"],
    ["AUTO_UNIVERSE","TRUE","Auto-fetch FnO universe daily"],
    ["BIAS_THRESHOLD","60","Min % breadth required"],

    ["BUY_SECTOR_COUNT","2","Top positive sectors"],
    ["SELL_SECTOR_COUNT","2","Top negative sectors"],

    ["MAX_UP_PERCENT","2.5","BUY max +%"],
    ["MAX_DOWN_PERCENT","-2.5","SELL max -%"],

    ["MAX_TRADE_TIME","12:00","No trades after this time"],
    ["MAX_TRADES_PER_DAY","5","Daily limit"],

    ["PER_TRADE_RISK","1000","₹ risk per trade"],
    ["RR_RATIO","2","Reward ratio"],
    ["PARTIAL_EXIT_PERCENT","50","Partial exit % (RR=2)"],
    ["AUTO_SQUAREOFF_TIME","15:15","Final exit cutoff"],

    ["TELEGRAM_TOKEN_ENC","","Encrypted bot token"],
    ["TELEGRAM_CHAT_ID_ENC","","Encrypted chat ID"]
  ];

  sh.getRange(1,1,rows.length,3).setValues(rows);
  sh.setColumnWidths(1,3,180);
  sh.getDataRange().setHorizontalAlignment("center");

  logInfo("Settings sheet prepared.");
}

/* =====================================================
   TRADES + DASHBOARD INIT
===================================================== */
function initDashboardTrades_(ss) {
  logInfo("Trades + Dashboard initialized.");
}

/* =====================================================
   TRIGGERS
===================================================== */
function resetTriggers_() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
}

function createMidnightResetTrigger_() {
  ScriptApp.newTrigger("dailyReset_")
    .timeBased()
    .atHour(0).nearMinute(0)
    .everyDays(1)
    .create();
}

function createRepairTrigger_() {
  ScriptApp.newTrigger("repairGuard")
    .timeBased()
    .everyMinutes(10)
    .create();
}

/* =====================================================
   DAILY RESET (Universe stays)
===================================================== */
function dailyReset_() {
  const ss = SpreadsheetApp.getActive();

  const wipeSheets = [
    "SectorPerf",
    "StockList",
    "CandleHistory",
    "Signals",
    "Trades",
    "LiveState",
    "Dashboard",
    "PriceHistory",
    "State"
  ];

  wipeSheets.forEach(name => {
    const sh = ss.getSheetByName(name);
    if (!sh) return;

    if (sh.getLastRow() > 1)
      sh.getRange(2,1, sh.getLastRow()-1, sh.getLastColumn()).clearContent();
  });

  autoCenter_(ss);
  logInfo("Daily reset completed.");
}

/* =====================================================
   UTILITIES
===================================================== */
function autoCenter_(ss) {
  ss.getSheets().forEach(sh => {
    try {
      const rng = sh.getDataRange();
      if (rng) rng.setHorizontalAlignment("center");
    } catch(e){}
  });
}

function now_() {
  return Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd HH:mm:ss");
}

function logInfo(msg) {
  const sh = SpreadsheetApp.getActive().getSheetByName("Logs");
  sh.appendRow([now_(),"INFO",msg]);
}

function logError(fn, err) {
  const sh = SpreadsheetApp.getActive().getSheetByName("Logs");
  sh.appendRow([now_(),"ERROR",`${fn}: ${err}`]);
}

function repairGuard() {
  try {
    const ss = SpreadsheetApp.getActive();
    const req = ["Settings","Universe","SectorPerf","StockList","CandleHistory","Signals","Trades","LiveState","PriceHistory","Logs","Dashboard","State"];
    req.forEach(n=>{
      if (!ss.getSheetByName(n)) {
        ss.insertSheet(n);
        logInfo("Recreated sheet: "+n);
      }
    });
  } catch(e) {
    logError("repairGuard", e);
  }
}
