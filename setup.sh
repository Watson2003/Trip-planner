#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

mkdir -p "$BACKEND_DIR" "$FRONTEND_DIR"

cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cat > .env <<'EOF'
NVIDIA_API_KEY=your_key_here
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
OPENWEATHERMAP_API_KEY=your_key_here
OPENROUTESERVICE_API_KEY=your_key_here
EOF
fi

cd "$FRONTEND_DIR"

node_major="$(node -p "process.versions.node.split('.')[0]")"
if [ "$node_major" -lt 18 ]; then
  echo "Node.js 18 or newer is required. Current version: $(node -v)" >&2
  exit 1
fi

npm install
