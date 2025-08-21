# Базовый образ ComfyUI
FROM nextdiffusionai/comfyui:latest

# Установка рабочей директории
WORKDIR /workspace

# Диагностика базового образа
RUN echo "=== Диагностика базового образа ===" && \
    pwd && \
    ls -la /workspace && \
    find /workspace -name "main.py" 2>/dev/null || echo "main.py не найден в /workspace" && \
    find / -name "main.py" -path "*/ComfyUI/*" 2>/dev/null | head -5 || echo "ComfyUI не найден"

# Установка системных зависимостей для аудио обработки
RUN apt-get update && apt-get install -y \
    ffmpeg \
    sox \
    libsox-fmt-all \
    portaudio19-dev \
    build-essential \
    python3-dev \
    libportaudio2 \
    libportaudiocpp0 \
    libsndfile1 \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей (убрали base64, io, json - они встроенные)
RUN pip install --no-cache-dir \
    runpod \
    requests \
    websocket-client \
    pillow \
    numpy \
    soundfile \
    librosa \
    scipy \
    python-dotenv

# Копирование файлов
COPY handler.py /workspace/
# Замена стандартных скриптов на улучшенные версии
COPY init_audio.sh /workspace/init_audio.sh
COPY run_gpu.sh /workspace/run_gpu.sh
COPY workflow.json /workspace/

# Делаем скрипты исполняемыми
RUN chmod +x /workspace/init_audio.sh
RUN chmod +x /workspace/run_gpu.sh

# Создание директорий для временных файлов и вывода
RUN mkdir -p /workspace/temp /workspace/output

# Настройка переменных окружения
ENV PYTHONPATH="/workspace:${PYTHONPATH}"
ENV COMFYUI_PATH="/workspace/ComfyUI"

# Запуск init_audio.sh при старте контейнера (если нужно)
# RUN /workspace/init_audio.sh

# Для RunPod Services нужно открыть порт
EXPOSE 8000

# Команда запуска handler'а
CMD ["python", "-u", "handler.py"]