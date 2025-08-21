import runpod
import json
import os
import time
import uuid
import base64
import io
import subprocess
import requests
import websocket
import threading
from urllib.parse import urljoin, urlparse
from pathlib import Path

# Глобальные переменные
COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = "/workspace/user/default/workflows/xttsSpeach.json"  # Используем ваш существующий workflow
OUTPUT_DIR = "/workspace/output"
TEMP_DIR = "/workspace/temp"

class ComfyUIClient:
    def __init__(self, server_address):
        self.server_address = server_address
        self.client_id = str(uuid.uuid4())
        
    def queue_prompt(self, prompt):
        """Отправляет workflow в очередь ComfyUI"""
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode('utf-8')
        
        try:
            response = requests.post(f"{self.server_address}/prompt", data=data, headers={'Content-Type': 'application/json'})
            return response.json()
        except Exception as e:
            print(f"Ошибка при отправке prompt: {e}")
            return None

    def get_image(self, filename, subfolder, folder_type):
        """Получает изображение из ComfyUI"""
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = requests.compat.urlencode(data)
        try:
            response = requests.get(f"{self.server_address}/view?{url_values}")
            return response.content
        except Exception as e:
            print(f"Ошибка при получении изображения: {e}")
            return None

    def get_audio(self, filename, subfolder, folder_type):
        """Получает аудио файл из ComfyUI"""
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = requests.compat.urlencode(data)
        try:
            response = requests.get(f"{self.server_address}/view?{url_values}")
            return response.content
        except Exception as e:
            print(f"Ошибка при получении аудио: {e}")
            return None

    def get_history(self, prompt_id):
        """Получает историю выполнения workflow"""
        try:
            response = requests.get(f"{self.server_address}/history/{prompt_id}")
            return response.json()
        except Exception as e:
            print(f"Ошибка при получении истории: {e}")
            return None

    def get_images(self, ws, prompt):
        """Ждет завершения выполнения и получает результаты"""
        prompt_id = prompt['prompt_id']
        output_images = {}
        current_node = ""
        
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        if data['node'] is None:
                            break  # Execution is done
                        else:
                            current_node = data['node']
            else:
                continue

        history = self.get_history(prompt_id)[prompt_id]
        return history

def start_comfyui():
    """Запускает ComfyUI сервер"""
    print("Запуск ComfyUI сервера...")
    
    # Проверяем, запущен ли уже сервер
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if response.status_code == 200:
            print("ComfyUI сервер уже запущен")
            return True
    except:
        pass
    
    # Запускаем сервер
    def run_server():
        subprocess.run(["/workspace/run_gpu.sh"], cwd="/workspace")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Ждем, пока сервер запустится
    max_retries = 60
    for i in range(max_retries):
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
            if response.status_code == 200:
                print("ComfyUI сервер успешно запущен")
                return True
        except:
            pass
        time.sleep(5)
    
    print("Не удалось запустить ComfyUI сервер")
    return False

