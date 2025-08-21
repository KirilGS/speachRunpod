import runpod
import json
import os
import time
import uuid
import base64
import subprocess
import requests
import websocket
import threading
from pathlib import Path

# Конфигурация путей
COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_PATH = "/workspace/ComfyUI"
WORKFLOW_PATH = "/workspace/ComfyUI/user/default/workflows/xttsSpeach.json"
INPUT_DIR = "/workspace/ComfyUI/input"

# Глобальные переменные
comfyui_process = None
comfyui_ready = False

class ComfyUIClient:
    def __init__(self):
        self.client_id = str(uuid.uuid4())
    
    def queue_prompt(self, prompt):
        """Отправляет workflow в очередь ComfyUI"""
        payload = {"prompt": prompt, "client_id": self.client_id}
        
        try:
            response = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка отправки prompt: {e}")
            return None
    
    def get_audio(self, filename, subfolder="", folder_type="output"):
        """Получает аудио файл из ComfyUI"""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        
        try:
            response = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=60)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"Ошибка получения аудио: {e}")
            return None
    
    def get_history(self, prompt_id):
        """Получает историю выполнения"""
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка получения истории: {e}")
            return None
    
    def wait_for_completion(self, prompt_response, timeout=300):
        """Ждет завершения выполнения через WebSocket"""
        prompt_id = prompt_response['prompt_id']
        
        try:
            ws = websocket.WebSocket()
            ws.connect(f"ws://127.0.0.1:8188/ws?clientId={self.client_id}")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    message = ws.recv()
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data['type'] == 'executing':
                            exec_data = data['data']
                            if exec_data['prompt_id'] == prompt_id and exec_data['node'] is None:
                                # Выполнение завершено
                                break
                except:
                    time.sleep(1)
            
            ws.close()
            
            # Получаем результаты
            history_response = self.get_history(prompt_id)
            if history_response and prompt_id in history_response:
                return history_response[prompt_id]
            return None
            
        except Exception as e:
            print(f"Ошибка ожидания завершения: {e}")
            return None

def start_comfyui():
    """Запускает ComfyUI сервер"""
    global comfyui_process, comfyui_ready
    
    print("🚀 Запуск ComfyUI...")
    
    # Проверяем, не запущен ли уже
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if response.status_code == 200:
            print("✅ ComfyUI уже запущен")
            comfyui_ready = True
            return True
    except:
        pass
    
    # Проверяем наличие ComfyUI
    main_py_path = os.path.join(COMFYUI_PATH, "main.py")
    if not os.path.exists(main_py_path):
        print(f"❌ ComfyUI main.py не найден: {main_py_path}")
        return False
    
    print(f"📁 Найден ComfyUI: {COMFYUI_PATH}")
    
    def run_comfyui():
        global comfyui_process, comfyui_ready
        
        try:
            # Запускаем ComfyUI
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            comfyui_process = subprocess.Popen([
                "python", "main.py",
                "--listen", "0.0.0.0",
                "--port", "8188"
            ], cwd=COMFYUI_PATH, env=env)
            
            # Ждем готовности
            for i in range(60):  # 5 минут максимум
                try:
                    response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=2)
                    if response.status_code == 200:
                        print("✅ ComfyUI готов")
                        comfyui_ready = True
                        return
                except:
                    pass
                time.sleep(5)
            
            print("❌ ComfyUI не запустился вовремя")
            
        except Exception as e:
            print(f"❌ Ошибка запуска ComfyUI: {e}")
    
    # Запускаем в фоновом потоке
    thread = threading.Thread(target=run_comfyui, daemon=True)
    thread.start()
    
    return True

