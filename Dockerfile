# Базовый образ ComfyUI
FROM nextdiffusionai/comfyui:latest

# Рабочая директория
WORKDIR /workspace

# Установка дополнительных аудио зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    sox \
    libsox-fmt-all \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей для serverless
RUN pip install --no-cache-dir \
    runpod \
    requests \
    websocket-client

# Копирование handler файла
COPY handler.py /workspace/

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV COMFYUI_PATH="/workspace/ComfyUI"

# Команда запуска serverless handler
CMD ["python", "-u", "handler.py"]