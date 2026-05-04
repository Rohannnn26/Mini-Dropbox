import grpc
import os
import hashlib
import argparse
import sys
import time
sys.path.insert(0, '.')
from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000
CHUNK_SIZE = 1024 * 64  # 64 KB

def chunk_file(path):
    start_time = time.time()
    chunks = []
    with open(path, "rb") as f:
        idx = 0
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            chunk_id = hashlib.sha256(data + str(idx).encode()).hexdigest()
            chunks.append((chunk_id, data))
            idx += 1
    elapsed = (time.time() - start_time) * 1000
    file_size = os.path.getsize(path)
    print(f"[client] Chunked file into {len(chunks)} pieces ({file_size/1024:.2f}KB total, {elapsed:.2f}ms)")
    return chunks

def get_master_stub():
    channel = grpc.insecure_channel(f"{MASTER_HOST}:{MASTER_PORT}")
    return dropbox_pb2_grpc.MasterServiceStub(channel), channel

def get_storage_stub(host, port):
    channel = grpc.insecure_channel(f"{host}:{port}")
    return dropbox_pb2_grpc.StorageServiceStub(channel), channel

def push_chunk_to_node(node, chunk_id, data, version=1):
    start_time = time.time()
    stub, channel = get_storage_stub(node.host, node.port)
    request = dropbox_pb2.PutChunkRequest(chunk_id=chunk_id, data=data, version=version)
    response = stub.PutChunk(request)
    channel.close()
    elapsed = (time.time() - start_time) * 1000
    size_kb = len(data) / 1024
    print(f"[client] Transferred chunk {chunk_id[:16]}... to {node.host}:{node.port} ({size_kb:.2f}KB, {elapsed:.2f}ms)")
    return response

def get_chunk_from_node(node, chunk_id):
    start_time = time.time()
    stub, channel = get_storage_stub(node.host, node.port)
    request = dropbox_pb2.GetChunkRequest(chunk_id=chunk_id)
    response = stub.GetChunk(request)
    channel.close()
    elapsed = (time.time() - start_time) * 1000
    if response.status == "ok":
        size_kb = len(response.data) / 1024
        print(f"[client] Fetched chunk {chunk_id[:16]}... from {node.host}:{node.port} ({size_kb:.2f}KB, {elapsed:.2f}ms)")
        return response.data
    else:
        print(f"[client] Failed to fetch chunk {chunk_id[:16]}... from {node.host}:{node.port} ({elapsed:.2f}ms)")
    return None

def upload_file(filepath):
    overall_start = time.time()
    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    
    print(f"[client] Starting upload: {filename} ({file_size/1024:.2f}KB)")
    chunks = chunk_file(filepath)
    chunk_ids = [cid for cid, _ in chunks]

    stub, channel = get_master_stub()
    
    transfer_start = time.time()
    for cid, data in chunks:
        # Request put targets
        request = dropbox_pb2.PutTargetsRequest(chunk_id=cid)
        response = stub.RequestPutTargets(request)
        targets = response.targets
        
        if not targets:
            raise Exception("No storage nodes available")
        
        # Upload to each target
        for node in targets:
            r = push_chunk_to_node(node, cid, data, version=1)
            if r.status != "ok":
                print(f"[client] failed to push to {node.host}:{node.port}")
    
    transfer_elapsed = (time.time() - transfer_start) * 1000

    # Announce manifest
    manifest_request = dropbox_pb2.ManifestRequest(filename=filename, chunks=chunk_ids)
    stub.AnnounceManifest(manifest_request)
    channel.close()
    
    overall_elapsed = (time.time() - overall_start) * 1000
    print(f"[client] Upload complete: {filename}")
    print(f"[client] Total time: {overall_elapsed:.2f}ms (Transfer: {transfer_elapsed:.2f}ms, {len(chunks)} chunks to {len(targets)} nodes)")

def download_file(filename, outpath):
    overall_start = time.time()
    print(f"[client] Starting download: {filename}")
    
    stub, channel = get_master_stub()
    
    # Get manifest
    request = dropbox_pb2.GetManifestRequest(filename=filename)
    response = stub.GetManifest(request)
    chunks = response.chunks
    
    if not chunks:
        print("file not found")
        channel.close()
        return

    print(f"[client] Fetching {len(chunks)} chunks...")
    fetch_start = time.time()
    assembled = b""
    for cid in chunks:
        # Request get targets
        targets_request = dropbox_pb2.GetTargetsRequest(chunk_id=cid)
        targets_response = stub.RequestGetTargets(targets_request)
        targets = targets_response.targets
        
        got = None
        for node in targets:
            data = get_chunk_from_node(node, cid)
            if data is not None:
                got = data
                break
        
        if got is None:
            raise Exception("Failed to fetch chunk " + cid)
        assembled += got
    
    fetch_elapsed = (time.time() - fetch_start) * 1000
    channel.close()
    
    with open(outpath, "wb") as f:
        f.write(assembled)
    
    overall_elapsed = (time.time() - overall_start) * 1000
    file_size = len(assembled) / 1024
    print(f"[client] Download complete: {outpath} ({file_size:.2f}KB)")
    print(f"[client] Total time: {overall_elapsed:.2f}ms (Fetch: {fetch_elapsed:.2f}ms, {len(chunks)} chunks)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("op", choices=["upload","download"])
    parser.add_argument("--file", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.op == "upload":
        upload_file(args.file)
    else:
        if not args.out:
            raise SystemExit("provide --out path")
        download_file(args.file, args.out)