def load_workflow():
    """Загружает workflow из volume"""
    try:
        if os.path.exists(WORKFLOW_PATH):
            with open(WORKFLOW_PATH, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            print(f"✅ Workflow загружен: {WORKFLOW_PATH}")
            return workflow
        else:
            print(f"❌ Workflow не найден: {WORKFLOW_PATH}")
            return None
    except Exception as e:
        print(f"❌ Ошибка загрузки workflow: {e}")
        return None

def save_sample_audio(audio_base64, filename):
    """Сохраняет образец аудио в input директорию"""
    try:
        audio_data = base64.b64decode(audio_base64)
        os.makedirs(INPUT_DIR, exist_ok=True)
        
        filepath = os.path.join(INPUT_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        print(f"💾 Сохранен sample audio: {filename}")
        return filename
    except Exception as e:
        print(f"❌ Ошибка сохранения audio: {e}")
        return None

def modify_workflow(workflow, job_input):
    """Модифицирует workflow с параметрами"""
    try:
        modified = workflow.copy()
        
        # Обновляем текст для синтеза (node 17 - RUAccentize)
        if 'text' in job_input and '17' in modified:
            modified['17']['inputs']['text'] = job_input['text']
        
        # Обновляем sample text (node 25)
        if 'sample_text' in job_input and '25' in modified:
            modified['25']['inputs']['value'] = job_input['sample_text']
        
        # Обновляем параметры F5TTS (node 14)
        if '14' in modified:
            if 'seed' in job_input:
                modified['14']['inputs']['seed'] = job_input['seed']
            if 'speed' in job_input:
                modified['14']['inputs']['speed'] = job_input['speed']
        
        # Если есть sample audio
        if 'sample_audio' in job_input and job_input['sample_audio'] and '8' in modified:
            audio_filename = f"sample_{uuid.uuid4().hex[:8]}.wav"
            saved_filename = save_sample_audio(job_input['sample_audio'], audio_filename)
            if saved_filename:
                modified['8']['inputs']['audio'] = saved_filename
        
        return modified
        
    except Exception as e:
        print(f"❌ Ошибка модификации workflow: {e}")
        return workflow

def process_tts_generation(job_input):
    """Основная функция генерации TTS"""
    if not comfyui_ready:
        return {"error": "ComfyUI не готов"}
    
    try:
        # Загружаем workflow
        workflow = load_workflow()
        if not workflow:
            return {"error": "Не удалось загрузить workflow"}
        
        # Модифицируем workflow
        modified_workflow = modify_workflow(workflow, job_input)
        
        # Создаем клиент и отправляем задачу
        client = ComfyUIClient()
        prompt_response = client.queue_prompt(modified_workflow)
        
        if not prompt_response:
            return {"error": "Не удалось отправить задачу"}
        
        prompt_id = prompt_response['prompt_id']
        print(f"🎯 Задача {prompt_id} отправлена")
        
        # Ждем завершения
        history = client.wait_for_completion(prompt_response)
        if not history:
            return {"error": "Таймаут выполнения"}
        
        # Собираем аудио файлы
        audio_files = []
        
        if 'outputs' in history:
            for node_id, output in history['outputs'].items():
                if 'audio' in output:
                    for audio_info in output['audio']:
                        filename = audio_info['filename']
                        subfolder = audio_info.get('subfolder', '')
                        
                        # Получаем аудио
                        audio_data = client.get_audio(filename, subfolder)
                        if audio_data:
                            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                            audio_files.append({
                                'filename': filename,
                                'audio_base64': audio_base64,
                                'size_bytes': len(audio_data)
                            })
                            print(f"🎵 Получен аудио: {filename}")
        
        if not audio_files:
            return {"error": "Аудио файлы не найдены"}
        
        return {
            "success": True,
            "audio_files": audio_files,
            "prompt_id": prompt_id
        }
        
    except Exception as e:
        print(f"❌ Ошибка генерации: {e}")
        return {"error": str(e)}

def handler(job):
    """RunPod Serverless handler"""
    try:
        print(f"🎤 Новая задача: {job.get('id', 'unknown')}")
        
        job_input = job.get("input", {})
        
        # Валидация
        if not job_input.get("text"):
            return {"error": "Требуется параметр 'text'"}
        
        print(f"📝 Текст: {job_input['text'][:50]}...")
        
        # Обрабатываем задачу
        result = process_tts_generation(job_input)
        
        if result.get("success"):
            print(f"✅ Задача выполнена: {len(result['audio_files'])} файлов")
        else:
            print(f"❌ Ошибка: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return {"error": f"Критическая ошибка: {str(e)}"}

def initialize():
    """Инициализация при запуске контейнера"""
    print("🚀 Инициализация F5-TTS Serverless...")
    
    # Проверяем volume
    if os.path.exists(COMFYUI_PATH):
        print(f"✅ ComfyUI найден: {COMFYUI_PATH}")
    else:
        print(f"❌ ComfyUI не найден: {COMFYUI_PATH}")
        return False
    
    if os.path.exists(WORKFLOW_PATH):
        print(f"✅ Workflow найден: {WORKFLOW_PATH}")
    else:
        print(f"❌ Workflow не найден: {WORKFLOW_PATH}")
        return False
    
    # Запускаем ComfyUI
    if not start_comfyui():
        print("❌ Не удалось запустить ComfyUI")
        return False
    
    print("✅ Инициализация завершена")
    return True

if __name__ == '__main__':
    if initialize():
        print("🔄 Запуск RunPod Serverless Worker...")
        runpod.serverless.start({"handler": handler})
    else:
        print("❌ Ошибка инициализации")
        exit(1)