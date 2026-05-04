import grpc
from concurrent import futures
import os
import argparse
import sys
import time
sys.path.insert(0, '.')
from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

MASTER_HOST = "127.0.0.1"
MASTER_PORT = 9000

class StorageServicer(dropbox_pb2_grpc.StorageServiceServicer):
    
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
    
    def PutChunk(self, request, context):
        try:
            start_time = time.time()
            cid = request.chunk_id
            data = request.data
            path = os.path.join(self.storage_dir, cid)
            with open(path, "wb") as f:
                f.write(data)
            elapsed = (time.time() - start_time) * 1000
            size_kb = len(data) / 1024
            print(f"[storage] Stored chunk {cid[:16]}... ({size_kb:.2f}KB, {elapsed:.2f}ms)")
            return dropbox_pb2.PutChunkResponse(status="ok", message="Chunk stored")
        except Exception as e:
            print(f"[storage] Error storing chunk: {e}")
            return dropbox_pb2.PutChunkResponse(status="error", message=str(e))
    
    def GetChunk(self, request, context):
        try:
            start_time = time.time()
            cid = request.chunk_id
            path = os.path.join(self.storage_dir, cid)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    data = f.read()
                elapsed = (time.time() - start_time) * 1000
                size_kb = len(data) / 1024
                print(f"[storage] Retrieved chunk {cid[:16]}... ({size_kb:.2f}KB, {elapsed:.2f}ms)")
                return dropbox_pb2.GetChunkResponse(status="ok", data=data, message="")
            else:
                print(f"[storage] Chunk not found: {cid[:16]}...")
                return dropbox_pb2.GetChunkResponse(status="error", data=b"", message="Chunk not found")
        except Exception as e:
            print(f"[storage] Error retrieving chunk: {e}")
            return dropbox_pb2.GetChunkResponse(status="error", data=b"", message=str(e))

def register_with_master(host, port, node_id):
    channel = grpc.insecure_channel(f"{MASTER_HOST}:{MASTER_PORT}")
    stub = dropbox_pb2_grpc.MasterServiceStub(channel)
    request = dropbox_pb2.RegisterRequest(host=host, port=port, node_id=node_id)
    response = stub.RegisterNode(request)
    channel.close()
    print(f"[storage] Node '{node_id}' registered with master: {response.status}")

def main(node_id, port, storage_dir):
    os.makedirs(storage_dir, exist_ok=True)
    register_with_master("127.0.0.1", port, node_id)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    dropbox_pb2_grpc.add_StorageServiceServicer_to_server(
        StorageServicer(storage_dir), server
    )
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    print(f"[storage] Node '{node_id}' gRPC server listening on 127.0.0.1:{port}")
    server.wait_for_termination()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Node ID")
    parser.add_argument("--port", type=int, required=True, help="Port number")
    parser.add_argument("--store", required=True, help="Storage folder")
    args = parser.parse_args()

    main(args.id, args.port, args.store)
