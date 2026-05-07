#!/usr/bin/env python3
"""
ICT Backtest Runner — Optimized
Fetches data ONCE, slices per date, trailing stop logic, CSV output.
"""

import sys
import os
import csv
import warnings
import gc
import logging

warnings.filterwarnings('ignore')

# Use script directory for imports (no hardcoded paths)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from datetime import datetime, timedelta
from ict_analyzer import ICTAnalyzer, analyze_stock
import yfinance as yf
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.WARNING, format='%(message)s')

# ============ Config ============
SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
DAYS_AFTER = 30
INTERVAL_DAYS = 1

TIMESTAMP = datetime.now().strftime('%m%d_%H%M')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "samples", f"{SYMBOL.lower()}_daily_{TIMESTAMP}")
os.makedirs(os.path.join(OUTPUT_DIR, "charts"), exist_ok=True)

# ============ Date Range ============
end_date = datetime.now()
start_date = end_date - timedelta(days=730)

dates = []
current = start_date
while current < end_date - timedelta(days=DAYS_AFTER):
    dates.append(current.strftime('%Y-%m-%d'))
    current += timedelta(days=INTERVAL_DAYS)

print(f"📊 {SYMBOL} Daily Backtest: {len(dates)} dates")
print(f"📅 Range: {dates[0]} → {dates[-1]}")
print(f"📁 Output: {OUTPUT_DIR}\n")

# ============ Pre-fetch data ONCE ============
print("⏳ Fetching full 2-year dataset...")
full_df = yf.download(SYMBOL, period="2y", interval="1h", progress=False, threads=False)

if isinstance(full_df.columns, pd.MultiIndex):
    full_df.columns = full_df.columns.get_level_values(0)

# Resample to 4H
full_df = full_df.resample('4h').agg({
    'Open': 'first', 'High': 'max', 'Low': 'min',
    'Close': 'last', 'Volume': 'sum',
}).dropna()

print(f"✅ {len(full_df)} 4H candles loaded\n")

# ============ Backtest Loop ============
results = []
charts_saved = 0
MAX_CHARTS = 100
errors = 0
last_entry_price = None

