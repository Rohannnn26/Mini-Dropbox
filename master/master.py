import grpc
from concurrent import futures
import sys
import time
sys.path.insert(0, '.')
from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

HOST = "127.0.0.1"
PORT = 9000

storage_nodes = []   # registered nodes: list of dicts with host, port, node_id
file_manifest = {}   # filename -> list of chunk_ids
chunk_locations = {} # chunk_id -> list of node dicts

class MasterServicer(dropbox_pb2_grpc.MasterServiceServicer):
    
    def RegisterNode(self, request, context):
        start_time = time.time()
        node = {
            "host": request.host,
            "port": request.port,
            "node_id": request.node_id
        }
        storage_nodes.append(node)
        elapsed = (time.time() - start_time) * 1000
        print(f"[master] Registered node: {request.node_id} at {request.host}:{request.port} ({elapsed:.2f}ms)")
        return dropbox_pb2.RegisterResponse(status="ok", message="Node registered")
    
    def RequestPutTargets(self, request, context):
        targets = []
        for node in storage_nodes[:2]:  # Return first 2 nodes for replication
            targets.append(dropbox_pb2.StorageNode(
                host=node["host"],
                port=node["port"],
                node_id=node.get("node_id", "")
            ))
        return dropbox_pb2.PutTargetsResponse(targets=targets)
    
    def AnnounceManifest(self, request, context):
        start_time = time.time()
        file_manifest[request.filename] = list(request.chunks)
        for cid in request.chunks:
            chunk_locations.setdefault(cid, storage_nodes[:])
        elapsed = (time.time() - start_time) * 1000
        print(f"[master] Manifest announced for file: {request.filename} ({len(request.chunks)} chunks, {elapsed:.2f}ms)")
        return dropbox_pb2.ManifestResponse(status="ok", message="Manifest stored")
    
    def ListFiles(self, request, context):
        return dropbox_pb2.ListFilesResponse(files=list(file_manifest.keys()))
    
    def GetManifest(self, request, context):
        chunks = file_manifest.get(request.filename, [])
        return dropbox_pb2.GetManifestResponse(chunks=chunks)
    
    def RequestGetTargets(self, request, context):
        targets = []
        nodes = chunk_locations.get(request.chunk_id, [])
        for node in nodes:
            targets.append(dropbox_pb2.StorageNode(
                host=node["host"],
                port=node["port"],
                node_id=node.get("node_id", "")
            ))
        return dropbox_pb2.GetTargetsResponse(targets=targets)

def main():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    dropbox_pb2_grpc.add_MasterServiceServicer_to_server(MasterServicer(), server)
    server.add_insecure_port(f"{HOST}:{PORT}")
    server.start()
    print(f"[master] gRPC server listening on {HOST}:{PORT}")
    server.wait_for_termination()

if __name__ == "__main__":
    main()
