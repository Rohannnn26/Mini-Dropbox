from __future__ import annotations

import hashlib
import io
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import grpc
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000
NODE1_PORT = 9001
NODE2_PORT = 9002
CHUNK_SIZE = 64 * 1024

LOG_DIR = ROOT_DIR / "web_api" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PROCESSES: dict[str, subprocess.Popen] = {}
LOG_HANDLES: dict[str, io.TextIOBase] = {}

app = FastAPI(title="Mini-Dropbox API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _spawn_process(name: str, args: list[str], log_name: str) -> bool:
    existing = PROCESSES.get(name)
    if existing and existing.poll() is None:
        return False

    log_path = LOG_DIR / f"{log_name}.log"
    log_file = open(log_path, "a", encoding="utf-8")
    LOG_HANDLES[name] = log_file

    popen_kwargs = {
        "cwd": str(ROOT_DIR),
        "stdout": log_file,
        "stderr": log_file,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(args, **popen_kwargs)
    PROCESSES[name] = process
    return True


def _stop_process(name: str) -> bool:
    process = PROCESSES.get(name)
    if not process or process.poll() is not None:
        return False

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    return True


def _status_payload() -> dict:
    return {
        "master": {
            "host": MASTER_HOST,
            "port": MASTER_PORT,
            "running": _is_port_open(MASTER_HOST, MASTER_PORT),
            "pid": PROCESSES.get("master").pid if PROCESSES.get("master") else None,
        },
        "nodes": [
            {
                "name": "node1",
                "host": MASTER_HOST,
                "port": NODE1_PORT,
                "running": _is_port_open(MASTER_HOST, NODE1_PORT),
                "pid": PROCESSES.get("node1").pid if PROCESSES.get("node1") else None,
            },
            {
                "name": "node2",
                "host": MASTER_HOST,
                "port": NODE2_PORT,
                "running": _is_port_open(MASTER_HOST, NODE2_PORT),
                "pid": PROCESSES.get("node2").pid if PROCESSES.get("node2") else None,
            },
        ],
    }


def _get_master_stub():
    channel = grpc.insecure_channel(f"{MASTER_HOST}:{MASTER_PORT}")
    return dropbox_pb2_grpc.MasterServiceStub(channel), channel


def _get_storage_stub(host: str, port: int):
    channel = grpc.insecure_channel(f"{host}:{port}")
    return dropbox_pb2_grpc.StorageServiceStub(channel), channel


def _iter_chunks(file_obj):
    idx = 0
    while True:
        data = file_obj.read(CHUNK_SIZE)
        if not data:
            break
        chunk_id = hashlib.sha256(data + str(idx).encode()).hexdigest()
        yield chunk_id, data
        idx += 1


def _fetch_chunk(node, chunk_id: str) -> bytes | None:
    stub, channel = _get_storage_stub(node.host, node.port)
    request = dropbox_pb2.GetChunkRequest(chunk_id=chunk_id)
    response = stub.GetChunk(request)
    channel.close()
    if response.status == "ok":
        return response.data
    return None


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    return _status_payload()


@app.post("/api/start")
async def start_system():
    started = []
    if not _is_port_open(MASTER_HOST, MASTER_PORT):
        if _spawn_process("master", [sys.executable, "-m", "master.master"], "master"):
            started.append("master")

    if not _is_port_open(MASTER_HOST, NODE1_PORT):
        if _spawn_process(
            "node1",
            [
                sys.executable,
                "-m",
                "storage_node.storage_node",
                "--id",
                "node1",
                "--port",
                str(NODE1_PORT),
                "--store",
                "node1_store",
            ],
            "node1",
        ):
            started.append("node1")

    if not _is_port_open(MASTER_HOST, NODE2_PORT):
        if _spawn_process(
            "node2",
            [
                sys.executable,
                "-m",
                "storage_node.storage_node",
                "--id",
                "node2",
                "--port",
                str(NODE2_PORT),
                "--store",
                "node2_store",
            ],
            "node2",
        ):
            started.append("node2")

    time.sleep(0.5)
    return {"started": started, "status": _status_payload()}


@app.post("/api/stop")
async def stop_system():
    stopped = []
    for name in ("node2", "node1", "master"):
        if _stop_process(name):
            stopped.append(name)
    return {"stopped": stopped, "status": _status_payload()}


@app.get("/api/files")
async def list_files():
    if not _is_port_open(MASTER_HOST, MASTER_PORT):
        raise HTTPException(status_code=503, detail="master is not running")

    stub, channel = _get_master_stub()
    response = stub.ListFiles(dropbox_pb2.ListFilesRequest())
    channel.close()
    return {"files": list(response.files)}


@app.post("/api/upload")
def upload_file(file: UploadFile = File(...)):
    if not _is_port_open(MASTER_HOST, MASTER_PORT):
        raise HTTPException(status_code=503, detail="master is not running")

    filename = file.filename or "upload.bin"
    stub, channel = _get_master_stub()

    chunk_ids = []
    bytes_total = 0
    start_time = time.time()

    for chunk_id, data in _iter_chunks(file.file):
        chunk_ids.append(chunk_id)
        bytes_total += len(data)

        targets_response = stub.RequestPutTargets(
            dropbox_pb2.PutTargetsRequest(chunk_id=chunk_id)
        )
        targets = targets_response.targets
        if not targets:
            channel.close()
            raise HTTPException(status_code=500, detail="no storage nodes available")

        for node in targets:
            storage_stub, storage_channel = _get_storage_stub(node.host, node.port)
            request = dropbox_pb2.PutChunkRequest(
                chunk_id=chunk_id, data=data, version=1
            )
            response = storage_stub.PutChunk(request)
            storage_channel.close()
            if response.status != "ok":
                channel.close()
                raise HTTPException(
                    status_code=500,
                    detail=f"failed to store chunk on {node.host}:{node.port}",
                )

    stub.AnnounceManifest(
        dropbox_pb2.ManifestRequest(filename=filename, chunks=chunk_ids)
    )
    channel.close()

    elapsed_ms = (time.time() - start_time) * 1000
    return {
        "filename": filename,
        "chunks": len(chunk_ids),
        "bytes": bytes_total,
        "elapsed_ms": round(elapsed_ms, 2),
    }


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    if not _is_port_open(MASTER_HOST, MASTER_PORT):
        raise HTTPException(status_code=503, detail="master is not running")

    stub, channel = _get_master_stub()
    response = stub.GetManifest(dropbox_pb2.GetManifestRequest(filename=filename))
    chunk_ids = list(response.chunks)
    if not chunk_ids:
        channel.close()
        raise HTTPException(status_code=404, detail="file not found")

    assembled = bytearray()
    for chunk_id in chunk_ids:
        targets_response = stub.RequestGetTargets(
            dropbox_pb2.GetTargetsRequest(chunk_id=chunk_id)
        )
        data = None
        for node in targets_response.targets:
            data = _fetch_chunk(node, chunk_id)
            if data is not None:
                break
        if data is None:
            channel.close()
            raise HTTPException(status_code=500, detail="failed to fetch chunk")
        assembled += data

    channel.close()
    safe_name = os.path.basename(filename)
    return StreamingResponse(
        io.BytesIO(assembled),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"{safe_name}\""},
    )


@app.get("/api/analysis")
async def analyze():
    node1_path = ROOT_DIR / "node1_store"
    node2_path = ROOT_DIR / "node2_store"

    def store_stats(path: Path):
        if not path.exists():
            return {"count": 0, "size_bytes": 0}
        files = [p for p in path.iterdir() if p.is_file()]
        return {
            "count": len(files),
            "size_bytes": sum(p.stat().st_size for p in files),
        }

    node1 = store_stats(node1_path)
    node2 = store_stats(node2_path)

    unique_chunks = set()
    for path in (node1_path, node2_path):
        if path.exists():
            unique_chunks.update(p.name for p in path.iterdir() if p.is_file())

    files = []
    if _is_port_open(MASTER_HOST, MASTER_PORT):
        stub, channel = _get_master_stub()
        list_resp = stub.ListFiles(dropbox_pb2.ListFilesRequest())
        for name in list_resp.files:
            manifest = stub.GetManifest(dropbox_pb2.GetManifestRequest(filename=name))
            files.append({"name": name, "chunks": len(manifest.chunks)})
        channel.close()

    return {
        "node1": node1,
        "node2": node2,
        "total_chunks": node1["count"] + node2["count"],
        "unique_chunks": len(unique_chunks),
        "files": files,
    }


@app.get("/api/verify")
async def verify():
    node1_path = ROOT_DIR / "node1_store"
    node2_path = ROOT_DIR / "node2_store"

    all_chunks = set()
    if node1_path.exists():
        all_chunks.update(p.name for p in node1_path.iterdir() if p.is_file())
    if node2_path.exists():
        all_chunks.update(p.name for p in node2_path.iterdir() if p.is_file())

    stats = {"match": 0, "mismatch": 0, "incomplete": 0}
    for chunk_id in sorted(all_chunks):
        n1 = node1_path / chunk_id
        n2 = node2_path / chunk_id
        e1, e2 = n1.exists(), n2.exists()
        if e1 and e2:
            d1 = n1.read_bytes()
            d2 = n2.read_bytes()
            if d1 == d2:
                stats["match"] += 1
            else:
                stats["mismatch"] += 1
        elif e1 or e2:
            stats["incomplete"] += 1

    return JSONResponse(stats)
