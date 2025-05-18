from flask import Flask, jsonify
import os
import threading
import time
from main import main as run_bot

app = Flask(__name__)

# Глобальная переменная для отслеживания статуса бота
bot_status = {
    "running": False,
    "start_time": None,
    "last_check": None
}

@app.route('/')
def home():
    return jsonify({
        "status": "Movie Recommendation Bot is running",
        "bot_running": bot_status["running"],
        "uptime": time.time() - bot_status["start_time"] if bot_status["start_time"] else 0,
        "last_check": bot_status["last_check"]
    })

@app.route('/health')
def health_check():
    """Проверка здоровья приложения для Render"""
    bot_status["last_check"] = time.time()
    return jsonify({
        "status": "healthy",
        "bot_status": "running" if bot_status["running"] else "stopped",
        "timestamp": bot_status["last_check"]
    }), 200

@app.route('/status')
def status():
    """Подробный статус бота"""
    return jsonify({
        "bot_running": bot_status["running"],
        "start_time": bot_status["start_time"],
        "uptime_seconds": time.time() - bot_status["start_time"] if bot_status["start_time"] else 0,
        "last_health_check": bot_status["last_check"]
    })

def run_bot_in_thread():
    """Запуск бота в отдельном потоке"""
    try:
        bot_status["running"] = True
        bot_status["start_time"] = time.time()
        print("Запуск Telegram бота...")
        run_bot()
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")
        bot_status["running"] = False
    finally:
        bot_status["running"] = False

if __name__ == '__main__':
    # Запуск бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()
    
    # Получение порта из переменной окружения или использование 5000 по умолчанию
    port = int(os.environ.get('PORT', 5000))
    
    # Запуск Flask-приложения
    print(f"Запуск Flask сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
