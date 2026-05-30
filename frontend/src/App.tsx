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
      {/* ===== Navbar ===== */}
      <nav className="navbar">
        <div className="brand">
          <div className="brand-icon">📡</div>
          <h1>Alpha Radar</h1>
          <span className="tag">Live</span>
        </div>
        <div className="search">
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
                Analyzing
                <span className="spinner sm" />
              </>
            ) : (
              <>Analyze</>
            )}
          </button>
        </div>
      </nav>

      {/* ===== Toolbar ===== */}
      <div className="toolbar">
        <button
          id="tab-chart"
          className={view === "chart" ? "active" : ""}
          onClick={() => setView("chart")}
        >
          Chart
        </button>
        <button
          id="tab-scanner"
          className={view === "scanner" ? "active" : ""}
          onClick={runScan}
        >
          Market Scanner
        </button>
      </div>

      {/* ===== Content ===== */}
      <div className="content">
        {view === "chart" ? (
          chartHtml ? (
            <iframe ref={frameRef} className="chart-frame" title="chart" />
          ) : (
            <div className="placeholder">
              <span className="icon">📡</span>
              <p>Enter a ticker symbol to generate an automated ICT trade plan</p>
              <span className="hint">
                Try <kbd>NVDA</kbd> <kbd>AAPL</kbd> <kbd>SPY</kbd>
              </span>
            </div>
          )
        ) : (
          <div className="scanner">
            <div className="scanner-header">
              <h2>Market Scanner</h2>
              <p className="sub">
                Tickers approaching entry — within ~1.5% of calculated setup
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
                  {isScanning ? "Scanning markets…" : "Scanner idle"}
                </span>
                <span>Last scan: {lastScan}</span>
                <span className="status-count">
                  {results?.filter(r => r.near_entry).length ?? 0} near buy zone | {results?.length ?? 0} active setups
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
                  <div style={{ display: "flex", gap: "6px", marginBottom: "1.25rem", background: "rgba(30, 41, 59, 0.4)", padding: "4px", borderRadius: "8px", width: "fit-content", border: "1px solid var(--border)" }}>
                    <button
                      className={`tab-btn ${filterNearEntry ? "active" : ""}`}
                      style={{
                        background: filterNearEntry ? "var(--accent)" : "transparent",
                        border: "none",
                        color: filterNearEntry ? "#fff" : "var(--text-secondary)",
                        padding: "6px 16px",
                        borderRadius: "6px",
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        cursor: "pointer",
                        transition: "all 0.2s"
                      }}
                      onClick={() => setFilterNearEntry(true)}
                    >
                      🎯 Near Entry ({results.filter(r => r.near_entry).length})
                    </button>
                    <button
                      className={`tab-btn ${!filterNearEntry ? "active" : ""}`}
                      style={{
                        background: !filterNearEntry ? "var(--accent)" : "transparent",
                        border: "none",
                        color: !filterNearEntry ? "#fff" : "var(--text-secondary)",
                        padding: "6px 16px",
                        borderRadius: "6px",
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        cursor: "pointer",
                        transition: "all 0.2s"
                      }}
                      onClick={() => setFilterNearEntry(false)}
                    >
                      🌐 All Setups ({results.length})
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
