#!/bin/bash
# Build script: compila frontend e copia pra pasta static do backend
set -e

echo "=== Instalando dependências do frontend ==="
cd frontend
npm install

echo "=== Buildando frontend ==="
npm run build

echo "=== Copiando build pro backend ==="
rm -rf ../backend/static
cp -r dist ../backend/static

echo "=== Instalando dependências do backend ==="
cd ../backend
pip install -r requirements.txt

echo "=== Build completo ==="
