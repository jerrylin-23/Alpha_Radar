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
            title = "FVG\u2191" if f['type'] == 'bullish' else "FVG\u2193"
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
        {'price': plan['entry'], 'color': '#4caf50', 'title': 'ENTRY', 'style': 2, 'width': 2},
        {'price': plan['sl'],    'color': '#ef5350', 'title': 'STOP',  'style': 0, 'width': 2},
        {'price': plan['tp1'],   'color': '#2196f3', 'title': 'T1',    'style': 2, 'width': 1},
        {'price': plan['tp2'],   'color': '#2196f3', 'title': 'T2',    'style': 2, 'width': 1},
        {'price': plan['tp3'],   'color': '#2196f3', 'title': 'T3',    'style': 2, 'width': 1},
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
            .hud-legend {{
                display: flex;
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
                <div class="hud-legend" id="hud-legend"></div>
            </div>
            <div id="er-vertical-line" style="position: absolute; top: 0; bottom: 0; width: 0; border-left: 1px dashed rgba(255, 255, 255, 0.08); pointer-events: none; z-index: 1; display: none;"></div>
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
                if (data.earnings_vwap && data.earnings_vwap.length > 0) {{
                    const erTime = data.earnings_vwap[0].time;
                    
                    // 1. Pinned Yellow "E" Badge at the absolute bottom of the chart
                    chart.priceScale('left').applyOptions({{
                        scaleMargins: {{
                            top: 0.90, // Force series slightly up to sit beautifully inside bottom grid
                            bottom: 0.04,
                        }}
                    }});

                    const erMarkerSeries = chart.addLineSeries({{
                        priceScaleId: 'left',
                        color: 'transparent', // Invisible line
                        priceLineVisible: false,
                        lastValueVisible: false,
                        crosshairMarkerVisible: false,
                    }});
                    erMarkerSeries.setData([
                        {{ time: erTime, value: 0 }}
                    ]);
                    erMarkerSeries.setMarkers([
                        {{
                            time: erTime,
                            position: 'inBar', // Places it directly on the value 0 line at the bottom
                            color: '#f59e0b',  // TV yellow
                            shape: 'circle',
                            text: 'E',
                            size: 1.2
                        }}
                    ]);

                    // 3. TV-style thin dashed vertical line going straight up (updates dynamically on scroll/zoom)
                    const erLineDiv = document.getElementById('er-vertical-line');
                    const updateErLinePosition = () => {{
                        const erCoordinate = chart.timeScale().timeToCoordinate(erTime);
                        if (erCoordinate === null) {{
                            erLineDiv.style.display = 'none';
                        }} else {{
                            erLineDiv.style.display = 'block';
                            erLineDiv.style.left = erCoordinate + 'px';
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
                        const fvgSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: 2,
                            lineStyle: LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false, lastValueVisible: false,
                            crosshairMarkerVisible: false
                        }});
                        const lineData = [];
                        data.candles.forEach(c => {{
                            if (c.time >= line.start_time) {{ lineData.push({{ time: c.time, value: line.price }}); }}
                        }});
                        if (lineData.length > 0) fvgSeries.setData(lineData);
                        registerSeries('fvg_' + idx, line.title, line.price, line.color, fvgSeries, 2);
                    }});
                }}

                candlestickSeries.setMarkers(markers);

                if (data.level_lines) {{
                    data.level_lines.forEach((line, idx) => {{
                        const levelSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: line.lineWidth || 1,
                            lineStyle: line.lineStyle || LightweightCharts.LineStyle.Dashed,
                            priceLineVisible: false, lastValueVisible: false,
                            crosshairMarkerVisible: false
                        }});
                        const lineData = [];
                        data.candles.forEach(c => {{
                            if (c.time >= line.start_time) {{
                                lineData.push({{ time: c.time, value: line.price }});
                            }}
                        }});
                        if (lineData.length > 0) levelSeries.setData(lineData);
                        registerSeries('level_' + idx, line.title, line.price, line.color, levelSeries, line.lineWidth || 1, true);
                    }});
                }}

                if (data.trade_lines) {{
                    data.trade_lines.forEach((line, idx) => {{
                        const tradeSeries = chart.addLineSeries({{
                            color: line.color, lineWidth: line.width || 2,
                            lineStyle: line.style === 2 ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                            priceLineVisible: false, lastValueVisible: false,
                            crosshairMarkerVisible: false
                        }});
                        const recentCandles = data.candles.slice(-100);
                        const lineData = recentCandles.map(c => ({{ time: c.time, value: line.price }}));
                        tradeSeries.setData(lineData);
                        registerSeries('trade_' + idx, line.title, line.price, line.color, tradeSeries, line.width || 2);
                    }});
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
