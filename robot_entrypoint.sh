#!/bin/bash
# Garante que o script para se houver algum erro grave
set -e

echo "Iniciando o Virtual FrameBuffer (Xvfb)..."
# Inicia o Python dentro do ecrã virtual com resolução Full HD
xvfb-run --auto-servernum --server-args="-screen 0 1920x1080x24" python robot/main.py