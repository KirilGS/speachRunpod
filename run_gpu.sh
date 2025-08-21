#!/usr/bin/env bash
set -euo pipefail

COMFY_DIR="/workspace/ComfyUI"   # поправь, если другой путь
VENV_DIR="$COMFY_DIR/venv"       # оставляю твоё имя venv

cd "$COMFY_DIR"

# упадём, если venv не найден (иначе source может молча проигнориться)
[ -f "$VENV_DIR/bin/activate" ] || { echo "No venv at $VENV_DIR"; exit 1; }

source "$VENV_DIR/bin/activate"

# полезные переменные (кашь HuggingFace переживёт рестарты, логи без буфера)
export HF_HOME="/workspace/.cache/huggingface"
export PYTHONUNBUFFERED=1

# короткая диагностика в логи
python - <<'PY'
import sys, os
print(">>> python:", sys.executable)
print(">>> VIRTUAL_ENV:", os.getenv("VIRTUAL_ENV"))
PY

# сам запуск
exec python main.py --preview-method auto --listen 0.0.0.0 --port "${PORT:-8188}"
