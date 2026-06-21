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
            color = '#4ebe96' if f['type'] == 'bullish' else '#ffa16c'
            title = 'Demand gap' if f['type'] == 'bullish' else 'Supply gap'
            start_time = int(f['date'].timestamp())
            fvg_lines.append({
                'price': midpoint, 'color': color, 'title': title,
                'start_time': start_time, 'end_time': last_candle_time,
            })

    # --- Structure context: enforce a one-line annotation budget ---
    # The trade plan owns the chart. Nearby FVG/EQH/EQL context is useful, but
    # showing several of each makes the candle read impossible.
    level_lines = _build_level_lines(df, eq_levels, current_price, 1)
    context_candidates = []
    for line in fvg_lines:
        context_candidates.append(('fvg', line, abs(line['price'] - current_price)))
    for line in level_lines:
        context_candidates.append(('level', line, abs(line['price'] - current_price)))
    context_candidates.sort(key=lambda item: item[2])

    if context_candidates:
        context_type, context_line, _ = context_candidates[0]
        fvg_lines = [context_line] if context_type == 'fvg' else []
        level_lines = [context_line] if context_type == 'level' else []
    else:
        fvg_lines = []
        level_lines = []

    # --- Trade plan lines ---
    plan = trade_plan
    trade_lines = [
        {'price': plan['entry'], 'color': '#4caf50', 'title': 'ENTRY', 'style': 2, 'width': 2},
        {'price': plan['sl'],    'color': '#ef5350', 'title': 'STOP',  'style': 0, 'width': 2},
        {'price': plan['tp1'],   'color': '#479ffa', 'title': 'T1',    'style': 2, 'width': 1},
        {'price': plan['tp2'],   'color': '#479ffa', 'title': 'T2',    'style': 2, 'width': 1},
        {'price': plan['tp3'],   'color': '#479ffa', 'title': 'T3',    'style': 2, 'width': 1},
    ]

    # --- Trade brief sidebar HTML ---
    setup_label = 'Long setup' if plan.get('valid') else 'Watch setup'
    setup_detail = plan['type'].replace('Limit Buy ', '').replace('Aggressive ', '')
    rr_value = f"{plan['rr_ratio']:.1f}R" if plan.get('rr_ratio') is not None else '—'
    chart_plan_note = (
        f"Entry ${plan['entry']:.2f} · Invalidate ${plan['sl']:.2f} · "
        f"First target ${plan['tp1']:.2f}"
    )
    tp_html = f"""
    <section class="trade-card">
        <div class="trade-card-header">
            <div>
                <span class="panel-eyebrow">Trade plan</span>
                <h2>{setup_label}</h2>
                <p>{setup_detail}</p>
            </div>
            <span class="rr-chip">{rr_value}<small>to TP1</small></span>
        </div>
        <div class="plan-grid">
            <div><span>Entry</span><strong class="entry-value">${plan['entry']:.2f}</strong></div>
            <div><span>Invalidation</span><strong class="stop-value">${plan['sl']:.2f}</strong></div>
        </div>
        <div class="targets">
            <span class="targets-label">Targets</span>
            <div><span>01</span><strong>${plan['tp1']:.2f}</strong></div>
            <div><span>02</span><strong>${plan['tp2']:.2f}</strong></div>
            <div><span>03</span><strong>${plan['tp3']:.2f}</strong></div>
        </div>
    </section>
    """
    summary_html = (
        tp_html
        + '<section class="market-map"><div class="market-map-header">'
        + '<span class="panel-eyebrow">Market map</span><span>Nearest structure</span>'
        + f'</div>{analysis_summary}</section>'
    )

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
            body {{ background: #0b0b0b; color: #ffffff; font-family: Inter Tight, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; display: flex; height: 100vh; letter-spacing: -0.03em; }}
            #chart-container {{ flex: 1; position: relative; }}
            #sidebar {{ flex: 0 0 clamp(370px, 29vw, 420px); background: #131313; border-left: 1px solid #303030; overflow-y: auto; }}
            .trade-card {{ padding: 28px 26px 22px; background: #191919; border-bottom: 1px solid #303030; }}
            .trade-card-header {{ display: flex; justify-content: space-between; gap: 15px; align-items: flex-start; }}
            .panel-eyebrow {{ display: block; color: #ffa16c; font-size: 11px; font-weight: 600; margin-bottom: 7px; }}
            .trade-card h2 {{ margin: 0; color: #ffffff; font-size: 23px; line-height: .95; letter-spacing: -0.08em; font-weight: 600; }}
            .trade-card p {{ margin: 7px 0 0; color: #868f97; font-size: 12px; }}
            .rr-chip {{ min-width: 45px; padding: 7px 6px; border: 1px solid #4ebe96; border-radius: 6px; color: #4ebe96; text-align: center; font-size: 14px; font-weight: 600; }}
            .rr-chip small {{ display: block; margin-top: 2px; color: #868f97; font-size: 9px; font-weight: 500; }}
            .plan-grid {{ display: grid; grid-template-columns: 1fr 1fr; margin-top: 22px; border: 1px solid #303030; border-radius: 6px; overflow: hidden; }}
            .plan-grid div {{ padding: 13px 14px; }} .plan-grid div + div {{ border-left: 1px solid #303030; }}
            .plan-grid span, .targets-label {{ display: block; color: #868f97; font-size: 10px; }}
            .plan-grid strong {{ display: block; margin-top: 4px; font-size: 15px; letter-spacing: -0.05em; }}
            .entry-value {{ color: #4ebe96; }} .stop-value {{ color: #c8746a; }}
            .targets {{ margin-top: 19px; }} .targets-label {{ margin-bottom: 8px; }}
            .targets div {{ display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-top: 1px solid #303030; }}
            .targets div span {{ color: #868f97; font-size: 10px; }} .targets div strong {{ color: #ffffff; font-size: 14px; font-weight: 500; }}
            .market-map {{ padding: 25px 26px 30px; }}
            .market-map-header {{ display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }}
            .market-map-header .panel-eyebrow {{ margin: 0; }} .market-map-header > span:last-child {{ color: #868f97; font-size: 10px; }}
            .market-level {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 10px 0; border-top: 1px solid #303030; }}
            .market-level-label {{ color: #cccccc; font-size: 12px; }}
            .market-level-value {{ color: #ffffff; text-align: right; font-size: 13px; font-weight: 600; }}
            .market-level-value small {{ display: block; margin-top: 2px; color: #868f97; font-size: 10px; font-weight: 400; }}
            .market-level.resistance .market-level-value {{ color: #c8746a; }}
            .market-level.warning .market-level-value {{ color: #ffa16c; }}
            .market-level.support .market-level-value {{ color: #4ebe96; }}
            .market-level.reference .market-level-value {{ color: #479ffa; }}
            .market-level-empty {{ margin: 0; padding: 12px 0; color: #868f97; font-size: 12px; border-top: 1px solid #303030; }}
            #er-vertical-line {{ position: absolute; top: 0; bottom: 27px; width: 0; border-left: 1px dashed rgba(255, 255, 255, 0.18); pointer-events: none; z-index: 1; display: none; }}
            #er-axis-label {{ position: absolute; bottom: 5px; z-index: 12; display: none; transform: translateX(-50%); padding: 2px 5px; border-radius: 3px; background: #ffa16c; color: #0b0b0b; font-size: 9px; font-weight: 700; pointer-events: none; }}
            #target-ladder {{ position: absolute; top: 0; right: 55px; bottom: 27px; z-index: 11; pointer-events: none; }}
            .target-ladder-item {{ position: absolute; right: 0; min-width: 72px; padding: 3px 6px; border: 1px solid rgba(71,159,250,.6); border-radius: 4px; background: rgba(11,11,11,.92); color: #d9ebff; font-size: 10px; text-align: right; white-space: nowrap; }}
            .target-ladder-item strong {{ margin-right: 4px; color: #479ffa; font-size: 9px; }}
            @media (max-width: 920px) {{ #sidebar {{ flex-basis: 340px; }} .trade-card {{ padding: 21px 18px 18px; }} .market-map {{ padding: 21px 18px 24px; }} }}
            
            /* Floating HUD styles */
            .chart-hud {{
                position: absolute;
                top: 15px;
                left: 15px;
                z-index: 10;
                pointer-events: none;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .hud-header {{
                display: flex;
                align-items: baseline;
                gap: 6px;
            }}
            .hud-symbol {{
                font-size: 22px;
                font-weight: 700;
                color: #ffffff;
                text-shadow: 0 2px 4px rgba(0,0,0,0.5);
            }}
            .hud-tf {{
                font-size: 11px;
                font-weight: 600;
                color: #8f94a0;
                background: rgba(255, 255, 255, 0.1);
                padding: 1px 6px;
                border-radius: 3px;
            }}
            .hud-plan {{
                display: flex;
                align-items: center;
                gap: 8px;
                color: #b7bcc4;
                font-size: 11px;
                text-shadow: 0 1px 2px rgba(0,0,0,.8);
            }}
            .hud-plan strong {{ color: #4ebe96; font-size: 10px; letter-spacing: .02em; text-transform: uppercase; }}
            .hud-legend {{
                display: none;
                flex-wrap: wrap;
                gap: 6px;
                max-width: 550px;
            }}
            .hud-badge {{
                font-size: 11px;
                font-weight: 500;
                padding: 4px 8px;
                border-radius: 4px;
                backdrop-filter: blur(8px);
                background: rgba(26, 26, 46, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                display: flex;
                align-items: center;
                gap: 5px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            }}
        </style>
    </head>
    <body>
        <div id="chart-container">
            <div class="chart-hud">
                <div class="hud-header">
                    <span class="hud-symbol">{symbol}</span>
                    <span class="hud-tf">4H</span>
                </div>
                <div class="hud-plan"><strong>{setup_label}</strong><span>{chart_plan_note}</span></div>
                <div class="hud-legend" id="hud-legend"></div>
            </div>
            <div id="er-vertical-line"></div>
            <div id="er-axis-label">E</div>
            <div id="target-ladder"></div>
        </div>

        <aside id="sidebar">{summary_html}</aside>

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
                let updateErLinePosition = () => {{}};
                let updateTargetLadder = () => {{}};
                if (data.earnings_vwap && data.earnings_vwap.length > 0) {{
                    const erTime = data.earnings_vwap[0].time;
                    const erLineDiv = document.getElementById('er-vertical-line');
                    const erAxisLabel = document.getElementById('er-axis-label');
                    updateErLinePosition = () => {{
                        const erCoordinate = chart.timeScale().timeToCoordinate(erTime);
                        if (erCoordinate === null) {{
                            erLineDiv.style.display = 'none';
                            erAxisLabel.style.display = 'none';
                        }} else {{
                            erLineDiv.style.display = 'block';
                            erLineDiv.style.left = erCoordinate + 'px';
                            erAxisLabel.style.display = 'block';
                            erAxisLabel.style.left = erCoordinate + 'px';
                        }}
                    }};

                    chart.timeScale().subscribeVisibleLogicalRangeChange(updateErLinePosition);
                    chart.timeScale().subscribeVisibleTimeRangeChange(updateErLinePosition);
                    setTimeout(updateErLinePosition, 100);
                }}
                const seriesRegistry = [];

                const registerSeries = (id, title, price, color, seriesObj, originalWidth, isLevelLine = false) => {{
                    seriesRegistry.push({{
                        id: id,
                        title: title,
                        price: price,
                        color: color,
                        series: seriesObj,
                        originalWidth: originalWidth,
                        isLevelLine: isLevelLine,
                        badgeElement: null
                    }});
                }};

                if (data.fvg_lines) {{
                    data.fvg_lines.forEach((line, idx) => {{
                        const fvgLine = candlestickSeries.createPriceLine({{
                            price: line.price,
                            color: line.color,
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Dashed,
                            axisLabelVisible: true,
                            title: line.title,
                        }});
                        registerSeries('fvg_' + idx, line.title, line.price, line.color, fvgLine, 1, true);
                    }});
                }}

                candlestickSeries.setMarkers(markers);

                if (data.level_lines) {{
                    data.level_lines.forEach((line, idx) => {{
                        const levelLine = candlestickSeries.createPriceLine({{
                            price: line.price,
                            color: line.color,
                            lineWidth: 1,
                            lineStyle: LightweightCharts.LineStyle.Dashed,
                            axisLabelVisible: true,
                            title: line.title,
                        }});
                        registerSeries('level_' + idx, line.title, line.price, line.color, levelLine, 1, true);
                    }});
                }}

                if (data.trade_lines) {{
                    data.trade_lines.forEach((line, idx) => {{
                        if (line.title === 'T2' || line.title === 'T3') return;
                        const tradeLabel = line.title === 'T1' ? 'Target 1' : line.title.charAt(0) + line.title.slice(1).toLowerCase();
                        const tradeLine = candlestickSeries.createPriceLine({{
                            price: line.price,
                            color: line.color,
                            lineWidth: line.width || 2,
                            lineStyle: line.style === 2 ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                            axisLabelVisible: true,
                            title: tradeLabel,
                        }});
                        registerSeries('trade_' + idx, line.title, line.price, line.color, tradeLine, line.width || 2);
                    }});

                    const targetLadder = document.getElementById('target-ladder');
                    const overheadTargets = data.trade_lines.filter(line => line.title === 'T2' || line.title === 'T3');
                    updateTargetLadder = () => {{
                        targetLadder.innerHTML = '';
                        const positions = overheadTargets
                            .map(line => ({{ line, y: candlestickSeries.priceToCoordinate(line.price) }}))
                            .filter(item => item.y !== null)
                            .sort((a, b) => a.y - b.y);
                        let previousTop = -Infinity;
                        const maxTop = Math.max(18, chartContainer.clientHeight - 54);
                        positions.forEach(item => {{
                            let top = Math.max(18, item.y - 10);
                            if (top < previousTop + 24) top = previousTop + 24;
                            top = Math.min(top, maxTop);
                            previousTop = top;
                            const marker = document.createElement('div');
                            marker.className = 'target-ladder-item';
                            marker.style.top = top + 'px';
                            marker.innerHTML = '<strong>' + item.line.title + '</strong>$' + Number(item.line.price).toFixed(2);
                            targetLadder.appendChild(marker);
                        }});
                    }};
                    chart.timeScale().subscribeVisibleLogicalRangeChange(updateTargetLadder);
                    setTimeout(updateTargetLadder, 120);
                }}

                if (data.earnings_vwap && data.earnings_vwap.length > 0) {{
                    const vwapSeries = chart.addLineSeries({{
                        color: '#b39ddb', lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Solid,
                        priceLineVisible: false, lastValueVisible: false,
                        crosshairMarkerVisible: false
                    }});
                    vwapSeries.setData(data.earnings_vwap);
                    const lastVwap = data.earnings_vwap[data.earnings_vwap.length - 1].value;
                    registerSeries('vwap', 'ER VWAP', lastVwap, '#b39ddb', vwapSeries, 2);
                }}

                // Highlights State Management
                let activeHighlightId = null;
                let activeHoverId = null;

                const toggleHighlight = (id) => {{
                    if (activeHighlightId === id) {{
                        clearHighlights();
                    }} else {{
                        highlightSeries(id);
                    }}
                }};

                const highlightSeries = (id) => {{
                    activeHighlightId = id;
                    activeHoverId = null;
                    
                    seriesRegistry.forEach(item => {{
                        const isTarget = item.id === id;
                        
                        item.series.applyOptions({{
                            lineWidth: isTarget ? (item.originalWidth + 2) : 1,
                            lineStyle: isTarget ? LightweightCharts.LineStyle.Solid : LightweightCharts.LineStyle.Dashed
                        }});

                        if (item.badgeElement) {{
                            if (isTarget) {{
                                item.badgeElement.style.background = 'rgba(255, 255, 255, 0.2)';
                                item.badgeElement.style.borderColor = item.color;
                                item.badgeElement.style.boxShadow = '0 0 10px ' + item.color + '40';
                                item.badgeElement.style.transform = 'scale(1.05)';
                                item.badgeElement.style.opacity = '1';
                            }} else {{
                                item.badgeElement.style.background = 'rgba(26, 26, 46, 0.3)';
                                item.badgeElement.style.opacity = '0.3';
                                item.badgeElement.style.transform = 'scale(0.95)';
                                item.badgeElement.style.borderColor = 'rgba(255, 255, 255, 0.04)';
                                item.badgeElement.style.boxShadow = 'none';
                            }}
                        }}
                    }});
                }};

                const clearHighlights = () => {{
                    activeHighlightId = null;
                    activeHoverId = null;
                    
                    seriesRegistry.forEach(item => {{
                        item.series.applyOptions({{
                            lineWidth: item.originalWidth,
                            lineStyle: item.isLevelLine || (item.id.startsWith('trade_') && item.title !== 'ENTRY' && item.title !== 'STOP')
                                ? LightweightCharts.LineStyle.Dashed
                                : LightweightCharts.LineStyle.Solid
                        }});

                        if (item.badgeElement) {{
                            item.badgeElement.style.background = 'rgba(26, 26, 46, 0.75)';
                            item.badgeElement.style.opacity = '1';
                            item.badgeElement.style.borderColor = 'rgba(255, 255, 255, 0.08)';
                            item.badgeElement.style.boxShadow = '0 4px 6px rgba(0,0,0,0.2)';
                            item.badgeElement.style.transform = 'none';
                        }}
                    }});
                }};

                const hoverHighlightSeries = (id) => {{
                    if (activeHighlightId !== null) return;
                    activeHoverId = id;
                    
                    seriesRegistry.forEach(item => {{
                        const isTarget = item.id === id;
                        item.series.applyOptions({{
                            lineWidth: isTarget ? (item.originalWidth + 2) : 1
                        }});
                        if (item.badgeElement) {{
                            if (isTarget) {{
                                item.badgeElement.style.background = 'rgba(255, 255, 255, 0.25)';
                                item.badgeElement.style.borderColor = item.color;
                                item.badgeElement.style.boxShadow = '0 0 10px ' + item.color + '40';
                                item.badgeElement.style.transform = 'scale(1.05)';
                                item.badgeElement.style.opacity = '1';
                            }} else {{
                                item.badgeElement.style.opacity = '0.4';
                                item.badgeElement.style.transform = 'scale(0.95)';
                            }}
                        }}
                    }});
                }};

                const clearHoverHighlight = () => {{
                    activeHoverId = null;
                    if (activeHighlightId !== null) return;
                    
                    seriesRegistry.forEach(item => {{
                        item.series.applyOptions({{
                            lineWidth: item.originalWidth
                        }});
                        if (item.badgeElement) {{
                            item.badgeElement.style.background = 'rgba(26, 26, 46, 0.75)';
                            item.badgeElement.style.opacity = '1';
                            item.badgeElement.style.borderColor = 'rgba(255, 255, 255, 0.08)';
                            item.badgeElement.style.boxShadow = '0 4px 6px rgba(0,0,0,0.2)';
                            item.badgeElement.style.transform = 'none';
                        }}
                    }});
                }};

                // Build dynamic glassmorphism HUD legend
                const hudLegend = document.getElementById('hud-legend');
                const addBadge = (id, label, value, color) => {{
                    const badge = document.createElement('div');
                    badge.className = 'hud-badge';
                    badge.style.borderLeft = '3px solid ' + color;
                    badge.style.cursor = 'pointer';
                    badge.style.transition = 'all 0.2s ease';
                    badge.style.pointerEvents = 'auto';
                    
                    const dot = document.createElement('span');
                    dot.style.width = '6px';
                    dot.style.height = '6px';
                    dot.style.borderRadius = '50%';
                    dot.style.backgroundColor = color;
                    
                    const text = document.createElement('span');
                    text.style.color = '#e1e4ea';
                    text.innerHTML = '<strong>' + label + '</strong>: $' + Number(value).toFixed(2);
                    
                    badge.appendChild(dot);
                    badge.appendChild(text);
                    hudLegend.appendChild(badge);

                    const registryItem = seriesRegistry.find(item => item.id === id);
                    if (registryItem) {{
                        registryItem.badgeElement = badge;
                    }}

                    badge.addEventListener('click', (e) => {{
                        e.stopPropagation();
                        toggleHighlight(id);
                    }});

                    badge.addEventListener('mouseenter', () => {{
                        badge.style.background = 'rgba(255, 255, 255, 0.15)';
                        badge.style.transform = 'translateY(-1px)';
                    }});
                    badge.addEventListener('mouseleave', () => {{
                        if (activeHighlightId !== id) {{
                            badge.style.background = 'rgba(26, 26, 46, 0.75)';
                            badge.style.transform = 'none';
                        }}
                    }});
                }};

                if (data.trade_lines) {{
                    data.trade_lines.forEach((line, idx) => {{
                        addBadge('trade_' + idx, line.title, line.price, line.color);
                    }});
                }}
                if (data.fvg_lines) {{
                    data.fvg_lines.forEach((line, idx) => {{
                        addBadge('fvg_' + idx, line.title, line.price, line.color);
                    }});
                }}
                if (data.level_lines) {{
                    data.level_lines.forEach((line, idx) => {{
                        addBadge('level_' + idx, line.title, line.price, line.color);
                    }});
                }}
                if (data.earnings_vwap && data.earnings_vwap.length > 0) {{
                    const lastVwap = data.earnings_vwap[data.earnings_vwap.length - 1].value;
                    addBadge('vwap', 'ER VWAP', lastVwap, '#b39ddb');
                }}

                // Crosshair interaction for Hover-Highlighting lines
                chart.subscribeCrosshairMove(param => {{
                    if (activeHighlightId !== null) return;
                    
                    if (!param || !param.time || !param.point) {{
                        if (activeHoverId !== null) {{
                            clearHoverHighlight();
                        }}
                        return;
                    }}

                    const price = candlestickSeries.coordinateToPrice(param.point.y);
                    if (price === null) return;

                    let closestItem = null;
                    let minDistance = Infinity;
                    
                    seriesRegistry.forEach(item => {{
                        const dist = Math.abs(item.price - price) / item.price;
                        if (dist < minDistance) {{
                            minDistance = dist;
                            closestItem = item;
                        }}
                    }});

                    // 0.2% tolerance for hovering
                    if (minDistance < 0.002) {{
                        if (activeHoverId !== closestItem.id) {{
                            hoverHighlightSeries(closestItem.id);
                        }}
                    }} else {{
                        if (activeHoverId !== null) {{
                            clearHoverHighlight();
                        }}
                    }}
                }});

                // Click interaction for Click-Highlighting lines
                chart.subscribeClick(param => {{
                    if (!param || !param.point) return;
                    const price = candlestickSeries.coordinateToPrice(param.point.y);
                    if (price === null) return;

                    let closestItem = null;
                    let minDistance = Infinity;
                    
                    seriesRegistry.forEach(item => {{
                        const dist = Math.abs(item.price - price) / item.price;
                        if (dist < minDistance) {{
                            minDistance = dist;
                            closestItem = item;
                        }}
                    }});

                    // 0.25% tolerance for clicking
                    if (minDistance < 0.0025) {{
                        toggleHighlight(closestItem.id);
                    }} else {{
                        clearHighlights();
                    }}
                }});

                const lastTime = data.candles[data.candles.length - 1].time;
                const startTime = data.candles[Math.max(0, data.candles.length - 100)].time;
                chart.timeScale().setVisibleRange({{ from: startTime, to: lastTime }});

                window.addEventListener('resize', () => {{
                    chart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
                    updateErLinePosition();
                    updateTargetLadder();
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
            all_levels.append({'price': eqh['price'], 'type': 'EQH', 'color': '#ef5350', 'indices': eqh.get('indices', [])})
        for eql in eq_levels.get('lows', []):
            all_levels.append({'price': eql['price'], 'type': 'EQL', 'color': '#26a69a', 'indices': eql.get('indices', [])})

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
            forced_levels.append({'price': float(nearest['High'].iloc[0]), 'type': 'Swing High', 'color': '#ef5350', 'indices': [nearest.index[0]]})
        else:
            recent = df.iloc[-300:]
            rh = recent[recent['High'] > current_price]
            if not rh.empty:
                forced_levels.append({'price': float(rh['High'].max()), 'type': 'Recent High', 'color': '#ef5350', 'indices': [rh['High'].idxmax()]})

    # Ensure at least one support
    if valid_eql:
        forced_levels.append(valid_eql[0])
    elif 'swing_low' in df.columns:
        swing_lows = df[df['swing_low']]
        lows_below = swing_lows[swing_lows['Low'] < current_price]
        if not lows_below.empty:
            nearest = lows_below.iloc[(current_price - lows_below['Low']).abs().argsort()[:1]]
            forced_levels.append({'price': float(nearest['Low'].iloc[0]), 'type': 'Swing Low', 'color': '#26a69a', 'indices': [nearest.index[0]]})
        else:
            recent = df.iloc[-300:]
            rl = recent[recent['Low'] < current_price]
            if not rl.empty:
                forced_levels.append({'price': float(rl['Low'].min()), 'type': 'Recent Low', 'color': '#26a69a', 'indices': [rl['Low'].idxmin()]})

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
        # Short label: just the type abbreviation
        short = lvl['type'].replace('Recent High', 'RH').replace('Recent Low', 'RL') \
                           .replace('Swing High', 'SH').replace('Swing Low', 'SL')
        
        indices = lvl.get('indices', [])
        valid_timestamps = [int(x.timestamp()) for x in indices if hasattr(x, 'timestamp')]
        if valid_timestamps:
            start_time = min(valid_timestamps)
        else:
            start_time = int(df.index[0].timestamp())

        level_lines.append({
            'price': lvl['price'], 'color': lvl['color'],
            'title': short,
            'lineWidth': 1, 'lineStyle': 2,
            'start_time': start_time,
        })
    return level_lines
