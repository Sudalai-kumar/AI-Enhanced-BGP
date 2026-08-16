#!/usr/bin/env bash
# Deploy script for Containerlab on Linux / WSL2
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
TOPOLOGY_FILE="${DIR}/../topologies/bgp_multi_as.clab.yml"

echo "=========================================================="
echo " Deploying BGP Multi-AS Topology via Containerlab"
echo " Image Pinned: quay.io/frrouting/frr:10.2.1"
echo "=========================================================="

if ! command -v clab &> /dev/null; then
    echo "[!] Containerlab ('clab') is not installed in this environment."
    echo "[*] Install with: bash -c \"\$(curl -sL https://get.containerlab.dev)\""
    exit 1
fi

sudo clab deploy -t "${TOPOLOGY_FILE}" --reconfigure
echo "[✓] Containerlab deployment complete."
