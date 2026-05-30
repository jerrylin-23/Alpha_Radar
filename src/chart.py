"""
Chart HTML generation for ICT analysis.
Produces self-contained TradingView Lightweight Charts HTML with sidebar.
Extracted from ict_analyzer.py for separation of concerns.
"""

import json
import pandas as pd


def generate_chart_html(
    df: pd.DataFrame,
    symbol: str,
    fvgs: list,
    eq_levels: dict,
    trade_plan: dict,
    analysis_summary: str,
    earnings_vwap: list = None,
    show_fvgs: bool = True,
    max_fvgs: int = 2,
    max_levels: int = 2,
) -> str:
    """
    Generate interactive TradingView Lightweight Chart HTML.

    Args:
        df: OHLCV DataFrame (must have swing_high / swing_low columns).
        symbol: Ticker symbol.
        fvgs: List of FVG dicts from detect_fair_value_gaps().
        eq_levels: Dict with 'highs' and 'lows' from detect_equal_highs_lows().
        trade_plan: Dict from calculate_trade_plan().
        analysis_summary: HTML-formatted summary string.
        earnings_vwap: Optional list of {time, value} for ER VWAP line.
        show_fvgs: Whether to render FVG lines.
        max_fvgs: Max number of FVG lines to show.
        max_levels: Max number of EQH/EQL levels to show.

    Returns:
        Self-contained HTML string.
    """
    view_df = df.tail(1500).copy()
    current_price = float(view_df['Close'].iloc[-1])
    last_candle_time = int(view_df.index[-1].timestamp())
    threshold_pct = 0.03  # Only show levels within 3% of current price

    # --- Candle data ---
    candle_data = [
        {
            'time': int(idx.timestamp()),
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close']),
        }
        for idx, row in view_df.iterrows()
    ]

    # --- FVG lines ---
    fvg_lines = []
    if show_fvgs and fvgs:
        recent_fvgs = [f for f in fvgs if not f.get('filled', False)]
        relevant_fvgs = [
            f for f in recent_fvgs
            if abs(((f['top'] + f['bottom']) / 2) - current_price) / current_price <= threshold_pct
        ]
        relevant_fvgs.sort(key=lambda x: abs(((x['top'] + x['bottom']) / 2) - current_price))
        for f in relevant_fvgs[:max_fvgs]:
            midpoint = (f['top'] + f['bottom']) / 2
            color = '#ffeb3b' if f['type'] == 'bullish' else '#ff9800'
            title = "BULL GAP" if f['type'] == 'bullish' else "BEAR GAP"
            start_time = int(f['date'].timestamp())
            fvg_lines.append({
                'price': midpoint, 'color': color, 'title': title,
                'start_time': start_time, 'end_time': last_candle_time,
            })

    # --- EQH / EQL level lines ---
    level_lines = _build_level_lines(df, eq_levels, current_price, max_levels)

    # --- Trade plan lines ---
    plan = trade_plan
    trade_lines = [
        {'price': plan['entry'], 'color': '#4caf50', 'title': 'ENTRY', 'style': 2},
        {'price': plan['sl'],    'color': '#ef5350', 'title': 'STOP',  'style': 0},
        {'price': plan['tp1'],   'color': '#2196f3', 'title': 'TP1',   'style': 2},
        {'price': plan['tp2'],   'color': '#2196f3', 'title': 'TP2',   'style': 2},
        {'price': plan['tp3'],   'color': '#2196f3', 'title': 'TP3',   'style': 2},
    ]

    # --- Trade plan sidebar HTML ---
    tp_html = f"""
    <div style="margin-top: 15px; border-top: 1px solid #363c4e; padding-top: 10px;">
        <h3 style="color: #4caf50; margin-bottom: 5px;">🚀 BULLISH SETUP</h3>
        <div style="font-size: 13px; color: #d1d4dc;">
            <div><strong>Entry:</strong> <span style="color: #4caf50;">${plan['entry']:.2f}</span> ({plan['type']})</div>
            <div><strong>Stop Loss:</strong> <span style="color: #ef5350;">${plan['sl']:.2f}</span></div>
            <div style="margin-top: 5px;"><strong>Targets:</strong></div>
            <div>🎯 TP1: <span style="color: #2196f3;">${plan['tp1']:.2f}</span></div>
            <div>🎯 TP2: <span style="color: #2196f3;">${plan['tp2']:.2f}</span></div>
            <div>🚀 TP3: <span style="color: #2196f3;">${plan['tp3']:.2f}</span></div>
        </div>
    </div>
    """
    if plan.get('rr_ratio') is not None:
        tp_html += f'<div style="font-size:12px;color:#787b86;margin-top:5px;">R:R = 1:{plan["rr_ratio"]:.1f}</div>'
    summary_html = analysis_summary + tp_html

    # --- Stats for sidebar ---
    num_fvgs = len(fvgs) if fvgs else 0
    num_levels = len(eq_levels.get('highs', [])) + len(eq_levels.get('lows', []))

    # --- Serialize ---
    chart_data = json.dumps({
        'candles': candle_data,
        'fvg_lines': fvg_lines,
        'level_lines': level_lines,
        'trade_lines': trade_lines,
        'earnings_vwap': earnings_vwap or [],
        'symbol': symbol,
        'width': 800,
        'height': 600,
    }, default=str)

    # --- HTML template ---
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{symbol} ICT Analysis</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ background: #0a0a0a; color: #d1d4dc; font-family: -apple-system, sans-serif; margin: 0; display: flex; height: 100vh; }}
            #chart-container {{ flex: 1; position: relative; }}
            #sidebar {{ width: 280px; background: #1a1a2e; padding: 20px; border-left: 1px solid #363c4e; overflow-y: auto; box-shadow: -2px 0 10px rgba(0,0,0,0.3); }}
            h2 {{ color: #2196f3; margin-top: 0; font-size: 20px; }}
            h3 {{ color: #a0a0a0; font-size: 14px; margin-top: 20px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #363c4e; padding-bottom: 5px; }}
            .stat-item {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }}
            .bullish {{ color: #4caf50; }}
            .bearish {{ color: #ef5350; }}
            .legend {{ position: absolute; top: 12px; left: 12px; z-index: 10; font-size: 24px; font-weight: bold; color: rgba(255, 255, 255, 0.7); }}
        </style>
    </head>
    <body>
        <div id="chart-container">
            <div class="legend">{symbol} 4H</div>
        </div>

        <div id="sidebar">
            <h2>📊 Analysis Summary</h2>
            <div style="font-size: 13px; line-height: 1.6;">
                {summary_html}
            </div>

            <h3>Key Levels Found</h3>
            <div class="stat-item">
                <span>Fair Value Gaps:</span>
                <span>{num_fvgs}</span>
            </div>
            <div class="stat-item">
                <span>EQH/EQL Zones:</span>
                <span>{num_levels}</span>
            </div>

        </div>

        <script>
            try {{
                const data = {chart_data};

                if (!data.candles || data.candles.length === 0) {{
                    document.getElementById('chart-container').innerHTML = '<div style="color:white;text-align:center;padding:20px;">No candle data available</div>';
                    throw new Error("No data");
                }}

                const chartContainer = document.getElementById('chart-container');
                const chart = LightweightCharts.createChart(chartContainer, {{
                    layout: {{ background: {{ type: 'solid', color: '#0a0a0a' }}, textColor: '#d1d4dc' }},
                    grid: {{ vertLines: {{ color: '#1f2937' }}, horzLines: {{ color: '#1f2937' }} }},
                    rightPriceScale: {{ borderColor: '#363c4e' }},
                    timeScale: {{ borderColor: '#363c4e', timeVisible: true }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                }});

                const candlestickSeries = chart.addCandlestickSeries({{
                    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350'
                }});
                candlestickSeries.setData(data.candles);

                const markers = [];

                if (data.fvg_lines) {{
                    data.fvg_lines.forEach(line => {{
                        const fvgSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: 2,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false, lastValueVisible: false,
                            title: line.title, crosshairMarkerVisible: false
                        }});
                        const lineData = [];
                        data.candles.forEach(c => {{
                            if (c.time >= line.start_time) {{ lineData.push({{ time: c.time, value: line.price }}); }}
                        }});
                        if (lineData.length > 0) fvgSeries.setData(lineData);
                    }});
                }}

                candlestickSeries.setMarkers(markers);

                if (data.level_lines) {{
                    data.level_lines.forEach(line => {{
                        const levelSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: line.lineWidth || 1,
                            lineStyle: line.lineStyle || LightweightCharts.LineStyle.Dashed,
                            priceLineVisible: false, lastValueVisible: false, title: line.title
                        }});
                        const lineData = data.candles.map(c => ({{ time: c.time, value: line.price }}));
                        levelSeries.setData(lineData);
                    }});
                }}

                if (data.trade_lines) {{
                    data.trade_lines.forEach(line => {{
                        const isKey = line.title === 'ENTRY' || line.title === 'STOP';
                        const tradeSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: 2,
                            lineStyle: line.style === 2 ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                            priceLineVisible: isKey, lastValueVisible: isKey, title: line.title
                        }});
                        const recentCandles = data.candles.slice(-100);
                        const lineData = recentCandles.map(c => ({{ time: c.time, value: line.price }}));
                        tradeSeries.setData(lineData);
                    }});
                }}

                if (data.earnings_vwap && data.earnings_vwap.length > 0) {{
                    const vwapSeries = chart.addLineSeries({{
                        color: '#b39ddb', lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Solid,
                        title: 'Earnings VWAP', priceLineVisible: false
                    }});
                    vwapSeries.setData(data.earnings_vwap);
                }}

                const lastTime = data.candles[data.candles.length - 1].time;
                const startTime = data.candles[Math.max(0, data.candles.length - 100)].time;
                chart.timeScale().setVisibleRange({{ from: startTime, to: lastTime }});

                window.addEventListener('resize', () => {{
                    chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
                }});

            }} catch (e) {{
                console.error("Chart Error:", e);
                document.body.innerHTML += '<div style="position:absolute;top:10px;left:10px;color:red;background:rgba(0,0,0,0.8);padding:10px;">JS Error: ' + e.message + '</div>';
            }}
        </script>
    </body>
    </html>
    """
    return html


def _build_level_lines(df: pd.DataFrame, eq_levels: dict, current_price: float, max_levels: int) -> list:
    """Build the EQH/EQL level lines with fallbacks to swing highs/lows."""
    all_levels = []
    if eq_levels:
        for eqh in eq_levels.get('highs', []):
            all_levels.append({'price': eqh['price'], 'type': 'EQH', 'color': '#ef5350'})
        for eql in eq_levels.get('lows', []):
            all_levels.append({'price': eql['price'], 'type': 'EQL', 'color': '#26a69a'})

    valid_eqh = sorted([l for l in all_levels if l['type'] == 'EQH' and l['price'] > current_price],
                        key=lambda x: abs(x['price'] - current_price))
    valid_eql = sorted([l for l in all_levels if l['type'] == 'EQL' and l['price'] < current_price],
                        key=lambda x: abs(x['price'] - current_price))

    forced_levels = []

    # Ensure at least one resistance
    if valid_eqh:
        forced_levels.append(valid_eqh[0])
    elif 'swing_high' in df.columns:
        swing_highs = df[df['swing_high']]
        highs_above = swing_highs[swing_highs['High'] > current_price]
        if not highs_above.empty:
            nearest = highs_above.iloc[(highs_above['High'] - current_price).abs().argsort()[:1]]
            forced_levels.append({'price': float(nearest['High'].iloc[0]), 'type': 'Swing High', 'color': '#ef5350'})
        else:
            recent = df.iloc[-300:]
            rh = recent[recent['High'] > current_price]
            if not rh.empty:
                forced_levels.append({'price': float(rh['High'].max()), 'type': 'Recent High', 'color': '#ef5350'})

    # Ensure at least one support
    if valid_eql:
        forced_levels.append(valid_eql[0])
    elif 'swing_low' in df.columns:
        swing_lows = df[df['swing_low']]
        lows_below = swing_lows[swing_lows['Low'] < current_price]
        if not lows_below.empty:
            nearest = lows_below.iloc[(current_price - lows_below['Low']).abs().argsort()[:1]]
            forced_levels.append({'price': float(nearest['Low'].iloc[0]), 'type': 'Swing Low', 'color': '#26a69a'})
        else:
            recent = df.iloc[-300:]
            rl = recent[recent['Low'] < current_price]
            if not rl.empty:
                forced_levels.append({'price': float(rl['Low'].min()), 'type': 'Recent Low', 'color': '#26a69a'})

    # Deduplicate and pick top N by distance
    seen_prices = set()
    final_pool = []
    for l in forced_levels + valid_eqh + valid_eql:
        if l['price'] not in seen_prices:
            final_pool.append(l)
            seen_prices.add(l['price'])
    final_pool.sort(key=lambda x: abs(x['price'] - current_price))

    level_lines = []
    for lvl in final_pool[:max_levels]:
        role = "Res" if lvl['price'] > current_price else "Sup"
        level_lines.append({
            'price': lvl['price'], 'color': lvl['color'],
            'title': f"{lvl['type']} ({role})",
            'lineWidth': 1, 'lineStyle': 2, 'axisLabelVisible': True,
        })
    return level_lines
