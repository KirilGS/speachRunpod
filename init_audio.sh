#!/bin/bash
set -e

echo "Установка аудио зависимостей..."

# Обновляем список пакетов
apt-get update

# Устанавливаем аудио зависимости
apt-get install -y \
    ffmpeg \
    sox \
    libsox-fmt-all \
    portaudio19-dev \
    build-essential \
    python3-dev \
    libportaudio2 \
    libportaudiocpp0 \
    libsndfile1 \
    alsa-utils \
    pulseaudio-utils

# Очищаем кэш apt для уменьшения размера образа
rm -rf /var/lib/apt/lists/*

echo "Аудио зависимости установлены успешно"