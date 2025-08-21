# Базовый образ ComfyUI
FROM nextdiffusionai/comfyui:latest

# Установка рабочей директории
WORKDIR /workspace

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

# Копирование handler скрипта
COPY handler.py /workspace/

# Копирование скриптов инициализации
COPY init_audio.sh /workspace/
COPY run_gpu.sh /workspace/

# Делаем скрипты исполняемыми
RUN chmod +x /workspace/init_audio.sh
RUN chmod +x /workspace/run_gpu.sh

# Создание директорий для временных файлов и вывода
RUN mkdir -p /workspace/temp /workspace/output

# Настройка переменных окружения
ENV PYTHONPATH="/workspace:${PYTHONPATH}"
ENV COMFYUI_PATH="/workspace/ComfyUI"

# Запуск init_audio.sh при старте контейнера (если нужно)
RUN /workspace/init_audio.sh
RUN /workspace/run_gpu.sh

# Для RunPod Services нужно открыть порт
EXPOSE 8000

# Команда запуска handler'а
CMD ["python", "-u", "handler.py"]