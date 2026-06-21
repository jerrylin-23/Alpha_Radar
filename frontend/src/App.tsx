import { useCallback, useEffect, useRef, useState } from "react";
import { analyzeSymbol, fetchScanAll, fetchScanStatus, type ScanResult, type ScanStatusResponse } from "./api";

type View = "chart" | "scanner";

/** Map setup type strings to badge style class + label */
function setupBadge(setup: string) {
  const lower = setup.toLowerCase();
  if (lower.includes("confluence"))
    return { cls: "badge badge-confluence", label: "Confluence" };
  if (lower.includes("fvg") || lower.includes("fair"))
    return { cls: "badge badge-fvg", label: "FVG" };
  if (lower.includes("eql") || lower.includes("equal"))
    return { cls: "badge badge-eql", label: "EQL" };
  return { cls: "badge badge-default", label: setup };
}

export default function App() {
  const [symbol, setSymbol] = useState("");
  const [view, setView] = useState<View>("chart");
  const [analyzing, setAnalyzing] = useState(false);
  const [chartHtml, setChartHtml] = useState<string | null>(null);

  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanResult[] | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<ScanStatusResponse | null>(null);
  const [filterNearEntry, setFilterNearEntry] = useState(true);

  const frameRef = useRef<HTMLIFrameElement>(null);

  // Write returned chart HTML into the iframe document.
  useEffect(() => {
    if (view === "chart" && chartHtml && frameRef.current) {
      const doc = frameRef.current.contentWindow?.document;
      if (doc) {
        doc.open();
        doc.write(chartHtml);
        doc.close();
      }
    }
  }, [chartHtml, view]);

  const analyze = useCallback(async (sym: string) => {
    const ticker = sym.trim().toUpperCase();
    if (!ticker) return;
    setSymbol(ticker);
    setView("chart");
    setAnalyzing(true);
    try {
      const html = await analyzeSymbol(ticker);
      setChartHtml(html);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const runScan = useCallback(async () => {
    setView("scanner");
    setScanning(true);
    setScanError(null);
    try {
      const [data, status] = await Promise.all([fetchScanAll(), fetchScanStatus()]);
      setResults(data.results);
      setScanStatus(status);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }, []);

  const totalScanned = scanStatus?.scan_count ?? 0;
  const lastScan = scanStatus?.last_scan
    ? new Date(scanStatus.last_scan).toLocaleTimeString()
    : "—";
  const isScanning = scanStatus?.is_scanning ?? false;

  return (
    <div className="app">
      <nav className="navbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><i /><i /><i /></div>
          <div>
            <h1>Alpha Radar</h1>
            <span className="brand-subtitle">Market structure intelligence</span>
          </div>
        </div>
        <div className="nav-links" aria-label="Primary navigation">
          <button className={view === "chart" ? "active" : ""} onClick={() => setView("chart")}>Terminal</button>
          <button className={view === "scanner" ? "active" : ""} onClick={runScan}>Scanner</button>
        </div>
        <div className="search">
          <label htmlFor="ticker-input">Symbol</label>
          <input
            id="ticker-input"
            type="text"
            placeholder="Enter ticker…"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && analyze(symbol)}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            id="analyze-btn"
            className="btn-primary"
            onClick={() => analyze(symbol)}
            disabled={analyzing}
          >
            {analyzing ? (
              <>
                Reading tape
                <span className="spinner sm" />
              </>
            ) : (
              <>Run analysis <span aria-hidden="true">↗</span></>
            )}
          </button>
        </div>
      </nav>

      <div className="toolbar">
        <span className="live-dot" />
        <span>US markets</span>
        <span className="toolbar-divider" />
        <span>ICT structure engine</span>
        <span className="toolbar-spacer" />
        <span className="toolbar-time">Realtime scanner</span>
      </div>

      <div className="content">
        {view === "chart" ? (
          chartHtml ? (
            <iframe ref={frameRef} className="chart-frame" title="chart" />
          ) : (
            <div className="placeholder">
              <section className="terminal-intro">
                <div className="intro-copy">
                  <span className="eyebrow">Alpha Radar / Terminal</span>
                  <h2>Less chart.<br /><em>More conviction.</em></h2>
                  <p>A decision brief that keeps the price action, levels, and trade thesis in one focused view.</p>
                  <div className="quick-symbols">
                    <span>Start with</span>
                    {["NVDA", "AAPL", "SPY"].map((ticker) => (
                      <button key={ticker} onClick={() => analyze(ticker)}>{ticker}</button>
                    ))}
                  </div>
                </div>
                <article className="research-brief" aria-label="Example NVDA research brief">
                  <header className="brief-topbar">
                    <div><span className="brief-kicker">Research brief</span><strong>NVDA</strong><span className="brief-company">NVIDIA Corp.</span></div>
                    <span className="demo-chip">Illustrative</span>
                  </header>
                  <div className="brief-price-row">
                    <div><span>Current price</span><strong>$181.64</strong><em>+1.84% today</em></div>
                    <div className="brief-score"><span>Setup quality</span><strong>74<span>/100</span></strong></div>
                  </div>
                  <div className="brief-chart">
                    <div className="brief-chart-header"><span>Market structure</span><span>4H</span></div>
                    <span className="brief-gridline grid-a" /><span className="brief-gridline grid-b" /><span className="brief-gridline grid-c" />
                    <span className="target-line target-one"><b>Target 1</b> $186.20</span>
                    <span className="entry-line"><b>Entry</b> $178.40</span>
                    <span className="stop-line"><b>Invalidation</b> $174.60</span>
                    <svg viewBox="0 0 620 190" preserveAspectRatio="none" aria-hidden="true"><path className="brief-area" d="M0 158 C25 149 38 165 61 144 S95 125 120 135 S152 152 176 129 S213 124 237 98 S279 95 302 112 S332 130 355 83 S390 90 414 64 S452 102 478 70 S515 57 542 38 S584 45 620 17 L620 190 L0 190 Z" /><path className="brief-line" d="M0 158 C25 149 38 165 61 144 S95 125 120 135 S152 152 176 129 S213 124 237 98 S279 95 302 112 S332 130 355 83 S390 90 414 64 S452 102 478 70 S515 57 542 38 S584 45 620 17" /></svg>
                    <span className="brief-now">NOW $181.64</span>
                  </div>
                  <div className="brief-plan">
                    <div><span>Bias</span><strong className="positive">Long</strong></div>
                    <div><span>Entry zone</span><strong>$178.40</strong></div>
                    <div><span>Risk / reward</span><strong className="positive">2.8R</strong></div>
                  </div>
                  <footer className="brief-thesis"><span className="thesis-dot" />Liquidity swept below the prior low. Price is reclaiming the 4H order block.</footer>
                </article>
              </section>
              <div className="placeholder-footnote"><span>01</span> Research brief demo · Select a symbol to open its full market structure report</div>
            </div>
          )
        ) : (
          <div className="scanner">
            <div className="scanner-header">
              <span className="eyebrow">Market scanner</span>
              <h2>Setups approaching<br /><em>the buy zone.</em></h2>
              <p className="sub">
                Tickers approaching entry within ~1.5% of calculated setup
                price
              </p>
            </div>

            {/* Status bar */}
            {!scanning && (
              <div className="status-bar">
                <span
                  className={`status-dot${isScanning ? " scanning" : ""}`}
                />
                <span>
                  {isScanning ? "Scanning markets" : "Scanner ready"}
                </span>
                <span>Last scan: {lastScan}</span>
                <span className="status-count">
                  {results?.filter(r => r.near_entry).length ?? 0} near zone / {results?.length ?? 0} active setups
                </span>
              </div>
            )}

            {/* Loading */}
            {scanning && (
              <div className="center">
                <span className="spinner" />
                <p>Fetching scan results…</p>
              </div>
            )}

            {/* Error */}
            {!scanning && scanError && (
              <div className="empty">
                <div className="empty-icon">⚠️</div>
                {scanError}
              </div>
            )}

            {/* Results table */}
            {!scanning && !scanError && results && results.length > 0 && (() => {
              const displayedResults = filterNearEntry ? results.filter(r => r.near_entry) : results;
              return (
                <>
                  <div className="scan-filters">
                    <button
                      className={`tab-btn ${filterNearEntry ? "active" : ""}`}
                      onClick={() => setFilterNearEntry(true)}
                    >
                      Near entry <span>{results.filter(r => r.near_entry).length}</span>
                    </button>
                    <button
                      className={`tab-btn ${!filterNearEntry ? "active" : ""}`}
                      onClick={() => setFilterNearEntry(false)}
                    >
                      All setups <span>{results.length}</span>
                    </button>
                  </div>

                  {displayedResults.length > 0 ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Price</th>
                          <th>Entry</th>
                          <th>Distance</th>
                          <th>Setup</th>
                          <th>R:R</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayedResults.map((r) => {
                          const badge = setupBadge(r.setup);
                          const distNear = Math.abs(r.dist) <= 1.0;
                          const rrGood =
                            r.rr_ratio != null && r.rr_ratio >= 2;
                          return (
                            <tr key={r.symbol}>
                              <td className="sym">{r.symbol}</td>
                              <td className="price">${r.price.toFixed(2)}</td>
                              <td className="entry">${r.entry.toFixed(2)}</td>
                              <td
                                className={`dist ${distNear ? "near" : "far"}`}
                              >
                                {r.dist.toFixed(2)}%
                              </td>
                              <td>
                                <span className={badge.cls}>{badge.label}</span>
                              </td>
                              <td
                                className={`rr ${rrGood ? "good" : ""}`}
                              >
                                {r.rr_ratio != null
                                  ? `${r.rr_ratio.toFixed(1)}:1`
                                  : "—"}
                              </td>
                              <td>
                                <button
                                  className="btn-view"
                                  onClick={() => analyze(r.symbol)}
                                >
                                  View →
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty">
                      <div className="empty-icon">🔭</div>
                      No setups are currently in the buy-the-dip zone. Select "All Setups" to view pending structures.
                    </div>
                  )}

                  <div className="scan-meta">
                    <span>
                      Scans completed: {totalScanned}
                    </span>
                    <span>{displayedResults.length} setups displayed</span>
                  </div>
                </>
              );
            })()}

            {/* Empty */}
            {!scanning && !scanError && (!results || results.length === 0) && (
              <div className="empty">
                <div className="empty-icon">🔭</div>
                No tickers within range right now. The scanner refreshes every
                few minutes.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
