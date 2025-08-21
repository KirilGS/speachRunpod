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
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

# Глобальные переменные
COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_PATH = "/workspace/workflow.json"  # Путь к нашему workflow файлу
OUTPUT_DIR = "/workspace/output"
TEMP_DIR = "/workspace/temp"
SERVICE_PORT = int(os.environ.get('RUNPOD_TCP_PORT_8000', 8000))

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
    
    # Сначала проверим возможные пути к ComfyUI
    possible_paths = [
        "/workspace/ComfyUI",
        "/comfyui",
        "/app/ComfyUI",
        "/workspace"
    ]
    
    comfyui_path = None
    for path in possible_paths:
        if os.path.exists(os.path.join(path, "main.py")):
            comfyui_path = path
            print(f"Найден ComfyUI в: {path}")
            break
    
    if not comfyui_path:
        print("Не найден main.py ComfyUI")
        return False
    
    # Запускаем сервер
    def run_server():
        try:
            # Пробуем запустить напрямую
            os.chdir(comfyui_path)
            print(f"Запуск ComfyUI из директории: {os.getcwd()}")
            
            # Проверяем наличие виртуального окружения
            venv_paths = [
                os.path.join(comfyui_path, "venv", "bin", "python"),
                os.path.join(comfyui_path, ".venv", "bin", "python"),
                "/opt/conda/bin/python",
                "python3",
                "python"
            ]
            
            python_cmd = "python"
            for venv_path in venv_paths:
                if os.path.exists(venv_path):
                    python_cmd = venv_path
                    print(f"Используем Python: {python_cmd}")
                    break
            
            # Устанавливаем переменные окружения
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["HF_HOME"] = "/workspace/.cache/huggingface"
            
            # Запускаем ComfyUI
            subprocess.run([
                python_cmd, "main.py", 
                "--preview-method", "auto",
                "--listen", "0.0.0.0", 
                "--port", "8188"
            ], cwd=comfyui_path, env=env)
            
        except Exception as e:
            print(f"Ошибка при запуске ComfyUI: {e}")
            # Fallback - пробуем через наш скрипт
            try:
                subprocess.run(["/workspace/run_gpu.sh"], cwd="/workspace")
            except Exception as e2:
                print(f"Ошибка при запуске через скрипт: {e2}")
    
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
        print(f"Попытка {i+1}/{max_retries} - ждем запуска ComfyUI...")
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
        if 'outputs' in history:
            for node_id, output in history['outputs'].items():
                print(f"Проверяем выход ноды {node_id}: {output.keys()}")
                
                # Ищем аудио файлы в любых нодах
                if 'audio' in output:
                    for audio_info in output['audio']:
                        filename = audio_info['filename']
                        subfolder = audio_info.get('subfolder', '')
                        
                        print(f"Найден аудио файл: {filename} в папке: {subfolder}")
                        
                        # Получаем аудио файл
                        audio_data = client.get_audio(filename, subfolder, 'output')
                        if audio_data:
                            # Конвертируем в base64 для возврата
                            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                            output_files.append({
                                'filename': filename,
                                'audio_base64': audio_base64,
                                'source_node': node_id
                            })
                            
                            print(f"Аудио файл обработан: {filename}")
        
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

class ServiceHandler(BaseHTTPRequestHandler):
    """HTTP Handler для обработки запросов к сервису"""
    
    def do_GET(self):
        """Обработка GET запросов"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Обработка POST запросов"""
        try:
            if self.path == '/generate':
                # Читаем данные запроса
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                
                # Парсим JSON
                try:
                    job_input = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    self.send_error_response(400, f"Неверный JSON: {str(e)}")
                    return
                
                # Валидация входных данных
                if not job_input.get("text"):
                    self.send_error_response(400, "Параметр 'text' обязателен")
                    return
                
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
                
                # Отправляем ответ
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
                print(f"Результат генерации: {result}")
                
            else:
                self.send_response(404)
                self.end_headers()
                
        except Exception as e:
            print(f"Ошибка в POST обработчике: {e}")
            self.send_error_response(500, f"Внутренняя ошибка сервера: {str(e)}")
    
    def send_error_response(self, code, message):
        """Отправляет ошибку в JSON формате"""
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        error_response = {"error": message}
        self.wfile.write(json.dumps(error_response).encode())

def init_handler():
    """Инициализация при запуске"""
    print("Инициализация F5-TTS Audio Generation Service...")
    
    # Создаем необходимые директории
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Запускаем ComfyUI сервер
    if not start_comfyui():
        print("КРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить ComfyUI")
        return False
    
    print("Service успешно инициализирован")
    return True

def run_service():
    """Запуск HTTP сервиса"""
    try:
        server = HTTPServer(('0.0.0.0', SERVICE_PORT), ServiceHandler)
        print(f"F5-TTS Service запущен на порту {SERVICE_PORT}")
        print("Доступные endpoints:")
        print(f"  GET  /health - проверка состояния")
        print(f"  POST /generate - генерация аудио")
        server.serve_forever()
    except Exception as e:
        print(f"Ошибка при запуске сервиса: {e}")

# Serverless handler для совместимости
def handler(job):
    """Handler для Runpod Serverless (если используется)"""
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

if __name__ == '__main__':
    # Инициализация
    if init_handler():
        # Определяем режим работы
        mode = os.environ.get('RUNPOD_MODE', 'service')
        
        if mode == 'serverless':
            print("Запуск в режиме Runpod Serverless...")
            runpod.serverless.start({"handler": handler})
        else:
            print("Запуск в режиме Runpod Service...")
            run_service()
    else:
        print("Ошибка инициализации")
        exit(1)