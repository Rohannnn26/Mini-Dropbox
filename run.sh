#!/bin/bash

# Mini-Dropbox CLI - Distributed File Storage System
# Manages master node, storage nodes, and provides analysis tools

set -e

MASTER_PORT=9000
NODE1_PORT=9001
NODE2_PORT=9002
MASTER_HOST="127.0.0.1"

# Resolve Python from the local .venv, relative to this script's directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"   # Windows Git Bash (local venv)
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"            # Linux/WSL (local venv)
elif [ -f "$PARENT_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON="$PARENT_DIR/.venv/Scripts/python.exe"   # Windows Git Bash (parent venv)
elif [ -f "$PARENT_DIR/.venv/bin/python" ]; then
    PYTHON="$PARENT_DIR/.venv/bin/python"            # Linux/WSL (parent venv)
else
    PYTHON="python3"  # fallback to system python
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# PID tracking
MASTER_PID=""
NODE1_PID=""
NODE2_PID=""

#==============================================================================
# UTILITY FUNCTIONS
#==============================================================================

print_header() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

check_port() {
    # Works on Windows (Git Bash) and Linux — uses netstat which is available everywhere
    if netstat -ano 2>/dev/null | grep -q ":$1 .*LISTENING" || \
       netstat -tlnp 2>/dev/null | grep -q ":$1 "; then
        return 0
    else
        return 1
    fi
}

#==============================================================================
# SYSTEM MANAGEMENT
#==============================================================================

start_master() {
    print_info "Starting master node on port $MASTER_PORT..."
    cd "$SCRIPT_DIR" && "$PYTHON" -m master.master > /tmp/master.log 2>&1 &
    MASTER_PID=$!
    sleep 2
    if check_port $MASTER_PORT; then
        print_success "Master node started (PID: $MASTER_PID)"
    else
        print_error "Failed to start master node"
        cat /tmp/master.log
        exit 1
    fi
}

start_storage_nodes() {
    print_info "Starting storage node 1 on port $NODE1_PORT..."
    cd "$SCRIPT_DIR" && "$PYTHON" -m storage_node.storage_node --id node1 --port $NODE1_PORT --store node1_store > /tmp/node1.log 2>&1 &
    NODE1_PID=$!
    sleep 1
    
    print_info "Starting storage node 2 on port $NODE2_PORT..."
    cd "$SCRIPT_DIR" && "$PYTHON" -m storage_node.storage_node --id node2 --port $NODE2_PORT --store node2_store > /tmp/node2.log 2>&1 &
    NODE2_PID=$!
    sleep 1
    
    if check_port $NODE1_PORT && check_port $NODE2_PORT; then
        print_success "Storage nodes started (PIDs: $NODE1_PID, $NODE2_PID)"
    else
        print_error "Failed to start storage nodes"
        cat /tmp/node1.log /tmp/node2.log
        exit 1
    fi
}

stop_all() {
    print_info "Stopping all services..."
    
    # Kill Python processes listening on our ports
    for port in $MASTER_PORT $NODE1_PORT $NODE2_PORT; do
        # Windows netstat gives PID in last column for LISTENING entries
        PID=$(netstat -ano 2>/dev/null | grep ":$port " | grep "LISTENING" | awk '{print $NF}' | head -1 || echo "")
        if [ ! -z "$PID" ] && [ "$PID" != "0" ]; then
            taskkill //PID $PID //F >/dev/null 2>&1 || kill $PID 2>/dev/null || true
        fi
    done
    
    sleep 1
    print_success "All services stopped"
}

start_all() {
    print_header "Starting Mini-Dropbox System"
    
    # Check if already running
    if check_port $MASTER_PORT; then
        print_warning "Master already running on port $MASTER_PORT"
        read -p "Stop and restart? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            stop_all
            sleep 1
        else
            exit 0
        fi
    fi
    
    start_master
    start_storage_nodes
    
    echo ""
    print_success "Mini-Dropbox system is running!"
    print_info "Use './run.sh status' to check system health"
}

#==============================================================================
# FILE OPERATIONS
#==============================================================================

upload_file() {
    if [ ! -f "$1" ]; then
        print_error "File not found: $1"
        exit 1
    fi
    
    print_header "Uploading File: $(basename $1)"
    print_info "File size: $(du -h "$1" | cut -f1)"
    
    if ! check_port $MASTER_PORT; then
        print_error "Master node not running. Start with: ./run.sh start"
        exit 1
    fi
    
    cd "$SCRIPT_DIR" && "$PYTHON" -m client.client upload --file "$1"
    print_success "Upload complete"
}

download_file() {
    if [ -z "$2" ]; then
        print_error "Usage: ./run.sh download <filename> <output_path>"
        exit 1
    fi
    
    print_header "Downloading File: $1"
    
    if ! check_port $MASTER_PORT; then
        print_error "Master node not running. Start with: ./run.sh start"
        exit 1
    fi
    
    cd "$SCRIPT_DIR" && "$PYTHON" -m client.client download --file "$1" --out "$2"
    print_success "Download complete: $2"
}

list_files() {
    print_header "Files in Mini-Dropbox"
    
    if ! check_port $MASTER_PORT; then
        print_error "Master node not running"
        exit 1
    fi
    
    # Create temporary script using existing codebase
    cat > /tmp/list_files.py <<'PYEOF'
import sys
sys.path.insert(0, '.')
import grpc
from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:9000")
stub = dropbox_pb2_grpc.MasterServiceStub(channel)
request = dropbox_pb2.ListFilesRequest()
response = stub.ListFiles(request)
channel.close()

files = response.files
if files:
    for i, f in enumerate(files, 1):
        print(f"{i}. {f}")
else:
    print("No files stored")
PYEOF
    
    "$PYTHON" /tmp/list_files.py
    rm -f /tmp/list_files.py
}

#==============================================================================
# ANALYSIS & MONITORING
#==============================================================================

analyze_system() {
    print_header "Mini-Dropbox System Analysis"
    
    # System Status
    echo -e "\n${YELLOW}[SYSTEM STATUS]${NC}"
    if check_port $MASTER_PORT; then
        MASTER_PID=$(netstat -ano 2>/dev/null | grep ":$MASTER_PORT " | grep "LISTENING" | awk '{print $NF}' | head -1 || echo "?")
        print_success "Master Node: RUNNING (PID: $MASTER_PID, Port: $MASTER_PORT)"
    else
        print_error "Master Node: STOPPED"
    fi
    
    if check_port $NODE1_PORT; then
        N1_PID=$(netstat -ano 2>/dev/null | grep ":$NODE1_PORT " | grep "LISTENING" | awk '{print $NF}' | head -1 || echo "?")
        print_success "Storage Node 1: RUNNING (PID: $N1_PID, Port: $NODE1_PORT)"
    else
        print_error "Storage Node 1: STOPPED"
    fi
    
    if check_port $NODE2_PORT; then
        N2_PID=$(netstat -ano 2>/dev/null | grep ":$NODE2_PORT " | grep "LISTENING" | awk '{print $NF}' | head -1 || echo "?")
        print_success "Storage Node 2: RUNNING (PID: $N2_PID, Port: $NODE2_PORT)"
    else
        print_error "Storage Node 2: STOPPED"
    fi
    
    # Storage Analysis
    echo -e "\n${YELLOW}[STORAGE ANALYSIS]${NC}"
    
    if [ -d "node1_store" ]; then
        NODE1_COUNT=$(ls -1 node1_store 2>/dev/null | wc -l)
        NODE1_SIZE=$(du -sh node1_store 2>/dev/null | cut -f1)
        echo -e "  ${BLUE}Node 1 Storage:${NC}"
        echo -e "    • Chunks: $NODE1_COUNT"
        echo -e "    • Size: $NODE1_SIZE"
        echo -e "    • Location: $(pwd)/node1_store"
    fi
    
    if [ -d "node2_store" ]; then
        NODE2_COUNT=$(ls -1 node2_store 2>/dev/null | wc -l)
        NODE2_SIZE=$(du -sh node2_store 2>/dev/null | cut -f1)
        echo -e "  ${BLUE}Node 2 Storage:${NC}"
        echo -e "    • Chunks: $NODE2_COUNT"
        echo -e "    • Size: $NODE2_SIZE"
        echo -e "    • Location: $(pwd)/node2_store"
    fi
    
    # Chunk Hash Analysis (SHA-256)
    echo -e "\n${YELLOW}[CHUNK ANALYSIS - SHA-256 HASHED]${NC}"
    
    ALL_CHUNKS=$(find node1_store node2_store -type f 2>/dev/null | wc -l)
    UNIQUE_CHUNKS=$(find node1_store node2_store -type f -exec basename {} \; 2>/dev/null | sort -u | wc -l)
    
    echo -e "  ${BLUE}Total Chunks:${NC} $ALL_CHUNKS"
    echo -e "  ${BLUE}Unique Chunks:${NC} $UNIQUE_CHUNKS"
    echo -e "  ${BLUE}Replication Factor:${NC} $(awk "BEGIN {printf \"%.2f\", $ALL_CHUNKS/$UNIQUE_CHUNKS}")"
    
    # List chunks with details
    if [ $UNIQUE_CHUNKS -gt 0 ]; then
        echo -e "\n  ${BLUE}Chunk Distribution:${NC}"
        find node1_store node2_store -type f -exec basename {} \; 2>/dev/null | sort -u | while read chunk; do
            SIZE=$(find node1_store node2_store -name "$chunk" -exec du -h {} \; 2>/dev/null | head -1 | cut -f1)
            LOCATIONS=""
            [ -f "node1_store/$chunk" ] && LOCATIONS="${LOCATIONS}node1 "
            [ -f "node2_store/$chunk" ] && LOCATIONS="${LOCATIONS}node2"
            echo -e "    ${GREEN}${chunk:0:16}...${NC}"
            echo -e "      ├─ Size: $SIZE"
            echo -e "      └─ Replicas: [$LOCATIONS]"
        done
    fi
    
    # File Manifest Analysis
    if check_port $MASTER_PORT; then
        echo -e "\n${YELLOW}[FILE MANIFEST]${NC}"
        
        cat > /tmp/manifest_analysis.py <<'PYEOF'
import sys
sys.path.insert(0, '.')
import grpc
from proto import dropbox_pb2
from proto import dropbox_pb2_grpc

try:
    channel = grpc.insecure_channel("127.0.0.1:9000")
    stub = dropbox_pb2_grpc.MasterServiceStub(channel)
    
    # List files
    list_request = dropbox_pb2.ListFilesRequest()
    list_response = stub.ListFiles(list_request)
    files = list_response.files
    
    if files:
        print(f"  Total Files: {len(files)}")
        print(f"\n  Files:")
        for f in files:
            # Get manifest for each file
            manifest_request = dropbox_pb2.GetManifestRequest(filename=f)
            manifest_response = stub.GetManifest(manifest_request)
            chunks = manifest_response.chunks
            print(f"    • {f}")
            print(f"      └─ Chunks: {len(chunks)}")
    else:
        print("  No files stored in system")
    
    channel.close()
except Exception as e:
    print(f"  Error querying master: {e}")
PYEOF
        
        "$PYTHON" /tmp/manifest_analysis.py
        rm -f /tmp/manifest_analysis.py
    fi
    
    # Network Analysis
    echo -e "\n${YELLOW}[NETWORK CONFIGURATION]${NC}"
    echo -e "  ${BLUE}Protocol:${NC} gRPC (Protocol Buffers)"
    echo -e "  ${BLUE}Master:${NC} ${MASTER_HOST}:${MASTER_PORT}"
    echo -e "  ${BLUE}Node 1:${NC} ${MASTER_HOST}:${NODE1_PORT}"
    echo -e "  ${BLUE}Node 2:${NC} ${MASTER_HOST}:${NODE2_PORT}"
    echo -e "  ${BLUE}Chunk Size:${NC} 64 KB"
    echo -e "  ${BLUE}Hash Algorithm:${NC} SHA-256"
    
    echo ""
}

verify_chunks() {
    print_header "Chunk Integrity Verification (SHA-256)"
    
    echo -e "\n${YELLOW}Verifying chunk integrity across storage nodes...${NC}\n"
    
    cat > /tmp/verify_chunks.py <<'PYEOF'
import sys
sys.path.insert(0, '.')
import os
import hashlib

def verify_chunk_pair(chunk_id, node1_path, node2_path):
    """Verify that replicated chunks are identical"""
    exists_n1 = os.path.exists(node1_path)
    exists_n2 = os.path.exists(node2_path)
    
    if exists_n1 and exists_n2:
        with open(node1_path, 'rb') as f1, open(node2_path, 'rb') as f2:
            data1 = f1.read()
            data2 = f2.read()
            
            if data1 == data2:
                size = len(data1)
                actual_hash = hashlib.sha256(data1).hexdigest()
                return "MATCH", size, actual_hash
            else:
                return "MISMATCH", None, None
    elif exists_n1 or exists_n2:
        return "INCOMPLETE", None, None
    else:
        return "MISSING", None, None

# Get all unique chunks
all_chunks = set()
if os.path.exists('node1_store'):
    all_chunks.update(os.listdir('node1_store'))
if os.path.exists('node2_store'):
    all_chunks.update(os.listdir('node2_store'))

if not all_chunks:
    print("  No chunks found in storage")
else:
    stats = {"match": 0, "mismatch": 0, "incomplete": 0}
    
    for chunk_id in sorted(all_chunks):
        n1_path = os.path.join('node1_store', chunk_id)
        n2_path = os.path.join('node2_store', chunk_id)
        
        status, size, actual_hash = verify_chunk_pair(chunk_id, n1_path, n2_path)
        
        if status == "MATCH":
            stats["match"] += 1
            print(f"  ✓ {chunk_id[:32]}...")
            print(f"    ├─ Status: VERIFIED")
            print(f"    ├─ Size: {size} bytes")
            print(f"    └─ SHA-256: {actual_hash[:32]}...")
        elif status == "MISMATCH":
            stats["mismatch"] += 1
            print(f"  ✗ {chunk_id[:32]}...")
            print(f"    └─ Status: MISMATCH (data differs between nodes)")
        elif status == "INCOMPLETE":
            stats["incomplete"] += 1
            print(f"  ⚠ {chunk_id[:32]}...")
            print(f"    └─ Status: INCOMPLETE (exists on only one node)")
    
    print(f"\n  Summary:")
    print(f"    • Verified: {stats['match']}")
    print(f"    • Mismatched: {stats['mismatch']}")
    print(f"    • Incomplete: {stats['incomplete']}")
PYEOF
    
    "$PYTHON" /tmp/verify_chunks.py
    rm -f /tmp/verify_chunks.py
    echo ""
}

monitor_live() {
    print_header "Live System Monitor (Press Ctrl+C to stop)"
    
    while true; do
        clear
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}  Mini-Dropbox Live Monitor - $(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        # Service status
        echo -e "\n${YELLOW}Services:${NC}"
        for port in $MASTER_PORT $NODE1_PORT $NODE2_PORT; do
            if check_port $port; then
                PID=$(netstat -ano 2>/dev/null | grep ":$port " | grep "LISTENING" | awk '{print $NF}' | head -1 || echo "?")
                CPU=$(ps -p $PID -o %cpu= 2>/dev/null || echo "0.0")
                MEM=$(ps -p $PID -o %mem= 2>/dev/null || echo "0.0")
                
                if [ $port -eq $MASTER_PORT ]; then
                    NAME="Master"
                elif [ $port -eq $NODE1_PORT ]; then
                    NAME="Node 1"
                else
                    NAME="Node 2"
                fi
                
                echo -e "  ${GREEN}●${NC} $NAME (Port $port) - CPU: ${CPU}% | MEM: ${MEM}%"
            else
                echo -e "  ${RED}●${NC} Port $port - OFFLINE"
            fi
        done
        
        # Storage stats
        echo -e "\n${YELLOW}Storage:${NC}"
        NODE1_COUNT=$(ls -1 node1_store 2>/dev/null | wc -l)
        NODE2_COUNT=$(ls -1 node2_store 2>/dev/null | wc -l)
        NODE1_SIZE=$(du -sh node1_store 2>/dev/null | cut -f1)
        NODE2_SIZE=$(du -sh node2_store 2>/dev/null | cut -f1)
        
        echo -e "  Node 1: $NODE1_COUNT chunks ($NODE1_SIZE)"
        echo -e "  Node 2: $NODE2_COUNT chunks ($NODE2_SIZE)"
        
        # Recent log activity
        echo -e "\n${YELLOW}Recent Activity:${NC}"
        if [ -f "/tmp/master.log" ]; then
            tail -3 /tmp/master.log 2>/dev/null | sed 's/^/  /'
        fi
        
        sleep 2
    done
}

#==============================================================================
# HELP & USAGE
#==============================================================================

show_usage() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Mini-Dropbox CLI - Distributed File Storage System${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${YELLOW}SYSTEM MANAGEMENT:${NC}"
    echo "  ./run.sh start              Start all services (master + 2 storage nodes)"
    echo "  ./run.sh stop               Stop all services"
    echo "  ./run.sh restart            Restart all services"
    echo "  ./run.sh status             Check system status"
    echo ""
    echo -e "${YELLOW}FILE OPERATIONS:${NC}"
    echo "  ./run.sh upload <file>      Upload file to Mini-Dropbox"
    echo "  ./run.sh download <name> <out>  Download file from Mini-Dropbox"
    echo "  ./run.sh list               List all stored files"
    echo ""
    echo -e "${YELLOW}ANALYSIS & MONITORING:${NC}"
    echo "  ./run.sh analyze            Full system analysis (storage, chunks, SHA-256)"
    echo "  ./run.sh verify             Verify chunk integrity across nodes"
    echo "  ./run.sh monitor            Live system monitoring (real-time)"
    echo ""
    echo -e "${YELLOW}EXAMPLES:${NC}"
    echo "  ./run.sh start"
    echo "  ./run.sh upload hello.txt"
    echo "  ./run.sh list"
    echo "  ./run.sh analyze"
    echo "  ./run.sh download hello.txt hello_downloaded.txt"
    echo "  ./run.sh verify"
    echo "  ./run.sh monitor"
    echo ""
    echo -e "${YELLOW}TECHNICAL DETAILS:${NC}"
    echo "  • Chunk Size: 64 KB"
    echo "  • Hash Algorithm: SHA-256 (content-addressable storage)"
    echo "  • Replication Factor: 2 nodes per chunk"
    echo "  • Network Protocol: gRPC (Protocol Buffers)"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

#==============================================================================
# MAIN COMMAND ROUTER
#==============================================================================

case "$1" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 1
        start_all
        ;;
    status)
        analyze_system
        ;;
    upload)
        if [ -z "$2" ]; then
            print_error "Usage: ./run.sh upload <file>"
            exit 1
        fi
        upload_file "$2"
        ;;
    download)
        download_file "$2" "$3"
        ;;
    list)
        list_files
        ;;
    analyze)
        analyze_system
        ;;
    verify)
        verify_chunks
        ;;
    monitor)
        monitor_live
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
