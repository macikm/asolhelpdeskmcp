#!/bin/bash
# update.sh - Skript pro kontrolu nového kódu z Git repozitáře a automatickou aktualizaci Docker kontejneru

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔍 Kontroluji aktualizace z Git repozitáře..."

# Ověřit, zda je nastaven remote origin
if ! git remote get-url origin > /dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ Git remote 'origin' není nastaven."
    exit 1
fi

# Zjistit aktuální větev (main nebo master)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "HEAD" ] || [ -z "$BRANCH" ]; then
    BRANCH="main"
fi

# Stáhnout informace o změnách
git fetch origin "$BRANCH"

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Repozitář je aktuální ($BRANCH). Žádné nové změny."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 Zjištěna nová verze na Gitu ($BRANCH). Aktualizuji..."
    git pull origin "$BRANCH"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🛠️ Rebuilduji a restartuji Docker kontejner..."
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d --build
    else
        docker compose up -d --build
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🎉 Aktualizace úspěšně dokončena!"
fi
