#!/usr/bin/env bash
set -euo pipefail

# Поиск ComfyUI в возможных местах
POSSIBLE_DIRS=(
    "/workspace/ComfyUI"
    "/comfyui" 
    "/app/ComfyUI"
    "/workspace"
)

COMFY_DIR=""
for dir in "${POSSIBLE_DIRS[@]}"; do
    if [ -f "$dir/main.py" ]; then
        COMFY_DIR="$dir"
        echo "Найден ComfyUI в: $COMFY_DIR"
        break
    fi
done

if [ -z "$COMFY_DIR" ]; then
    echo "Ошибка: Не найден main.py ComfyUI в стандартных местах"
    echo "Проверяемые директории: ${POSSIBLE_DIRS[*]}"
    exit 1
fi

cd "$COMFY_DIR"

# Поиск Python интерпретера
POSSIBLE_PYTHONS=(
    "$COMFY_DIR/venv/bin/python"
    "$COMFY_DIR/.venv/bin/python"
    "/opt/conda/bin/python"
    "python3"
    "python"
)

PYTHON_CMD=""
for python in "${POSSIBLE_PYTHONS[@]}"; do
    if command -v "$python" >/dev/null 2>&1; then
        PYTHON_CMD="$python"
        echo "Используем Python: $PYTHON_CMD"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "Ошибка: Не найден Python интерпретер"
    exit 1
fi

# Активируем виртуальное окружение если есть
VENV_DIR="$COMFY_DIR/venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "Активируем виртуальное окружение: $VENV_DIR"
    source "$VENV_DIR/bin/activate"
fi

# Устанавливаем переменные окружения
export HF_HOME="/workspace/.cache/huggingface"
export PYTHONUNBUFFERED=1

# Создаем директории для кэша
mkdir -p "/workspace/.cache/huggingface"

# Диагностика
echo "=== Диагностика окружения ==="
echo "Рабочая директория: $(pwd)"
echo "Python: $PYTHON_CMD"
echo "Python версия: $($PYTHON_CMD --version 2>&1)"
echo "VIRTUAL_ENV: ${VIRTUAL_ENV:-не установлен}"
echo "HF_HOME: $HF_HOME"

# Проверяем наличие main.py
if [ ! -f "main.py" ]; then
    echo "Ошибка: main.py не найден в $(pwd)"
    ls -la
    exit 1
fi

echo "=== Запуск ComfyUI ==="

# Запуск ComfyUI
exec "$PYTHON_CMD" main.py \
    --preview-method auto \
    --listen 0.0.0.0 \
    --port "${PORT:-8188}"