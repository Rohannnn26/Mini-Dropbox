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

export default function App() {
  const [status, setStatus] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const apiOnline = useMemo(() => !!status, [status]);

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

  useEffect(() => {
    refreshAll();
  }, []);

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">Mini-Dropbox Control Room</p>
          <h1>Operate your distributed storage system with confidence.</h1>
          <p className="subhead">
            Launch services, upload files, and inspect replication health in one
            place.
          </p>
        </div>
        <div className="hero-actions">
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
      </header>

      <main className="grid">
        <section className="card status">
          <div className="card-header">
            <h2>Service status</h2>
            <span className={`pill ${apiOnline ? "ok" : "warn"}`}>
              API {apiOnline ? "online" : "offline"}
            </span>
          </div>
          {status ? (
            <div className="status-list">
              <div className="status-row">
                <div>
                  <p className="label">Master</p>
                  <p className="value">
                    {status.master.host}:{status.master.port}
                  </p>
                </div>
                <span className={`pill ${status.master.running ? "ok" : "warn"}`}>
                  {status.master.running ? "Running" : "Stopped"}
                </span>
              </div>
              {status.nodes.map((node) => (
                <div className="status-row" key={node.name}>
                  <div>
                    <p className="label">{node.name.toUpperCase()}</p>
                    <p className="value">
                      {node.host}:{node.port}
                    </p>
                  </div>
                  <span className={`pill ${node.running ? "ok" : "warn"}`}>
                    {node.running ? "Running" : "Stopped"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">API offline. Start the backend to see status.</p>
          )}
        </section>

        <section className="card upload">
          <div className="card-header">
            <h2>Upload a file</h2>
            <span className="pill info">64 KB chunks</span>
          </div>
          <div className="upload-box">
            <input
              type="file"
              id="file-input"
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            />
            <label htmlFor="file-input" className="file-label">
              {selectedFile ? selectedFile.name : "Choose a file"}
            </label>
          </div>
          <button className="primary" onClick={uploadFile} disabled={busy}>
            Upload
          </button>
        </section>

        <section className="card files">
          <div className="card-header">
            <h2>Stored files</h2>
            <span className="pill info">{files.length} total</span>
          </div>
          {files.length ? (
            <div className="file-list">
              {files.map((name) => (
                <div className="file-row" key={name}>
                  <div>
                    <p className="value">{name}</p>
                    <p className="muted">Ready for download</p>
                  </div>
                  <button
                    className="ghost"
                    onClick={() => downloadFile(name)}
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

        <section className="card analysis">
          <div className="card-header">
            <h2>Storage analysis</h2>
            <span className="pill info">Replication view</span>
          </div>
          {analysis ? (
            <div className="analysis-grid">
              <div>
                <p className="label">Node 1</p>
                <p className="value">{analysis.node1.count} chunks</p>
                <p className="muted">{formatBytes(analysis.node1.size_bytes)}</p>
              </div>
              <div>
                <p className="label">Node 2</p>
                <p className="value">{analysis.node2.count} chunks</p>
                <p className="muted">{formatBytes(analysis.node2.size_bytes)}</p>
              </div>
              <div>
                <p className="label">Unique chunks</p>
                <p className="value">{analysis.unique_chunks}</p>
                <p className="muted">Across all nodes</p>
              </div>
              <div>
                <p className="label">Total chunks</p>
                <p className="value">{analysis.total_chunks}</p>
                <p className="muted">Replicated copies</p>
              </div>
            </div>
          ) : (
            <p className="muted">No analysis available.</p>
          )}
        </section>
      </main>

      {message ? (
        <div className={`toast ${message.type}`}>{message.text}</div>
      ) : null}
    </div>
  );
}
