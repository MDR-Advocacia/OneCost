#!/bin/bash
# Script para abrir o Google Chrome com modo de depuração no macOS

# O caminho pode variar. Verifique o seu em "chrome://version"
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE_PATH="$HOME/chrome-dev-profile-onenotify"

echo "[🌐] Abrindo Google Chrome com depuração remota..."
echo "Usando perfil em: $PROFILE_PATH"

"$CHROME_PATH" --remote-debugging-port=9222 --user-data-dir="$PROFILE_PATH" &

echo "[✔] Chrome aberto."

