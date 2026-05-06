import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const formatBytes = (value) => {
  if (!value && value !== 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(2)} ${units[idx]}`;
};

const formatTime = (value) => (value ? value.toLocaleTimeString() : "Not yet");

export default function App() {
  const [status, setStatus] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [search, setSearch] = useState("");
  const [verifyReport, setVerifyReport] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const apiOnline = useMemo(() => !!status, [status]);
  const masterRunning = status?.master?.running ?? false;
  const nodeCount = status?.nodes?.length ?? 0;
  const nodesRunning = status?.nodes?.filter((node) => node.running).length ?? 0;
  const serviceTotal = 1 + nodeCount;
  const availability = status
    ? Math.round(((masterRunning ? 1 : 0) + nodesRunning) / serviceTotal * 100)
    : 0;
  const masterLabel = status ? (masterRunning ? "Running" : "Stopped") : "Unknown";
  const nodesLabel = status ? `${nodesRunning}/${nodeCount}` : "-";

  const storageTotalBytes = analysis
    ? analysis.node1.size_bytes + analysis.node2.size_bytes
    : 0;

  const replication =
    analysis && analysis.unique_chunks
      ? (analysis.total_chunks / analysis.unique_chunks).toFixed(2)
      : "-";

  const fileEntries = useMemo(() => {
    if (analysis?.files?.length) {
      return analysis.files.map((entry) => ({
        name: entry.name,
        chunks: entry.chunks
      }));
    }
    return files.map((name) => ({ name, chunks: null }));
  }, [analysis, files]);

  const filteredFiles = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return fileEntries;
    return fileEntries.filter((entry) =>
      entry.name.toLowerCase().includes(term)
    );
  }, [fileEntries, search]);

  const node1Share = analysis && storageTotalBytes
    ? Math.round((analysis.node1.size_bytes / storageTotalBytes) * 100)
    : 0;
  const node2Share = analysis && storageTotalBytes
    ? Math.round((analysis.node2.size_bytes / storageTotalBytes) * 100)
    : 0;

  const notify = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const fetchJson = async (path, options) => {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const msg = detail.detail || response.statusText;
      throw new Error(msg);
    }
    return response.json();
  };

  const loadStatus = async () => {
    const data = await fetchJson("/api/status");
    setStatus(data);
  };

  const loadFiles = async () => {
    const data = await fetchJson("/api/files");
    setFiles(data.files || []);
  };

  const loadAnalysis = async () => {
    const data = await fetchJson("/api/analysis");
    setAnalysis(data);
  };

  const refreshAll = async () => {
    try {
      setBusy(true);
      await Promise.all([loadStatus(), loadFiles(), loadAnalysis()]);
      setLastUpdated(new Date());
    } catch (err) {
      notify("error", err.message || "API not reachable");
      setStatus(null);
    } finally {
      setBusy(false);
    }
  };

  const startSystem = async () => {
    try {
      setBusy(true);
      await fetchJson("/api/start", { method: "POST" });
      notify("success", "System start requested");
      await refreshAll();
    } catch (err) {
      notify("error", err.message);
    } finally {
      setBusy(false);
    }
  };

  const stopSystem = async () => {
    try {
      setBusy(true);
      await fetchJson("/api/stop", { method: "POST" });
      notify("success", "System stop requested");
      await refreshAll();
    } catch (err) {
      notify("error", err.message);
    } finally {
      setBusy(false);
    }
  };

  const uploadFile = async () => {
    if (!selectedFile) {
      notify("error", "Select a file to upload");
      return;
    }

    try {
      setBusy(true);
      const form = new FormData();
      form.append("file", selectedFile);
      const result = await fetchJson("/api/upload", {
        method: "POST",
        body: form
      });
      notify("success", `Uploaded ${result.filename}`);
      setSelectedFile(null);
      await refreshAll();
    } catch (err) {
      notify("error", err.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadFile = async (filename) => {
    try {
      setBusy(true);
      const response = await fetch(
        `${API_BASE}/api/download/${encodeURIComponent(filename)}`
      );
      if (!response.ok) {
        throw new Error("Download failed");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      notify("success", `Downloaded ${filename}`);
    } catch (err) {
      notify("error", err.message);
    } finally {
      setBusy(false);
    }
  };

  const runVerify = async () => {
    try {
      setBusy(true);
      const result = await fetchJson("/api/verify");
      setVerifyReport(result);
      notify("success", "Integrity check complete");
    } catch (err) {
      notify("error", err.message || "Integrity check failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">MD</div>
          <div>
            <p className="brand-title">Mini Dropbox</p>
            <p className="brand-sub">Cloud workspace</p>
          </div>
        </div>

        <div className="sidebar-status">
          <span className={`status-dot ${apiOnline ? "ok" : "warn"}`} />
          <div>
            <p className="label">API status</p>
            <p className="value">{apiOnline ? "Online" : "Offline"}</p>
            <p className="muted">{API_BASE}</p>
          </div>
        </div>

        <nav className="nav">
          <p className="nav-label">Console</p>
          <button className="nav-item active" type="button">
            Dashboard
          </button>
          <button className="nav-item" type="button">
            Files
          </button>
          <button className="nav-item" type="button">
            Health
          </button>
          <button className="nav-item" type="button">
            Analytics
          </button>
        </nav>

        <div className="sidebar-card">
          <p className="label">Cluster health</p>
          <p className="value">
            {status ? `${availability}% availability` : "Unknown"}
          </p>
          <div className="progress">
            <span style={{ width: `${availability}%` }} />
          </div>
          <p className="muted">Master: {masterLabel}</p>
          <p className="muted">Nodes: {nodesLabel} online</p>
          <p className="muted">Last refresh: {formatTime(lastUpdated)}</p>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-title">
            <p className="eyebrow">Local cloud workspace</p>
            <h1>Mini-Dropbox Cloud Console</h1>
            <p className="subhead">
              Start services, ship files, and inspect replication health in one
              console.
            </p>
          </div>
          <div className="topbar-panel">
            <div className="search-field">
              <input
                type="search"
                placeholder="Search stored files"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <div className="action-row">
              <button className="primary" onClick={startSystem} disabled={busy}>
                Start system
              </button>
              <button className="ghost" onClick={stopSystem} disabled={busy}>
                Stop system
              </button>
              <button className="ghost" onClick={refreshAll} disabled={busy}>
                Refresh
              </button>
            </div>
          </div>
        </header>

        <section className="summary-grid">
          <article className="card summary" style={{ "--delay": "0ms" }}>
            <p className="label">Availability</p>
            <p className="value">{status ? `${availability}%` : "--"}</p>
            <p className="muted">Master and nodes online</p>
          </article>
          <article className="card summary" style={{ "--delay": "80ms" }}>
            <p className="label">Replication</p>
            <p className="value">{replication}x</p>
            <p className="muted">Total vs unique chunks</p>
          </article>
          <article className="card summary" style={{ "--delay": "160ms" }}>
            <p className="label">Stored data</p>
            <p className="value">{formatBytes(storageTotalBytes)}</p>
            <p className="muted">Across node stores</p>
          </article>
          <article className="card summary" style={{ "--delay": "240ms" }}>
            <p className="label">Files</p>
            <p className="value">{fileEntries.length}</p>
            <p className="muted">Total manifests</p>
          </article>
        </section>

        <section className="content-grid">
          <div className="column">
            <section className="card table" style={{ "--delay": "120ms" }}>
              <div className="card-header">
                <h2>Files</h2>
                <span className="pill info">
                  {filteredFiles.length} shown
                </span>
              </div>
              {filteredFiles.length ? (
                <div className="table">
                  <div className="table-head">
                    <span>Name</span>
                    <span>Chunks</span>
                    <span>Action</span>
                  </div>
                  {filteredFiles.map((entry) => (
                    <div className="table-row" key={entry.name}>
                      <div className="table-cell">
                        <p className="value">{entry.name}</p>
                        <p className="muted">Ready for download</p>
                      </div>
                      <span className="chip">
                        {entry.chunks !== null ? entry.chunks : "-"}
                      </span>
                      <button
                        className="ghost"
                        onClick={() => downloadFile(entry.name)}
                        disabled={busy}
                      >
                        Download
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">No files stored yet.</p>
              )}
            </section>

            <section className="card activity" style={{ "--delay": "200ms" }}>
              <div className="card-header">
                <h2>Activity</h2>
                <span className="pill info">Local cluster</span>
              </div>
              <div className="activity-list">
                <div className="activity-item">
                  <p className="value">No recent events</p>
                  <p className="muted">
                    Run uploads or downloads to populate activity.
                  </p>
                </div>
              </div>
            </section>
          </div>

          <div className="column">
            <section className="card upload" style={{ "--delay": "160ms" }}>
              <div className="card-header">
                <h2>Upload</h2>
                <span className="pill info">64 KB chunks</span>
              </div>
              <div className="upload-zone">
                <input
                  type="file"
                  id="file-input"
                  onChange={(event) =>
                    setSelectedFile(event.target.files?.[0] || null)
                  }
                />
                <label htmlFor="file-input" className="file-label">
                  {selectedFile ? selectedFile.name : "Choose a file"}
                </label>
                <p className="upload-meta">
                  {selectedFile
                    ? formatBytes(selectedFile.size)
                    : "Upload any file type"}
                </p>
              </div>
              <button className="primary" onClick={uploadFile} disabled={busy}>
                Upload
              </button>
            </section>

            <section className="card nodes" style={{ "--delay": "240ms" }}>
              <div className="card-header">
                <h2>Storage nodes</h2>
                <span className="pill info">Replication view</span>
              </div>
              {analysis ? (
                <div className="node-list">
                  <div className="node-row">
                    <div>
                      <p className="label">Node 1</p>
                      <p className="value">{analysis.node1.count} chunks</p>
                      <p className="muted">
                        {formatBytes(analysis.node1.size_bytes)}
                      </p>
                    </div>
                    <div className="progress small">
                      <span style={{ width: `${node1Share}%` }} />
                    </div>
                  </div>
                  <div className="node-row">
                    <div>
                      <p className="label">Node 2</p>
                      <p className="value">{analysis.node2.count} chunks</p>
                      <p className="muted">
                        {formatBytes(analysis.node2.size_bytes)}
                      </p>
                    </div>
                    <div className="progress small">
                      <span style={{ width: `${node2Share}%` }} />
                    </div>
                  </div>
                  <div className="node-row compact">
                    <div>
                      <p className="label">Unique chunks</p>
                      <p className="value">{analysis.unique_chunks}</p>
                    </div>
                    <div>
                      <p className="label">Total chunks</p>
                      <p className="value">{analysis.total_chunks}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="muted">Storage data not available.</p>
              )}
            </section>

            <section className="card verify" style={{ "--delay": "320ms" }}>
              <div className="card-header">
                <h2>Integrity check</h2>
                <span className="pill info">SHA-256</span>
              </div>
              <p className="muted">
                Run a quick replica comparison across storage nodes.
              </p>
              <button className="ghost" onClick={runVerify} disabled={busy}>
                Run integrity check
              </button>
              {verifyReport ? (
                <div className="verify-grid">
                  <div>
                    <p className="label">Verified</p>
                    <p className="value">{verifyReport.match}</p>
                  </div>
                  <div>
                    <p className="label">Incomplete</p>
                    <p className="value">{verifyReport.incomplete}</p>
                  </div>
                  <div>
                    <p className="label">Mismatched</p>
                    <p className="value">{verifyReport.mismatch}</p>
                  </div>
                </div>
              ) : (
                <p className="muted">No report yet.</p>
              )}
            </section>
          </div>
        </section>
      </div>

      {message ? (
        <div className={`toast ${message.type}`}>{message.text}</div>
      ) : null}
    </div>
  );
}