for i, backtest_date in enumerate(dates):
    try:
        cutoff = pd.Timestamp(backtest_date) + pd.Timedelta(days=1)
        outcome_cutoff = pd.Timestamp(backtest_date) + pd.Timedelta(days=DAYS_AFTER + 1)

        if full_df.index.tz is not None:
            if cutoff.tz is None:
                cutoff = cutoff.tz_localize(full_df.index.tz)
                outcome_cutoff = outcome_cutoff.tz_localize(full_df.index.tz)

        df_before = full_df[full_df.index < cutoff]
        df_full = full_df[full_df.index < outcome_cutoff]

        if len(df_before) < 50 or len(df_full) < 50:
            continue

        # Setup analyzer with pre-sliced data (no yfinance call)
        analyzer = ICTAnalyzer(SYMBOL, "4h")
        analyzer.set_data(df_before)
        analyzer.detect_swing_points()
        analyzer.detect_order_blocks()
        analyzer.detect_equal_highs_lows()
        analyzer.detect_fair_value_gaps()

        plan = analyzer.calculate_trade_plan()
        entry, sl = plan['entry'], plan['sl']
        tp1, tp2, tp3 = plan['tp1'], plan['tp2'], plan['tp3']

        # Deduplication: skip if entry within 0.5% of last trade
        if last_entry_price is not None:
            if abs(entry - last_entry_price) / last_entry_price < 0.005:
                continue

        entry_time = df_before.index[-1]

        # Outcome analyzer
        analyzer_after = ICTAnalyzer(SYMBOL, "4h")
        analyzer_after.set_data(df_full)

        outcome_df = df_full[df_full.index > entry_time]
        if outcome_df.empty:
            continue

        # ============ Trailing Stop Logic ============
        sl_hit = tp1_hit = tp2_hit = tp3_hit = False
        exit_price = float(outcome_df['Close'].iloc[-1])
        exit_reason = "Timeout"
        trailing_sl = sl  # Dynamic trailing stop

        for _, row in outcome_df.iterrows():
            low, high = row['Low'], row['High']

            # Check SL first (trailing)
            if low <= trailing_sl:
                sl_hit = True
                exit_price = trailing_sl
                if tp2_hit:
                    exit_reason = "Trail (TP2→)"
                elif tp1_hit:
                    exit_reason = "Trail (TP1→)"
                else:
                    exit_reason = "SL"
                break

            # Track TPs and move trailing stop
            if high >= tp1 and not tp1_hit:
                tp1_hit = True
                trailing_sl = entry  # Move to breakeven after TP1

            if high >= tp2 and not tp2_hit:
                tp2_hit = True
                trailing_sl = tp1  # Move to TP1 after TP2

            if high >= tp3 and not tp3_hit:
                tp3_hit = True
                exit_price = tp3
                exit_reason = "TP3"
                break

        # Final exit status
        if tp3_hit:
            exit_reason = "TP3"
            exit_price = tp3
        elif not sl_hit:
            # Timeout — use trailing SL position to determine exit
            if tp2_hit:
                exit_reason = "Timeout (TP2+)"
            elif tp1_hit:
                exit_reason = "Timeout (TP1+)"

        pnl = ((exit_price - entry) / entry) * 100
        win = tp1_hit or tp2_hit or tp3_hit

        result = {
            'date': backtest_date, 'entry': entry, 'exit': exit_price,
            'pnl': pnl, 'win': win, 'reason': exit_reason,
            'sl_hit': sl_hit, 'tp1': tp1_hit, 'tp2': tp2_hit, 'tp3': tp3_hit,
            'rr_ratio': plan.get('rr_ratio', 0),
        }
        results.append(result)
        last_entry_price = entry

        # Save charts for notable trades
        save_chart = charts_saved < MAX_CHARTS and (tp3_hit or sl_hit)
        if save_chart:
            charts_saved += 1
            analyzer.detect_swing_points()
            analyzer.detect_order_blocks()
            analyzer.detect_equal_highs_lows()
            analyzer.detect_fair_value_gaps()

            try:
                before_html = analyzer.generate_chart_html()
                analyzer_after.detect_swing_points()
                analyzer_after.detect_order_blocks()
                analyzer_after.detect_equal_highs_lows()
                analyzer_after.detect_fair_value_gaps()
                after_html = analyzer_after.generate_chart_html()
            except Exception:
                before_html = after_html = "<html><body>Chart error</body></html>"

            outcome_label = f"{'✅ WIN' if win else '❌ LOSS'} - {exit_reason}"
            outcome_color = "#4caf50" if win else "#ef5350"

            combined_html = f'''<!DOCTYPE html>
<html>
<head>
    <title>{SYMBOL} {backtest_date} - {exit_reason}</title>
    <style>
        body {{ background: #0a0a0a; color: #d1d4dc;
               font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               margin: 0; padding: 20px; }}
        .header {{ text-align: center; padding: 20px;
                   border-bottom: 2px solid {outcome_color}; margin-bottom: 20px; }}
        .header h1 {{ color: {outcome_color}; margin: 0 0 10px 0; font-size: 28px; }}
        .stats {{ display: flex; justify-content: center; gap: 30px; font-size: 16px; }}
        .stat {{ padding: 5px 15px; background: #1a1a2e; border-radius: 5px; }}
        .panel {{ margin-bottom: 30px; border: 1px solid #363c4e;
                  border-radius: 8px; overflow: hidden; }}
        .panel-header {{ background: #1a1a2e; padding: 10px 20px;
                         font-size: 18px; font-weight: bold; }}
        .panel iframe {{ width: 100%; height: 500px; border: none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{outcome_label}</h1>
        <div class="stats">
            <div class="stat">📅 {backtest_date}</div>
            <div class="stat">💰 Entry: ${entry:.2f}</div>
            <div class="stat">🎯 Exit: ${exit_price:.2f}</div>
            <div class="stat" style="color: {"#4caf50" if pnl >= 0 else "#ef5350"}">P&L: {pnl:+.2f}%</div>
        </div>
    </div>
    <div class="panel">
        <div class="panel-header">📊 SETUP (Before Entry)</div>
        <iframe srcdoc="{before_html.replace('"', '&quot;')}"></iframe>
    </div>
    <div class="panel">
        <div class="panel-header">📈 OUTCOME (+{DAYS_AFTER} days)</div>
        <iframe srcdoc="{after_html.replace('"', '&quot;')}"></iframe>
    </div>
</body>
</html>'''

            status = "WIN" if win else "LOSS"
            filename = f"{charts_saved:02d}_{backtest_date}_{status}_{exit_reason.replace(' ', '_')}.html"
            with open(os.path.join(OUTPUT_DIR, "charts", filename), 'w') as f:
                f.write(combined_html)

        # Progress every 50 trades
        if (i + 1) % 50 == 0:
            wins = sum(r['win'] for r in results)
            print(f"  [{i+1}/{len(dates)}] {len(results)} valid | Win: {wins}/{len(results)} | Charts: {charts_saved}")

        del analyzer, analyzer_after, outcome_df
        gc.collect()

    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"⚠️ {backtest_date}: {str(e)[:60]}")

