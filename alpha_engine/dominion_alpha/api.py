import asyncio
import json
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from dominion_alpha.memory import get_conn, init_db, get_memory_stats
from dominion_alpha.paper_broker import get_capital, get_open_positions
from dominion_alpha.governor import scan_and_score, run_cycle, run_loop, get_state, toggle_kill_switch, emergency_exit_all
from dominion_alpha.performance import compute_performance
from dominion_alpha.learning import get_lessons, get_current_weights

app = FastAPI(title="Dominion Alpha Engine", version="2.0.0")


@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(run_loop())


def _pnl_color(v):
    return "#00ff88" if float(v or 0) >= 0 else "#ff4444"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    capital = get_capital()
    positions = get_open_positions()
    state = get_state()
    perf = compute_performance()
    mem = get_memory_stats()
    weights = get_current_weights()

    conn = get_conn()
    trades = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 20").fetchall()
    decisions = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    lessons = get_lessons(5)

    top_tokens = state.last_top_tokens[:20]

    trades_html = "".join(
        f"<tr><td>{r['timestamp'][:16]}</td><td>{r['symbol']}</td>"
        f"<td style='color:{'#00ff88' if r['action']=='BUY' else '#ff4444'}'>{r['action']}</td>"
        f"<td>${float(r['price']):.8f}</td><td>${float(r['size_usd']):.2f}</td>"
        f"<td style='color:{_pnl_color(r['pnl'])}'>${float(r['pnl']):.4f}</td></tr>"
        for r in trades
    ) or "<tr><td colspan=6>No trades yet</td></tr>"

    pos_html = "".join(
        f"<tr><td>{p['symbol']}</td><td>{p['timestamp'][:16]}</td>"
        f"<td>${float(p['price']):.8f}</td><td>${float(p['size_usd']):.2f}</td></tr>"
        for p in positions
    ) or "<tr><td colspan=4>No open positions</td></tr>"

    picks_html = "".join(
        f"<tr><td>{t.get('symbol','?')}</td><td>{t.get('chain','')}</td>"
        f"<td style='color:{'#00ff88' if t.get('verdict')=='BUY' else '#ffaa00'}'>{t.get('verdict','')}</td>"
        f"<td>{t.get('score',0):.3f}</td>"
        f"<td>${float(t.get('liquidity_usd') or t.get('liquidity') or 0):,.0f}</td>"
        f"<td>${float(t.get('market_cap') or 0):,.0f}</td>"
        f"<td>{float(t.get('pair_age_hours') or 0):.1f}h</td>"
        f"<td style='font-size:11px'>{str(t.get('thesis',''))[:60]}</td></tr>"
        for t in top_tokens
    ) or "<tr><td colspan=8>No scan data yet</td></tr>"

    decisions_html = "".join(
        f"<tr><td>{d['timestamp'][:16]}</td><td>{d['symbol']}</td>"
        f"<td style='color:{'#00ff88' if d['approved'] else '#ff4444'}'>{d['action']}</td>"
        f"<td>{float(d['score'] or 0):.3f}</td>"
        f"<td style='font-size:11px'>{str(d['thesis'] or '')[:70]}</td></tr>"
        for d in decisions
    ) or "<tr><td colspan=5>No decisions yet</td></tr>"

    weights_html = "".join(
        f"<tr><td>{name}</td><td>{v['weight']:.3f}</td><td>{v['accuracy']:.1%}</td></tr>"
        for name, v in weights.items()
    )

    lessons_html = "".join(
        f"<tr><td>{l['timestamp'][:16]}</td>"
        f"<td style='color:{'#00ff88' if 'WIN' in str(l['lesson']) else '#ff4444'}'>{l['lesson']}</td></tr>"
        for l in lessons
    ) or "<tr><td colspan=2>No lessons yet</td></tr>"

    errors_html = "".join(f"<li style='color:#ff6644'>{e}</li>" for e in (state.errors or [])) or "<li style='color:#00ff88'>None</li>"

    kill_color = "#ff4444" if state.kill_switch else "#00ff88"
    kill_label = "KILLED" if state.kill_switch else "ACTIVE"

    html = f"""
<!DOCTYPE html><html><head><title>Dominion Alpha v2</title>
<meta http-equiv='refresh' content='30'>
<style>
body{{font-family:monospace;background:#060610;color:#c8d8ff;padding:16px;margin:0;font-size:13px}}
h1{{color:#00ff88;border-bottom:1px solid #1a2a4a;padding-bottom:8px;margin-bottom:16px}}
h2{{color:#88aaff;font-size:14px;margin:18px 0 8px;border-bottom:1px solid #1a2a2a;padding-bottom:4px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}}
.card{{background:#0c0c1e;border:1px solid #1a2a4a;padding:12px;border-radius:6px}}
.card h3{{color:#667;margin:0 0 6px;font-size:11px;text-transform:uppercase}}
.card h2{{margin:0;font-size:20px;color:#c8d8ff}}
table{{width:100%;border-collapse:collapse;margin:6px 0;font-size:12px}}
th{{color:#667;text-align:left;border-bottom:1px solid #1a2a2a;padding:5px 4px}}
td{{padding:4px;border-bottom:1px solid #0f1528}}
.panel{{background:#0c0c1e;border:1px solid #1a2a4a;padding:12px;border-radius:6px;margin:10px 0}}
</style></head><body>
<h1>&#9889; DOMINION ALPHA ENGINE v2.0</h1>

<div class='grid'>
<div class='card'><h3>Capital</h3><h2>${capital:,.2f}</h2></div>
<div class='card'><h3>Open Positions</h3><h2>{len(positions)}</h2></div>
<div class='card'><h3>Governor</h3><h2 style='color:{kill_color}'>{kill_label}</h2></div>
<div class='card'><h3>Mode</h3><h2 style='color:#ffaa00'>PAPER</h2></div>
</div>

<div class='grid'>
<div class='card'><h3>Win Rate</h3><h2>{perf['win_rate']:.1%}</h2></div>
<div class='card'><h3>Profit Factor</h3><h2>{perf['profit_factor']:.2f}</h2></div>
<div class='card'><h3>Expectancy</h3><h2>${perf['expectancy']:.4f}</h2></div>
<div class='card'><h3>Total PnL</h3><h2 style='color:{_pnl_color(perf["total_pnl"])}'>${perf['total_pnl']:.2f}</h2></div>
</div>

<div class='grid3'>
<div class='card'><h3>Threshold</h3><h2>{state.confidence_threshold}</h2></div>
<div class='card'><h3>Cycles Run</h3><h2>{state.cycles_run}</h2></div>
<div class='card'><h3>Last Scan</h3><h2>{state.last_scan_count} tokens</h2></div>
</div>

<div class='panel'>
<h2>Top 20 Tokens &mdash; Last Scan</h2>
<table><tr><th>Symbol</th><th>Chain</th><th>Verdict</th><th>Score</th><th>Liquidity</th><th>Market Cap</th><th>Age</th><th>Thesis</th></tr>
{picks_html}</table></div>

<div class='panel'>
<h2>Open Positions</h2>
<table><tr><th>Symbol</th><th>Opened</th><th>Entry</th><th>Size</th></tr>
{pos_html}</table></div>

<div class='panel'>
<h2>Recent Trades</h2>
<table><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Price</th><th>Size</th><th>PnL</th></tr>
{trades_html}</table></div>

<div class='panel'>
<h2>Governor Decisions (last 10)</h2>
<table><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Score</th><th>Thesis</th></tr>
{decisions_html}</table></div>

<div class='grid3'>
<div class='panel'>
<h2>Advisor Weights (Live)</h2>
<table><tr><th>Advisor</th><th>Weight</th><th>Accuracy</th></tr>{weights_html}</table>
</div>
<div class='panel'>
<h2>Memory Stats</h2>
<table><tr><th>Table</th><th>Rows</th></tr>
{''.join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k,v in mem.items())}
</table></div>
<div class='panel'>
<h2>Lessons Learned</h2>
<table><tr><th>Time</th><th>Lesson</th></tr>{lessons_html}</table>
<h2>Errors</h2><ul>{errors_html}</ul>
</div></div>

</body></html>"""
    return HTMLResponse(html)


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "dominion-alpha", "mode": "paper", "version": "2.0", "live_trading": False}


