"""
ICT Buy-the-Dip Analyzer — Optimized
Vectorized detection of order blocks, fair value gaps, and key levels.
Timeframes: 4H and Daily
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import argparse
import logging
from datetime import datetime, timedelta

import cache
from chart import generate_chart_html

logger = logging.getLogger(__name__)


class ICTAnalyzer:
    """Implements ICT concepts for buy-the-dip detection with vectorized ops."""

    def __init__(self, symbol: str, timeframe: str = "4h"):
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self.df = None
        self.order_blocks = []
        self.fvgs = []
        self.eq_levels = {'highs': [], 'lows': []}
        self.earnings_vwap = None
        self.earnings_vwap_date = None
        self.earnings_vwap_current = None
        self._atr = None

    def fetch_data(self, period: str = "2y", use_cache: bool = True) -> pd.DataFrame:
        """Fetch OHLCV data from yfinance with optional disk cache."""
        interval = "1h" if self.timeframe == "4h" else "1d"
        cache_key = f"{self.symbol}_{interval}_{period}"

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                self.df = cached
                logger.info(f"Cache hit for {self.symbol} ({len(self.df)} candles)")
                return self.df

        self.df = yf.download(
            self.symbol, period=period, interval=interval,
            progress=False, threads=False
        )

        if isinstance(self.df.columns, pd.MultiIndex):
            self.df.columns = self.df.columns.get_level_values(0)

        if self.timeframe == "4h" and interval == "1h":
            resampler = self.df.resample('4h')
            self.df = pd.DataFrame({
                'Open': resampler['Open'].first(),
                'High': resampler['High'].max(),
                'Low': resampler['Low'].min(),
                'Close': resampler['Close'].last(),
                'Volume': resampler['Volume'].sum()
            }).dropna()

        if use_cache and self.df is not None and not self.df.empty:
            cache.put(cache_key, self.df)

        logger.info(f"Fetched {len(self.df)} candles for {self.symbol} ({self.timeframe})")
        return self.df

    def set_data(self, df: pd.DataFrame):
        """Inject pre-fetched data (for batch scanner)."""
        self.df = df.copy()
        if isinstance(self.df.columns, pd.MultiIndex):
            self.df.columns = self.df.columns.get_level_values(0)

    # ------------------------------------------------------------------ #
    #  ATR
    # ------------------------------------------------------------------ #
    def compute_atr(self, period: int = 20) -> pd.Series:
        """Average True Range for dynamic thresholds."""
        if self._atr is not None:
            return self._atr
        df = self.df
        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift(1)).abs(),
            (df['Low'] - df['Close'].shift(1)).abs(),
        ], axis=1).max(axis=1)
        self._atr = tr.rolling(period).mean()
        return self._atr

    # ------------------------------------------------------------------ #
    #  Swing Points — O(N) rolling window
    # ------------------------------------------------------------------ #
    def detect_swing_points(self, lookback: int = 3) -> pd.DataFrame:
        df = self.df
        window = 2 * lookback + 1
        rolling_high = df['High'].rolling(window, center=True).max()
        rolling_low = df['Low'].rolling(window, center=True).min()
        df['swing_high'] = (df['High'] == rolling_high).fillna(False)
        df['swing_low'] = (df['Low'] == rolling_low).fillna(False)
        self.df = df
        sh = df['swing_high'].sum()
        sl = df['swing_low'].sum()
        logger.info(f"Swing points: {sh} highs, {sl} lows")
        return df

    # ------------------------------------------------------------------ #
    #  Order Blocks — vectorized + displacement validation
    # ------------------------------------------------------------------ #
    def detect_order_blocks(self, min_move_pct: float = 1.0) -> list:
        df = self.df
        atr = self.compute_atr(20)

        # For each candle k (potential OB):
        #   k is the OB candle
        #   k+1 is the displacement candle
        #   k+2 is the confirmation candle
        is_bearish = df['Close'] < df['Open']
        is_bullish = df['Close'] > df['Open']

        next_high = df['High'].shift(-1)
        next_low = df['Low'].shift(-1)
        confirm_close = df['Close'].shift(-2)
        confirm_base = df['Close'].shift(-1)
        move_pct = (confirm_close - confirm_base).abs() / confirm_base * 100

        # Displacement validation: displacement candle body >= 70% of range
        disp_body = (df['Close'].shift(-1) - df['Open'].shift(-1)).abs()
        disp_range = (df['High'].shift(-1) - df['Low'].shift(-1)).replace(0, np.nan)
        disp_ratio = disp_body / disp_range
        disp_strong = (disp_ratio >= 0.65) & (disp_body >= 1.2 * atr)

        # Bullish OB: OB candle is bearish, confirmation closes above displacement high
        bull_mask = is_bearish & (confirm_close > next_high) & (move_pct >= min_move_pct) & disp_strong
        # Bearish OB: OB candle is bullish, confirmation closes below displacement low
        bear_mask = is_bullish & (confirm_close < next_low) & (move_pct >= min_move_pct) & disp_strong

        order_blocks = []
        for idx in df.index[bull_mask.fillna(False)]:
            row = df.loc[idx]
            i = df.index.get_loc(idx)
            if i + 2 < len(df):
                order_blocks.append({
                    'type': 'bullish', 'date': idx,
                    'high': float(row['High']), 'low': float(row['Low']),
                    'strength': float(move_pct.iloc[i]),
                })

        for idx in df.index[bear_mask.fillna(False)]:
            row = df.loc[idx]
            i = df.index.get_loc(idx)
            if i + 2 < len(df):
                order_blocks.append({
                    'type': 'bearish', 'date': idx,
                    'high': float(row['High']), 'low': float(row['Low']),
                    'strength': float(move_pct.iloc[i]),
                })

        self.order_blocks = order_blocks
        bull_count = sum(1 for ob in order_blocks if ob['type'] == 'bullish')
        bear_count = len(order_blocks) - bull_count
        logger.info(f"Order blocks: {bull_count} bullish, {bear_count} bearish")
        return order_blocks

    # ------------------------------------------------------------------ #
    #  Fair Value Gaps — vectorized with cummin/cummax fill check
    # ------------------------------------------------------------------ #
    def detect_fair_value_gaps(self, min_gap_pct: float = 0.5) -> list:
        df = self.df

        c1_high = df['High'].shift(2)
        c1_low = df['Low'].shift(2)
        c3_low = df['Low']
        c3_high = df['High']

        # Bullish FVG: gap up (c1_high < c3_low)
        bull_gap = c3_low - c1_high
        bull_gap_pct = bull_gap / c1_high * 100
        bull_mask = (c1_high < c3_low) & (bull_gap_pct >= min_gap_pct)

        # Bearish FVG: gap down (c1_low > c3_high)
        bear_gap = c1_low - c3_high
        bear_gap_pct = bear_gap / c1_low * 100
        bear_mask = (c1_low > c3_high) & (bear_gap_pct >= min_gap_pct)

        # Precompute forward cummin/cummax for O(1) fill checks
        future_low_min = df['Low'].iloc[::-1].cummin().iloc[::-1].shift(-1)
        future_high_max = df['High'].iloc[::-1].cummax().iloc[::-1].shift(-1)

        fvgs = []
        mid_date = df.index  # FVG date = middle candle (shift by -1 from current)

        for i in df.index[bull_mask.fillna(False)]:
            pos = df.index.get_loc(i)
            if pos < 2:
                continue
            bottom = float(c1_high.loc[i])
            top = float(c3_low.loc[i])
            filled = bool(future_low_min.loc[i] <= bottom) if pd.notna(future_low_min.loc[i]) else False
            mitigated = (not filled) and bool(future_low_min.loc[i] <= top) if pd.notna(future_low_min.loc[i]) else False
            fvgs.append({
                'type': 'bullish', 'date': df.index[pos - 1],
                'top': top, 'bottom': bottom,
                'gap_pct': float(bull_gap_pct.loc[i]),
                'filled': filled, 'mitigated': mitigated,
            })

        for i in df.index[bear_mask.fillna(False)]:
            pos = df.index.get_loc(i)
            if pos < 2:
                continue
            top = float(c1_low.loc[i])
            bottom = float(c3_high.loc[i])
            filled = bool(future_high_max.loc[i] >= top) if pd.notna(future_high_max.loc[i]) else False
            mitigated = (not filled) and bool(future_high_max.loc[i] >= bottom) if pd.notna(future_high_max.loc[i]) else False
            fvgs.append({
                'type': 'bearish', 'date': df.index[pos - 1],
                'top': top, 'bottom': bottom,
                'gap_pct': float(bear_gap_pct.loc[i]),
                'filled': filled, 'mitigated': mitigated,
            })

        self.fvgs = fvgs
        bull_count = sum(1 for f in fvgs if f['type'] == 'bullish')
        bear_count = len(fvgs) - bull_count
        unfilled = sum(1 for f in fvgs if not f['filled'])
        logger.info(f"FVGs: {bull_count} bullish, {bear_count} bearish ({unfilled} unfilled)")
        return fvgs

    # ------------------------------------------------------------------ #
    #  Equal Highs / Lows — sorted-pass clustering O(K log K)
    # ------------------------------------------------------------------ #
    def detect_equal_highs_lows(self, threshold_pct: float = 1.0) -> dict:
        df = self.df
        swing_highs = df[df['swing_high']]
        swing_lows = df[df['swing_low']]

        eqh = self._cluster_levels(
            swing_highs['High'].values, swing_highs.index.tolist(), threshold_pct
        )
        eql = self._cluster_levels(
            swing_lows['Low'].values, swing_lows.index.tolist(), threshold_pct
        )

        self.eq_levels = {'highs': eqh, 'lows': eql}
        logger.info(f"Equal levels: {len(eqh)} EQH, {len(eql)} EQL")
        return self.eq_levels

    @staticmethod
    def _cluster_levels(prices: np.ndarray, indices: list, threshold_pct: float) -> list:
        """Sorted-pass clustering of price levels within threshold."""
        if len(prices) == 0:
            return []
        order = np.argsort(prices)
        sorted_p = prices[order]
        sorted_idx = [indices[o] for o in order]

        groups = []
        i = 0
        while i < len(sorted_p):
            group_p = [sorted_p[i]]
            group_idx = [sorted_idx[i]]
            j = i + 1
            while j < len(sorted_p) and sorted_p[j] <= group_p[0] * (1 + threshold_pct / 100):
                group_p.append(sorted_p[j])
                group_idx.append(sorted_idx[j])
                j += 1
            if len(group_p) > 1:
                groups.append({
                    'price': float(np.mean(group_p)),
                    'count': len(group_p),
                    'indices': group_idx,
                })
            i = j
        return groups

    # ------------------------------------------------------------------ #
    #  Earnings date + VWAP (unchanged logic)
    # ------------------------------------------------------------------ #
    def get_last_earnings_date(self):
        """Get the most recent past earnings ANNOUNCEMENT date for a stock."""
        try:
            ticker = yf.Ticker(self.symbol)
            today = pd.Timestamp.now(tz='America/New_York').normalize()

            try:
                ed = ticker.earnings_dates
                if ed is not None and hasattr(ed, 'index') and len(ed.index) > 0:
                    announcement_dates = pd.to_datetime(ed.index)
                    past_dates = []
                    for d in announcement_dates:
                        dc = d.tz_convert('America/New_York') if d.tzinfo else d.tz_localize('America/New_York')
                        if dc < today:
                            past_dates.append(d)
                    if past_dates:
                        last_earnings = max(past_dates)
                        logger.info(f"Last earnings: {last_earnings.strftime('%Y-%m-%d')}")
                        return last_earnings
            except Exception:
                pass

            try:
                eh = ticker.earnings_history
                if eh is not None and hasattr(eh, 'index') and len(eh.index) > 0:
                    quarter_dates = pd.to_datetime(eh.index)
                    today_naive = pd.Timestamp.now().normalize()
                    past_quarters = [d for d in quarter_dates if d < today_naive]
                    if past_quarters:
                        return max(past_quarters)
            except Exception:
                pass

            try:
                calendar = ticker.calendar
                if isinstance(calendar, dict) and 'Earnings Date' in calendar:
                    ed_val = calendar['Earnings Date']
                    next_date = pd.to_datetime(ed_val[0] if isinstance(ed_val, (list, tuple)) else ed_val)
                    return next_date - pd.Timedelta(days=90)
            except Exception:
                pass

            return None
        except Exception:
            return None

    def calculate_earnings_vwap(self):
        """Calculate VWAP anchored from most recent earnings date."""
        earnings_date = self.get_last_earnings_date()
        if earnings_date is None:
            self.earnings_vwap = None
            self.earnings_vwap_date = None
            return None

        df = self.df.copy()
        if df.index.tz is not None:
            if earnings_date.tzinfo is None:
                earnings_date = earnings_date.tz_localize(df.index.tz)
            else:
                earnings_date = earnings_date.tz_convert(df.index.tz)

        df_since = df[df.index >= earnings_date]
        if len(df_since) < 2:
            self.earnings_vwap = None
            self.earnings_vwap_date = None
            return None

        tp = (df_since['High'] + df_since['Low'] + df_since['Close']) / 3
        cum_tp_vol = (tp * df_since['Volume']).cumsum()
        cum_vol = df_since['Volume'].cumsum()
        vwap = cum_tp_vol / cum_vol

        vwap_data = [{'time': int(idx.timestamp()), 'value': round(float(val), 2)}
                     for idx, val in vwap.items() if pd.notna(val)]

        self.earnings_vwap = vwap_data
        self.earnings_vwap_date = earnings_date
        self.earnings_vwap_current = float(vwap.iloc[-1]) if len(vwap) > 0 else None
        return vwap_data

    # ------------------------------------------------------------------ #
    #  Analysis summary
    # ------------------------------------------------------------------ #
    def generate_analysis_summary(self) -> str:
        current_price = float(self.df['Close'].iloc[-1])
        summary = []

        def add_level(label: str, price: float, detail: str, tone: str) -> None:
            summary.append(
                f'<div class="market-level {tone}">'
                f'<span class="market-level-label">{label}</span>'
                f'<span class="market-level-value">${price:.2f}'
                f'<small>{detail}</small></span>'
                f'</div>'
            )

        # Resistance
        resistances = [l for l in self.eq_levels.get('highs', []) if l['price'] > current_price]
        if resistances:
            closest_r = min(resistances, key=lambda x: x['price'])
            add_level('Resistance', closest_r['price'], 'Equal high', 'resistance')
        else:
            recent_highs = self.df[self.df.get('swing_high', False) == True].tail(5)
            highs_above = recent_highs[recent_highs['High'] > current_price]
            if not highs_above.empty:
                add_level('Resistance', highs_above.iloc[-1]['High'], 'Swing high', 'resistance')

        # Bear gaps above
        bear_fvgs = [f for f in self.fvgs if f['type'] == 'bearish' and not f['filled'] and f['bottom'] > current_price]
        if bear_fvgs:
            closest = min(bear_fvgs, key=lambda x: x['bottom'])
            add_level('Overhead gap', (closest['top'] + closest['bottom']) / 2, 'Unfilled bearish FVG', 'warning')

        # Bull gaps below
        bull_fvgs = [f for f in self.fvgs if f['type'] == 'bullish' and not f['filled'] and f['top'] < current_price]
        if bull_fvgs:
            closest = max(bull_fvgs, key=lambda x: x['top'])
            add_level('Demand gap', (closest['top'] + closest['bottom']) / 2, 'Unfilled bullish FVG', 'support')

        # Support
        supports = [l for l in self.eq_levels.get('lows', []) if l['price'] < current_price]
        if supports:
            closest_s = max(supports, key=lambda x: x['price'])
            add_level('Support', closest_s['price'], 'Equal low', 'support')
        else:
            recent_lows = self.df[self.df.get('swing_low', False) == True].tail(5)
            lows_below = recent_lows[recent_lows['Low'] < current_price]
            if not lows_below.empty:
                add_level('Support', lows_below.iloc[-1]['Low'], 'Swing low', 'support')

        # Earnings VWAP
        if self.earnings_vwap_current is not None:
            er_date = self.earnings_vwap_date.strftime('%m/%d') if self.earnings_vwap_date else ''
            add_level('Earnings VWAP', self.earnings_vwap_current, er_date, 'reference')

        if not summary:
            return '<p class="market-level-empty">No nearby structure levels found.</p>'
        return ''.join(summary)

    # ------------------------------------------------------------------ #
    #  Trade Plan — with recency, ATR-based SL, R:R gating
    # ------------------------------------------------------------------ #
    def calculate_trade_plan(self) -> dict:
        current_price = float(self.df['Close'].iloc[-1])
        atr = self.compute_atr(20)
        atr_val = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else current_price * 0.02
        num_candles = len(self.df)

        entry_candidates = []

        # Bullish FVGs
        for f in getattr(self, 'fvgs', []):
            if f['type'] == 'bullish' and not f['filled'] and f['top'] < current_price:
                date_idx = self.df.index.get_indexer([f['date']], method='nearest')[0]
                age = num_candles - date_idx
                recency = max(0.3, 1.0 - age / 120)
                entry_candidates.append({
                    'price': f['top'], 'type': 'FVG',
                    'bottom': f['bottom'], 'recency': recency,
                    'mitigated': f.get('mitigated', False),
                })

        # Bullish OBs
        for ob in getattr(self, 'order_blocks', []):
            if ob['type'] == 'bullish' and ob['high'] < current_price:
                date_idx = self.df.index.get_indexer([ob['date']], method='nearest')[0]
                age = num_candles - date_idx
                recency = max(0.3, 1.0 - age / 120)
                entry_candidates.append({
                    'price': ob['high'], 'type': 'OB',
                    'bottom': ob['low'], 'recency': recency,
                })

        # EQLs
        for l in self.eq_levels.get('lows', []):
            if l['price'] < current_price:
                entry_candidates.append({
                    'price': l['price'], 'type': 'EQL',
                    'bottom': l['price'], 'recency': 1.0,
                })

        # Sort by recency-weighted distance (prefer recent & close to price)
        entry_candidates.sort(key=lambda x: -(x['price'] * x['recency']))

        entry_price = current_price
        setup_type = "Aggressive (Market)"
        entry_obj = None

        if entry_candidates:
            entry_obj = entry_candidates[0]
            entry_price = entry_obj['price']
            label = entry_obj['type']
            if entry_obj.get('mitigated'):
                label += " mitigated"
            setup_type = f"Limit Buy ({label})"

        # Stop Loss — ATR-based buffer
        if entry_obj:
            sl_price = entry_obj['bottom'] - 0.5 * atr_val
        else:
            sl_price = entry_price - 1.5 * atr_val

        # Minimum risk floor
        if (entry_price - sl_price) / entry_price < 0.005:
            sl_price = entry_price - atr_val

        risk = entry_price - sl_price

        # Take profits should be actual destinations, not the first price line
        # above entry.  A nearby EQH can be useful context, but a target that is
        # only a few cents away is not a trade a person could realistically plan
        # around after spread, slippage, and normal 4H noise.
        #
        # Require the first objective to offer at least 1.5R *and* roughly one
        # ATR of room.  Prefer liquidity pools (EQH) and then swing highs that
        # clear that distance; use an ATR/R ladder only when no such structure
        # exists.  This keeps the targets tied to price action without letting a
        # trivial nearby level collapse the trade plan.
        min_tp1_distance = max(risk * 1.5, atr_val)
        min_target_spacing = max(risk, atr_val * 0.75)

        eqh_prices = [l['price'] for l in self.eq_levels.get('highs', [])]
        swing_high_prices = self.df.loc[
            self.df.get('swing_high', False) == True, 'High'
        ].tolist()
        liquidity_targets = sorted({
            float(price) for price in eqh_prices + swing_high_prices
            if price >= entry_price + min_tp1_distance
        })

        tp1 = liquidity_targets[0] if liquidity_targets else entry_price + min_tp1_distance
        later_targets = [
            price for price in liquidity_targets
            if price >= tp1 + min_target_spacing
        ]
        tp2 = (
            later_targets[0]
            if later_targets
            else max(entry_price + risk * 2.5, tp1 + min_target_spacing)
        )
        final_targets = [
            price for price in later_targets
            if price >= tp2 + min_target_spacing
        ]
        tp3 = (
            final_targets[0]
            if final_targets
            else max(entry_price + risk * 3.5, tp2 + min_target_spacing)
        )

        # R:R ratio
        rr_ratio = (tp1 - entry_price) / risk if risk > 0 else 0
        valid = rr_ratio >= 1.2  # Relaxed from 1.5 to avoid filtering too aggressively

        return {
            'type': setup_type,
            'entry': entry_price,
            'sl': sl_price,
            'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'rr_ratio': round(rr_ratio, 2),
            'valid': valid,
        }

    # ------------------------------------------------------------------ #
    #  Chart HTML (delegates to chart.py)
    # ------------------------------------------------------------------ #
    def generate_chart_html(self, show_fvgs=True, max_fvgs=1, max_levels=2) -> str:
        plan = self.calculate_trade_plan()
        summary = self.generate_analysis_summary()
        return generate_chart_html(
            df=self.df, symbol=self.symbol,
            fvgs=self.fvgs, eq_levels=self.eq_levels,
            trade_plan=plan, analysis_summary=summary,
            earnings_vwap=getattr(self, 'earnings_vwap', None),
            show_fvgs=show_fvgs, max_fvgs=max_fvgs, max_levels=max_levels,
        )


# ===================================================================== #
#  Public entry point
# ===================================================================== #

def analyze_stock(symbol: str, timeframe: str = "4h", end_date: str = None,
                  plan_only: bool = False, use_cache: bool = True):
    """
    Main entry point for analysis.

    Args:
        symbol: Ticker symbol.
        timeframe: "4h" or "1d".
        end_date: Optional cutoff for backtesting.
        plan_only: If True, skip chart HTML generation.
        use_cache: Whether to use disk cache for OHLCV data.

    Returns:
        ICTAnalyzer instance with all detections run.
    """
    logger.info(f"ANALYZING {symbol} ({timeframe})...")

    analyzer = ICTAnalyzer(symbol, timeframe)
    analyzer.fetch_data(use_cache=use_cache)

    if analyzer.df is None or analyzer.df.empty:
        logger.warning(f"No data for {symbol}")
        return None

    # Backtesting: slice data if end_date provided
    if end_date:
        try:
            cutoff = pd.Timestamp(end_date) + pd.Timedelta(days=1)
            if analyzer.df.index.tz is not None and cutoff.tz is None:
                cutoff = cutoff.tz_localize(analyzer.df.index.tz)
            analyzer.df = analyzer.df[analyzer.df.index < cutoff]
            if analyzer.df.empty:
                logger.warning(f"No data for {symbol} before {end_date}")
                return None
        except Exception as e:
            logger.warning(f"Error slicing data: {e}")

    analyzer.detect_swing_points()
    analyzer.detect_order_blocks()
    analyzer.detect_equal_highs_lows()
    analyzer.detect_fair_value_gaps()
    analyzer.calculate_earnings_vwap()

    has_structure = (analyzer.fvgs or
                     analyzer.eq_levels['highs'] or
                     analyzer.eq_levels['lows'] or
                     analyzer.order_blocks)

    if has_structure:
        plan = analyzer.calculate_trade_plan()
        logger.info(f"Trade plan: {plan['type']} | Entry=${plan['entry']:.2f} "
                     f"SL=${plan['sl']:.2f} TP1=${plan['tp1']:.2f} R:R=1:{plan['rr_ratio']}")
    else:
        logger.warning(f"No sufficient structure for {symbol}")

    return analyzer


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser(description="ICT Buy the Dip Analyzer")
    parser.add_argument("--date", type=str, help="Backtest date (YYYY-MM-DD)", default=None)
    parser.add_argument("--symbol", type=str, help="Specific symbol", default=None)
    args = parser.parse_args()

    symbol = args.symbol if args.symbol else "NVDA"
    symbols = [symbol] if args.symbol else ["AAPL", "NVDA", "SPY"]

    for s in symbols:
        analyzer = analyze_stock(s, timeframe="4h", end_date=args.date)
        if analyzer and not analyzer.df.empty:
            html_content = analyzer.generate_chart_html()
            import os
            date_str = args.date if args.date else "latest"
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f"{s}_{date_str}_ict_analysis.html")
            with open(filepath, "w") as f:
                f.write(html_content)
            print(f"📊 Chart saved to {filepath}")
