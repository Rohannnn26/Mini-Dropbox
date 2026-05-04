# Mini-Dropbox: Manual Run Guide & File Overview

This guide explains how to run the Mini-Dropbox gRPC project directly using Python commands (without relying on `run.sh` or `start.sh`), and provides a breakdown of what each file in the project does.

## 🏃‍♂️ How to Run Without a Script (Manual Execution)

You can run this project entirely from standard command prompts or PowerShell windows. Because this is a distributed system, you will need to open **three separate terminal windows** (one for the master node, and two for the storage nodes).

### Prerequisites
Make sure your virtual environment is activated and dependencies are installed. In your `Mini-DropBox-gRPC` root directory:
```powershell
# Activate the virtual environment (Windows)
.venv\Scripts\activate

# (If needed) Install dependencies
python -m pip install grpcio grpcio-tools protobuf
```

### Step 1: Start the Master Node
Open your first terminal, activate the venv, and run:
```powershell
# Start the master node (listens on port 9000 by default)
python -m master.master
```
*(Leave this terminal running)*

### Step 2: Start Storage Node 1
Open a second terminal, activate the venv, and run:
```powershell
# Start the first storage node (listens on port 9001)
python -m storage_node.storage_node --id node1 --port 9001 --store node1_store
```
*(Leave this terminal running)*

### Step 3: Start Storage Node 2
Open a third terminal, activate the venv, and run:
```powershell
# Start the second storage node (listens on port 9002)
python -m storage_node.storage_node --id node2 --port 9002 --store node2_store
```
*(Leave this terminal running)*

### Step 4: Use the Client to Upload/Download Files
Open a fourth terminal (or just use an existing one if you backgrounded the other processes). Activate the venv and use the client to interact with the system:

**Upload a file:**
```powershell
# Upload 'hello.txt' to the distributed storage
python -m client.client upload --file hello.txt
```

**Download a file:**
```powershell
# Download 'hello.txt' and save it locally as 'downloaded_hello.txt'
python -m client.client download --file hello.txt --out downloaded_hello.txt
```

*(Note: To stop the system, simply press `Ctrl+C` in the terminals where the master and storage nodes are running).*

---

## 📁 What Each File Does

Here is a detailed breakdown of the project structure and the purpose of each file:

### Core Architecture
*   **`proto/dropbox.proto`**: The Protocol Buffers definition file. This is the heart of the gRPC architecture. It defines the structure of the messages (like `PutChunkRequest` or `GetManifestRequest`) and the RPC services (`MasterService` and `StorageService`) that allow the nodes to talk to each other.
*   **`proto/dropbox_pb2.py` & `proto/dropbox_pb2_grpc.py`**: Auto-generated Python code created from `dropbox.proto`. You never edit these manually; they contain the underlying classes and network stubs required to make gRPC calls.

### The Nodes (Servers)
*   **`master/master.py`**: The control plane of the system. It runs a gRPC server that keeps track of the file metadata (which files exist, what 64KB chunks they are split into, and which storage nodes hold those chunks). **It does not store file data**, only the map of where data lives.
*   **`storage_node/storage_node.py`**: The data plane. It runs a gRPC server that receives binary data chunks from clients and saves them to the local disk (e.g., inside the `node1_store` folder). It also serves chunks back to clients upon request. 

### The Client (User Interface)
*   **`client/client.py`**: The command-line interface for the user. When you upload a file, this script reads the file, splits it into 64KB chunks, calculates the SHA-256 hash for each chunk, asks the master where to store them, and then uploads the chunks to the storage nodes. During download, it asks the master for the chunk list, fetches them from the nodes, and reassembles the original file.

### Data Storage Directories
*   **`node1_store/` & `node2_store/`**: These folders act as the "hard drives" for Storage Node 1 and Storage Node 2. When you upload a file, you will see files appear in here. The filenames are the SHA-256 hashes of the file chunks. Because the replication factor is 2, you will see identical chunks in both folders.

### Utilities and Scripts
*   **`run.sh` / `Mini-Dropbox/start.sh`**: Bash wrappers designed to automate the manual steps outlined above (starting all 3 nodes in the background, verifying chunk integrity, etc.). Because bash scripts rely on Linux tools (like `lsof` or specific path formatting), they can sometimes be tricky to run on Windows, which is why the manual Python commands are often more reliable on Windows machines.
*   **`requirements.txt`**: A list of the Python packages required to run the system (`grpcio`, `grpcio-tools`, `protobuf`).