@app.get("/capital")
async def capital_ep():
    return {"capital": get_capital()}


@app.get("/positions")
async def positions_ep():
    return {"positions": get_open_positions()}


@app.get("/scan")
async def scan_ep():
    tokens = await scan_and_score()
    return {"count": len(tokens), "top": tokens[:20]}


@app.get("/cycle")
async def cycle_ep():
    return await run_cycle()


@app.get("/trades")
async def trades_ep():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return {"trades": [dict(r) for r in rows]}


@app.get("/performance")
async def performance_ep():
    return compute_performance()


@app.get("/decisions")
async def decisions_ep():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return {"decisions": [dict(r) for r in rows]}


@app.get("/watchlist")
async def watchlist_ep():
    state = get_state()
    watch = [t for t in state.last_top_tokens if t.get("verdict") == "WATCH"]
    return {"watchlist": watch}


@app.get("/lessons")
async def lessons_ep():
    return {"lessons": get_lessons(20)}


@app.get("/weights")
async def weights_ep():
    return {"weights": get_current_weights()}


@app.post("/governor/kill")
async def kill_switch_ep():
    active = toggle_kill_switch()
    return {"kill_switch": active, "message": "KILL SWITCH ACTIVATED" if active else "Kill switch deactivated"}


@app.post("/governor/emergency-exit")
async def emergency_exit_ep():
    return await emergency_exit_all()


@app.get("/status")
async def status_ep():
    state = get_state()
    return {
        "version": state.version,
        "kill_switch": state.kill_switch,
        "confidence_threshold": state.confidence_threshold,
        "cycles_run": state.cycles_run,
        "last_scan_count": state.last_scan_count,
        "last_cycle_ts": state.last_cycle_ts,
        "capital": get_capital(),
        "open_positions": len(get_open_positions()),
        "errors": state.errors,
        "live_trading": False,
    }