def load_workflow():
    """Загружает workflow JSON"""
    try:
        with open(WORKFLOW_PATH, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        return workflow
    except Exception as e:
        print(f"Ошибка при загрузке workflow: {e}")
        return None

def save_audio_file(audio_data, filename):
    """Сохраняет аудио файл и возвращает путь"""
    try:
        if isinstance(audio_data, str):
            # Если это base64
            audio_data = base64.b64decode(audio_data)
        
        filepath = os.path.join(TEMP_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        return filepath
    except Exception as e:
        print(f"Ошибка при сохранении аудио файла: {e}")
        return None

def modify_workflow(workflow, params):
    """Модифицирует workflow с входными параметрами"""
    try:
        # Обновляем текст для синтеза в RUAccentize (node 17)
        if 'text' in params and '17' in workflow:
            workflow['17']['inputs']['text'] = params['text']
        
        # Обновляем sample_text если предоставлен (node 25)
        if 'sample_text' in params and '25' in workflow:
            workflow['25']['inputs']['value'] = params['sample_text']
        
        # Обновляем seed если предоставлен (node 14 - F5TTSAudioInputs)
        if 'seed' in params and '14' in workflow:
            workflow['14']['inputs']['seed'] = params['seed']
        
        # Обновляем speed если предоставлен
        if 'speed' in params and '14' in workflow:
            workflow['14']['inputs']['speed'] = params['speed']
        
        # Если предоставлен sample_audio, сохраняем его
        if 'sample_audio' in params and '8' in workflow:
            audio_filename = f"sample_{uuid.uuid4().hex[:8]}.wav"
            audio_path = save_audio_file(params['sample_audio'], audio_filename)
            if audio_path:
                # Обновляем LoadAudio node (node 8)
                workflow['8']['inputs']['audio'] = audio_filename
        
        return workflow
        
    except Exception as e:
        print(f"Ошибка при модификации workflow: {e}")
        return None

def process_audio_generation(params):
    """Основная функция обработки генерации аудио"""
    try:
        # Загружаем workflow
        workflow = load_workflow()
        if not workflow:
            return {"error": "Не удалось загрузить workflow"}
        
        # Модифицируем workflow
        modified_workflow = modify_workflow(workflow, params)
        if not modified_workflow:
            return {"error": "Не удалось модифицировать workflow"}
        
        # Создаем клиент ComfyUI
        client = ComfyUIClient(COMFYUI_URL)
        
        # Создаем WebSocket соединение
        ws = websocket.WebSocket()
        ws.connect(f"ws://127.0.0.1:8188/ws?clientId={client.client_id}")
        
        # Отправляем workflow
        prompt_response = client.queue_prompt(modified_workflow)
        if not prompt_response:
            return {"error": "Не удалось отправить workflow в очередь"}
        
        prompt_id = prompt_response['prompt_id']
        print(f"Workflow отправлен с ID: {prompt_id}")
        
        # Ждем результаты
        history = client.get_images(ws, prompt_response)
        ws.close()
        
        # Обрабатываем результаты
        output_files = []
        
        # Ищем выходные аудио файлы в истории выполнения
        # Node 9 - PreviewAudio является выходной нодой
        if 'outputs' in history:
            for node_id, output in history['outputs'].items():
                print(f"Проверяем выход ноды {node_id}: {output.keys()}")
                
                # Ищем аудио файлы в любых нодах (PreviewAudio, AudioQualityEnhancer и т.д.)
                if 'audio' in output:
                    for audio_info in output['audio']:
                        filename = audio_info['filename']
                        subfolder = audio_info.get('subfolder', '')
                        
                        print(f"Найден аудио файл: {filename} в папке: {subfolder}")
                        
                        # Получаем аудио файл
                        audio_data = client.get_audio(filename, subfolder, 'output')
                        if audio_data:
                            # Сохраняем в выходную директорию
                            output_filename = f"generated_{uuid.uuid4().hex[:8]}.wav"
                            output_path = os.path.join(OUTPUT_DIR, output_filename)
                            
                            with open(output_path, 'wb') as f:
                                f.write(audio_data)
                            
                            # Конвертируем в base64 для возврата
                            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                            output_files.append({
                                'filename': output_filename,
                                'audio_base64': audio_base64,
                                'path': output_path,
                                'source_node': node_id
                            })
                            
                            print(f"Аудио файл обработан: {output_filename}")
        
        if not output_files:
            print("Детали истории выполнения:")
            print(json.dumps(history, indent=2))
            return {"error": "Не найдены выходные аудио файлы"}
        
        return {
            "success": True,
            "prompt_id": prompt_id,
            "audio_files": output_files,
            "message": f"Сгенерировано {len(output_files)} аудио файл(ов)"
        }
        
    except Exception as e:
        print(f"Ошибка при обработке генерации аудио: {e}")
        return {"error": f"Внутренняя ошибка: {str(e)}"}

def handler(job):
    """Main handler function для Runpod"""
    try:
        print(f"F5-TTS Audio Generation | Starting job {job['id']}")
        
        # Получаем входные данные
        job_input = job.get("input", {})
        
        # Валидация входных данных
        if not job_input.get("text"):
            return {"error": "Параметр 'text' обязателен"}
        
        # Параметры по умолчанию
        params = {
            "text": job_input.get("text"),
            "sample_text": job_input.get("sample_text", ""),
            "seed": job_input.get("seed", 400),
            "speed": job_input.get("speed", 1.0)
        }
        
        # Добавляем sample_audio если предоставлен
        if job_input.get("sample_audio"):
            params["sample_audio"] = job_input["sample_audio"]
        
        print(f"Параметры генерации: {params}")
        
        # Обрабатываем генерацию
        result = process_audio_generation(params)
        
        print(f"Результат генерации: {result}")
        return result
        
    except Exception as e:
        print(f"Ошибка в handler: {e}")
        return {"error": f"Ошибка обработки: {str(e)}"}

def init_handler():
    """Инициализация при запуске"""
    print("Инициализация F5-TTS Audio Generation Handler...")
    
    # Создаем необходимые директории
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Запускаем ComfyUI сервер
    if not start_comfyui():
        print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить ComfyUI")
        return False
    
    print("Handler успешно инициализирован")
    return True

if __name__ == '__main__':
    # Инициализация
    if init_handler():
        print("Запуск Runpod serverless worker...")
        runpod.serverless.start({"handler": handler})
    else:
        print("Ошибка инициализации")
        exit(1)