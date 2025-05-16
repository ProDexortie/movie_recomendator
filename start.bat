@echo off
:: Устанавливаем кодировку консоли на UTF-8
chcp 65001 > nul

echo ===============================================
echo Запуск бота-рекомендателя фильмов, музыки и книг
echo ===============================================
echo.

:: Проверяем наличие Python в системе
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Python не найден в системе. Пожалуйста, установите Python 3.8 или выше.
    echo Загрузить Python можно с сайта: https://www.python.org/downloads/
    goto end
)

:: Проверяем наличие виртуального окружения
if not exist venv\ (
    echo Виртуальное окружение не найдено. Создаем...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение.
        goto end
    )
)

:: Активируем виртуальное окружение и устанавливаем зависимости
echo Активация виртуального окружения...
call venv\Scripts\activate.bat

:: Проверяем наличие файла requirements.txt
if not exist requirements.txt (
    echo [ПРЕДУПРЕЖДЕНИЕ] Файл requirements.txt не найден. Создаем базовый файл...
    (
        echo python-telegram-bot==20.7
        echo requests==2.31.0
        echo python-dotenv==1.0.0
    ) > requirements.txt
)

:: Устанавливаем зависимости
echo Установка необходимых библиотек...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось установить зависимости.
    goto end
)

:: Проверяем наличие файла .env
if not exist .env (
    echo [ПРЕДУПРЕЖДЕНИЕ] Файл .env не найден. Создаем шаблон...
    (
        echo # Токен Telegram бота, полученный от BotFather
        echo TELEGRAM_BOT_TOKEN=your_telegram_bot_token
        echo.
        echo # API ключ для The Movie Database (TMDb)
        echo TMDB_API_KEY=your_tmdb_api_key
        echo.
        echo # Учетные данные Spotify API
        echo SPOTIFY_CLIENT_ID=your_spotify_client_id
        echo SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
        echo.
        echo # API ключ для Google Books (необязательно)
        echo GOOGLE_BOOKS_API_KEY=your_google_books_api_key
    ) > .env
    echo [ВАЖНО] Пожалуйста, отредактируйте файл .env и добавьте свои API ключи!
    echo Нажмите любую клавишу, когда будете готовы...
    pause > nul
)

:: Дополнительная настройка шрифта консоли для лучшей поддержки кириллицы
echo Настройка консоли для корректного отображения кириллицы...
:: Устанавливаем шрифт Consolas или Lucida Console, если доступен
reg add "HKCU\Console" /v FaceName /t REG_SZ /d "Consolas" /f > nul 2>&1

:: Запуск бота
echo.
echo ===============================================
echo Запуск бота...
echo Для остановки нажмите Ctrl+C
echo ===============================================
echo.
python main.py

:end
echo.
echo Нажмите любую клавишу для выхода...
pause > nul