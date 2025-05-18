from flask import Flask, jsonify
import os
import threading
import time
import asyncio
import logging
from main import init_db, get_db_connection
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, filters
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton

# Импортируем обработчики из main.py
from main import (
    start, help_command, cancel, handle_category_selection, handle_genre_selection,
    handle_movie_actions, handle_music_actions, handle_book_actions,
    show_history, movies_command, music_command, books_command,
    handle_fallback_callback, error_handler,
    START_ROUTES, GENRE_SELECTION, MOVIE_ACTIONS, MUSIC_ACTIONS, BOOK_ACTIONS
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Глобальная переменная для отслеживания статуса бота
bot_status = {
    "running": False,
    "start_time": None,
    "last_check": None,
    "error": None
}

@app.route('/')
def home():
    return jsonify({
        "status": "Movie Recommendation Bot is running",
        "bot_running": bot_status["running"],
        "uptime": time.time() - bot_status["start_time"] if bot_status["start_time"] else 0,
        "last_check": bot_status["last_check"],
        "error": bot_status["error"]
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
        "last_health_check": bot_status["last_check"],
        "error": bot_status["error"]
    })

@app.route('/restart')
def restart_bot():
    """Перезапуск бота"""
    bot_status["error"] = None
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()
    return jsonify({"message": "Bot restart initiated"})

async def run_telegram_bot():
    """Асинхронная функция запуска Telegram бота"""
    try:
        # Инициализация базы данных
        init_db()
        
        # Создание бота и получение токена из переменных среды
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("Не указан токен бота в переменной TELEGRAM_BOT_TOKEN")
        
        # Создание приложения
        application = Application.builder().token(token).build()
        
        # Определение конечного автомата для диалога
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                START_ROUTES: [
                    CallbackQueryHandler(handle_category_selection, pattern="^category_.*|^help$|^back_to_main$|^start_over$")
                ],
                GENRE_SELECTION: [
                    CallbackQueryHandler(handle_genre_selection, pattern="^(movie|music|book)_.*|^back_to_main$")
                ],
                MOVIE_ACTIONS: [
                    CallbackQueryHandler(handle_movie_actions, pattern="^rate_movie_.*|^movie_.*|^category_movies$|^back_to_main$")
                ],
                MUSIC_ACTIONS: [
                    CallbackQueryHandler(handle_music_actions, pattern="^rate_music_.*|^music_.*|^category_music$|^back_to_main$")
                ],
                BOOK_ACTIONS: [
                    CallbackQueryHandler(handle_book_actions, pattern="^rate_book_.*|^book_.*|^category_books$|^back_to_main$")
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            name="main_conversation",
            persistent=False,
            allow_reentry=True,
        )
        
        # Регистрация обработчиков
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("history", show_history))
        application.add_handler(CommandHandler("movies", movies_command))
        application.add_handler(CommandHandler("music", music_command))
        application.add_handler(CommandHandler("books", books_command))
        
        # Глобальный обработчик для всех callback-запросов
        application.add_handler(CallbackQueryHandler(handle_fallback_callback))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Обновляем статус
        bot_status["running"] = True
        bot_status["start_time"] = time.time()
        bot_status["error"] = None
        
        logger.info("Telegram бот успешно запущен")
        
        # Запуск бота
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        error_msg = f"Ошибка при запуске бота: {e}"
        logger.error(error_msg)
        bot_status["running"] = False
        bot_status["error"] = str(e)
        raise

def run_bot_in_thread():
    """Запуск бота в отдельном потоке с правильной обработкой asyncio"""
    try:
        # Создаем новый event loop для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Запускаем асинхронную функцию бота
        loop.run_until_complete(run_telegram_bot())
        
    except Exception as e:
        logger.error(f"Критическая ошибка в потоке бота: {e}")
        bot_status["running"] = False
        bot_status["error"] = str(e)
    finally:
        bot_status["running"] = False

if __name__ == '__main__':
    # Запуск бота в отдельном потоке
    logger.info("Запуск Telegram бота в отдельном потоке...")
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()
    
    # Получение порта из переменной окружения или использование 5000 по умолчанию
    port = int(os.environ.get('PORT', 5000))
    
    # Запуск Flask-приложения
    logger.info(f"Запуск Flask сервера на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