# ============ Summary ============
print("\n" + "=" * 60)
total = len(results)
if total > 0:
    wins = sum(r['win'] for r in results)
    sl_count = sum(r['sl_hit'] for r in results)
    t1 = sum(r['tp1'] for r in results)
    t2 = sum(r['tp2'] for r in results)
    t3 = sum(r['tp3'] for r in results)
    avg_pnl = sum(r['pnl'] for r in results) / total
    pnls = [r['pnl'] for r in results]

    # Sharpe ratio (annualized, assuming daily trades)
    if np.std(pnls) > 0:
        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(252)
    else:
        sharpe = 0

    # Max drawdown
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    # Profit factor
    gross_profit = sum(r['pnl'] for r in results if r['pnl'] > 0)
    gross_loss = abs(sum(r['pnl'] for r in results if r['pnl'] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    print(f"📈 {SYMBOL} DAILY BACKTEST COMPLETE (Trailing Stop)")
    print(f"   Trades: {total} | Win Rate: {wins/total*100:.1f}% | Avg P&L: {avg_pnl:+.2f}%")
    print(f"   SL: {sl_count} ({sl_count/total*100:.0f}%)")
    print(f"   TP1: {t1} ({t1/total*100:.0f}%) | TP2: {t2} ({t2/total*100:.0f}%) | TP3: {t3} ({t3/total*100:.0f}%)")
    print(f"   Sharpe: {sharpe:.2f} | Max DD: {max_dd:.2f}% | Profit Factor: {profit_factor:.2f}")
    print(f"   📊 Charts saved: {charts_saved}")
    print(f"   ⚠️ Errors: {errors}")

    # Save summary
    with open(os.path.join(OUTPUT_DIR, "summary.txt"), 'w') as f:
        f.write(f"{SYMBOL} Daily Backtest — Trailing Stop\n{'='*50}\n")
        f.write(f"Trades: {total} | Win Rate: {wins/total*100:.1f}% | Avg P&L: {avg_pnl:+.2f}%\n")
        f.write(f"SL: {sl_count} | TP1: {t1} | TP2: {t2} | TP3: {t3}\n")
        f.write(f"Sharpe: {sharpe:.2f} | Max DD: {max_dd:.2f}% | Profit Factor: {profit_factor:.2f}\n\n")
        f.write("TRADES:\n" + "-"*50 + "\n")
        for r in results:
            icon = "✓" if r['win'] else "✗"
            f.write(f"{icon} {r['date']}: ${r['entry']:.2f}→${r['exit']:.2f} ({r['pnl']:+.1f}%) {r['reason']}\n")

    # Save CSV
    csv_path = os.path.join(OUTPUT_DIR, "results.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'entry', 'exit', 'pnl', 'win', 'reason',
                                                'sl_hit', 'tp1', 'tp2', 'tp3', 'rr_ratio'])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n📄 {OUTPUT_DIR}/summary.txt")
    print(f"📊 {csv_path}")
else:
    print("❌ No valid trades completed")
