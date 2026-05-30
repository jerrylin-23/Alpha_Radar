// Typed client for the Flask backend.

export interface ScanResult {
  symbol: string;
  price: number;
  entry: number;
  dist: number;
  setup: string;
  rr_ratio?: number;
  valid?: boolean;
  near_entry?: boolean;
  timestamp?: string;
}

export interface ScanResponse {
  results: ScanResult[];
  total_scanned?: number;
  last_scan: string | null;
}

export interface ScanStatusResponse {
  last_scan: string | null;
  next_scan: string | null;
  is_scanning: boolean;
  scan_count: number;
  demo_mode: boolean;
}
export async function fetchScan(): Promise<ScanResponse> {
  const res = await fetch("/scan");
  if (!res.ok) throw new Error(`Scan failed (${res.status})`);
  return res.json();
}

export async function fetchScanAll(): Promise<ScanResponse> {
  const res = await fetch("/scan/all");
  if (!res.ok) throw new Error(`Scan all failed (${res.status})`);
  return res.json();
}

export async function fetchScanStatus(): Promise<ScanStatusResponse> {
  const res = await fetch("/scan/status");
  if (!res.ok) throw new Error(`Status failed (${res.status})`);
  return res.json();
}

/** Returns a full HTML document (the generated chart) as a string. */
export async function analyzeSymbol(symbol: string): Promise<string> {
  const res = await fetch("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  if (!res.ok) throw new Error(`Analysis failed (${res.status})`);
  return res.text();
}
