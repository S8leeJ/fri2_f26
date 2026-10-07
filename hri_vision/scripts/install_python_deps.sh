#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r "$(dirname "$0")/../requirements.txt"

echo
echo "Python dependencies installed."
echo "If using camera_backend:=pyk4a, also install Azure Kinect Sensor SDK + pyk4a."
