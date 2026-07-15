#!/usr/bin/env bash
set -euo pipefail

#backend
echo "Building backend..."
cd ai-core
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
prisma generate


echo "Building frontend..."
#frontend
cd ../client
npm ci
npm run build



# restart app
sudo /bin/systemctl restart chatbot.service
echo "chatbot.service restarted."
