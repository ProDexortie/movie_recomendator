# main.py
import os
import logging
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import requests
import json
import random
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Загрузка переменных среды из файла .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# API ключи
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")

# Состояния для ConversationHandler
START_ROUTES, GENRE_SELECTION, MOVIE_ACTIONS, MUSIC_ACTIONS, BOOK_ACTIONS = range(5)

# Мапинг жанров для Spotify API
SPOTIFY_GENRE_MAPPING = {
    "pop": "pop",
    "rock": "rock",
    "hip-hop": "hip hop",  # Убираем дефис, так как Spotify может не распознавать его
    "electronic": "electronic",
    "jazz": "jazz",
    "classical": "classical music"  # Добавляем "music" для лучшего поиска
}

# Обработчик ошибок для телеграм-бота
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки, возникающие в диспетчере обновлений."""
    logger.error("Произошла ошибка при обработке обновления %s", update, exc_info=context.error)
    
    # Извлекаем информацию об ошибке
    error_message = str(context.error)
    
    # Если у нас есть объект update и сообщение
    if update and isinstance(update, Update) and update.effective_message:
        # Отправляем пользователю сообщение об ошибке
        error_text = f"😔 Произошла ошибка при обработке вашего запроса.\n\nПопробуйте начать сначала с помощью команды /start"
        
        # Добавляем кнопку для возврата в главное меню
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
            [InlineKeyboardButton("🔄 Начать заново", callback_data="start_over")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await update.effective_message.reply_text(
                error_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

# Подключение к БД
def get_db_connection():
    conn = sqlite3.connect('user_preferences.db')
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Создание таблицы пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        registration_date TEXT
    )
    ''')
    
    # Создание таблицы предпочтений пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        genre TEXT,
        item_id TEXT,
        rating INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Создание таблицы истории рекомендаций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recommendation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        item_id TEXT,
        recommendation_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Регистрация пользователя в базе данных
def register_user(user_id, username, first_name, last_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registration_date)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.commit()
    conn.close()

# Сохранение предпочтений пользователя
def save_preference(user_id, category, genre, item_id, rating):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO user_preferences (user_id, category, genre, item_id, rating)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, category, genre, item_id, rating))
    
    conn.commit()
    conn.close()

# Сохранение истории рекомендаций
def save_recommendation_history(user_id, category, item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO recommendation_history (user_id, category, item_id, recommendation_date)
    VALUES (?, ?, ?, ?)
    ''', (user_id, category, item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.commit()
    conn.close()

# Получение предпочтений пользователя
def get_user_preferences(user_id, category=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if category:
        cursor.execute('''
        SELECT * FROM user_preferences
        WHERE user_id = ? AND category = ?
        ''', (user_id, category))
    else:
        cursor.execute('''
        SELECT * FROM user_preferences
        WHERE user_id = ?
        ''', (user_id,))
    
    preferences = cursor.fetchall()
    conn.close()
    
    return preferences

# Функция для генерации случайного ID
def generate_random_id():
    return f"fallback_{random.randint(10000, 99999)}"

# Функции для получения рекомендаций от API

async def get_movie_recommendations(genre_id=None, user_id=None):
    # Используем популярные фильмы, если жанр не указан
    if genre_id:
        url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page=1"
    else:
        url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&page=1"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'results' in data and data['results']:
            # Исключаем фильмы, которые уже были рекомендованы пользователю
            if user_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                SELECT item_id FROM recommendation_history
                WHERE user_id = ? AND category = 'movie'
                ''', (user_id,))
                recommended_ids = [row['item_id'] for row in cursor.fetchall()]
                conn.close()
                
                filtered_results = [movie for movie in data['results'] if str(movie['id']) not in recommended_ids]
                if filtered_results:
                    movie = random.choice(filtered_results)
                else:
                    # Если все фильмы уже рекомендованы, берем любой
                    movie = random.choice(data['results'])
            else:
                movie = random.choice(data['results'])
            
            # Сохраняем рекомендацию в историю
            if user_id:
                save_recommendation_history(user_id, 'movie', str(movie['id']))
            
            # Получаем дополнительную информацию о фильме
            movie_url = f"https://api.themoviedb.org/3/movie/{movie['id']}?api_key={TMDB_API_KEY}&language=ru"
            movie_response = requests.get(movie_url, timeout=10)
            movie_response.raise_for_status()
            movie_data = movie_response.json()
            
            # Формируем информацию о фильме
            title = movie_data.get('title', 'Название неизвестно')
            original_title = movie_data.get('original_title', '')
            year = movie_data.get('release_date', '')[:4] if movie_data.get('release_date') else 'Год неизвестен'
            rating = movie_data.get('vote_average', 0)
            genres = ', '.join([genre['name'] for genre in movie_data.get('genres', [])])
            overview = movie_data.get('overview', 'Описание отсутствует')
            poster_path = movie_data.get('poster_path', None)
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            
            return {
                'id': movie['id'],
                'title': title,
                'original_title': original_title,
                'year': year,
                'rating': rating,
                'genres': genres,
                'overview': overview,
                'poster_url': poster_url
            }
        
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении рекомендаций фильмов: {e}")
        return None

async def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    auth = (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    data = {"grant_type": "client_credentials"}
    
    try:
        # Добавляем параметр verify=True и увеличиваем timeout
        response = requests.post(url, headers=headers, data=data, auth=auth, 
                               verify=True, timeout=30)
        
        # Проверяем статус ответа
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            logger.error(f"Ошибка получения токена Spotify: HTTP {response.status_code} - {response.text}")
            return None
    except requests.exceptions.SSLError as e:
        logger.error(f"SSL ошибка при получении токена Spotify: {e}")
        # Альтернативный вариант (использовать только в случае крайней необходимости)
        try:
            # Попытка с отключенной проверкой SSL сертификата (только для отладки)
            logger.warning("Пробуем получить токен с отключенной проверкой SSL (не рекомендуется для продакшена)")
            response = requests.post(url, headers=headers, data=data, auth=auth, 
                                   verify=False, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")
            else:
                logger.error(f"Ошибка получения токена Spotify: HTTP {response.status_code} - {response.text}")
                return None
        except Exception as alt_e:
            logger.error(f"Не удалось получить токен даже с отключенной проверкой SSL: {alt_e}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении токена Spotify: {e}")
        return None

async def get_music_recommendations(genre=None, user_id=None):
    token = await get_spotify_token()
    if not token:
        logger.warning("Не удалось получить токен Spotify, использую запасной вариант")
        return await get_music_recommendations_fallback(genre, user_id)
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        # Преобразуем жанр для лучшей совместимости с API
        search_genre = genre
        if genre and genre in SPOTIFY_GENRE_MAPPING:
            search_genre = SPOTIFY_GENRE_MAPPING[genre]
            logger.info(f"Преобразован жанр '{genre}' в '{search_genre}' для поиска в Spotify")
            
        # Если жанр указан, ищем плейлисты по жанру
        if search_genre:
            query = search_genre.replace(" ", "+")
            
            # Альтернативный подход - искать треки, а не плейлисты
            search_url = f"https://api.spotify.com/v1/search?q=genre:{query}&type=track&limit=50"
            logger.info(f"Поиск треков по URL: {search_url}")
            
            try:
                response = requests.get(search_url, headers=headers, timeout=10)
                response.raise_for_status()  # Проверяем статус ответа
                data = response.json()
                
                if 'tracks' in data and 'items' in data['tracks'] and data['tracks']['items']:
                    tracks = data['tracks']['items']
                    track = random.choice(tracks)
                    
                    # Убеждаемся, что трек существует и имеет ID
                    if track and 'id' in track:
                        logger.info(f"Найден трек по жанру: {track.get('name', 'unknown')}")
                    else:
                        logger.warning("Получен трек, но без ID, использую запасной вариант")
                        return await get_music_recommendations_fallback(genre, user_id)
                else:
                    logger.warning(f"Не найдены треки по жанру '{search_genre}', ищу плейлисты...")
                    
                    # Если треки не найдены, попробуем искать плейлисты
                    search_url = f"https://api.spotify.com/v1/search?q={query}&type=playlist&limit=10"
                    response = requests.get(search_url, headers=headers, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    
                    if 'playlists' in data and 'items' in data['playlists'] and data['playlists']['items']:
                        playlist = random.choice(data['playlists']['items'])
                        if not playlist or 'id' not in playlist:
                            logger.warning("Получен плейлист без ID, использую запасной вариант")
                            return await get_music_recommendations_fallback(genre, user_id)
                            
                        playlist_id = playlist['id']
                        
                        # Получаем треки из плейлиста
                        tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=20"
                        tracks_response = requests.get(tracks_url, headers=headers, timeout=10)
                        tracks_response.raise_for_status()
                        tracks_data = tracks_response.json()
                        
                        if 'items' in tracks_data and tracks_data['items']:
                            valid_tracks = [item for item in tracks_data['items'] 
                                          if item and 'track' in item and item['track'] and 'id' in item['track']]
                            
                            if valid_tracks:
                                track_item = random.choice(valid_tracks)
                                track = track_item['track']
                                logger.info(f"Найден трек через плейлист: {track.get('name', 'unknown')}")
                            else:
                                logger.warning("Не найдены валидные треки в плейлисте, использую запасной вариант")
                                return await get_music_recommendations_fallback(genre, user_id)
                        else:
                            logger.warning("Не найдены треки в плейлисте, использую запасной вариант")
                            return await get_music_recommendations_fallback(genre, user_id)
                    else:
                        logger.warning(f"Не найдены плейлисты по жанру '{search_genre}', использую запасной вариант")
                        return await get_music_recommendations_fallback(genre, user_id)
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка запроса к Spotify API: {e}")
                return await get_music_recommendations_fallback(genre, user_id)
        else:
            # Если жанр не указан, используем новые релизы
            try:
                tracks_url = "https://api.spotify.com/v1/browse/new-releases?limit=20"
                tracks_response = requests.get(tracks_url, headers=headers, timeout=10)
                tracks_response.raise_for_status()
                tracks_data = tracks_response.json()
                
                if 'albums' in tracks_data and 'items' in tracks_data['albums'] and tracks_data['albums']['items']:
                    albums = [album for album in tracks_data['albums']['items'] if album and 'id' in album]
                    
                    if not albums:
                        logger.warning("Не найдены валидные альбомы, использую запасной вариант")
                        return await get_music_recommendations_fallback(genre, user_id)
                        
                    album = random.choice(albums)
                    album_id = album['id']
                    
                    # Получаем треки из альбома
                    album_tracks_url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=10"
                    album_tracks_response = requests.get(album_tracks_url, headers=headers, timeout=10)
                    album_tracks_response.raise_for_status()
                    album_tracks_data = album_tracks_response.json()
                    
                    if 'items' in album_tracks_data and album_tracks_data['items']:
                        valid_tracks = [t for t in album_tracks_data['items'] if t and 'id' in t]
                        
                        if valid_tracks:
                            track = random.choice(valid_tracks)
                            logger.info(f"Найден трек из новых релизов: {track.get('name', 'unknown')}")
                        else:
                            logger.warning("Не найдены валидные треки в альбоме, использую запасной вариант")
                            return await get_music_recommendations_fallback(genre, user_id)
                    else:
                        logger.warning("Не найдены треки в альбоме, использую запасной вариант")
                        return await get_music_recommendations_fallback(genre, user_id)
                else:
                    logger.warning("Не найдены новые релизы, использую запасной вариант")
                    return await get_music_recommendations_fallback(genre, user_id)
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка запроса к Spotify API для новых релизов: {e}")
                return await get_music_recommendations_fallback(genre, user_id)
        
        # Проверка наличия track_id
        if 'id' not in track:
            logger.warning("Отсутствует ID трека, использую запасной вариант")
            return await get_music_recommendations_fallback(genre, user_id)
        
        # Сохраняем рекомендацию в историю
        track_id = track['id']
        if user_id:
            try:
                save_recommendation_history(user_id, 'music', track_id)
            except Exception as e:
                logger.error(f"Ошибка при сохранении истории рекомендаций: {e}")
        
        # Получаем дополнительную информацию о треке
        try:
            track_url = f"https://api.spotify.com/v1/tracks/{track_id}"
            track_response = requests.get(track_url, headers=headers, timeout=10)
            track_response.raise_for_status()
            track_data = track_response.json()
            
            # Проверяем наличие всех необходимых полей
            if not track_data:
                logger.warning("Получены пустые данные о треке, использую запасной вариант")
                return await get_music_recommendations_fallback(genre, user_id)
                
            # Формируем информацию о треке с проверкой наличия полей
            track_name = track_data.get('name', 'Название неизвестно')
            artists = ', '.join([artist.get('name', 'Неизвестный артист') for artist in track_data.get('artists', [])])
            
            album = track_data.get('album', {})
            album_name = album.get('name', 'Альбом неизвестен')
            
            preview_url = track_data.get('preview_url')
            
            album_images = album.get('images', [])
            album_image = album_images[0].get('url') if album_images and len(album_images) > 0 else None
            
            spotify_url = track_data.get('external_urls', {}).get('spotify')
            
            # Создаем результат с проверкой на None для каждого поля
            result = {
                'id': track_data.get('id', generate_random_id()),
                'track_name': track_name,
                'artists': artists,
                'album_name': album_name,
                'preview_url': preview_url,
                'album_image': album_image,
                'spotify_url': spotify_url
            }
            
            logger.info(f"Успешно сформированы данные о треке: {track_name} - {artists}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о треке: {e}")
            return await get_music_recommendations_fallback(genre, user_id)
            
    except Exception as e:
        logger.error(f"Общая ошибка при получении рекомендаций музыки: {e}")
        return await get_music_recommendations_fallback(genre, user_id)

# Запасной вариант рекомендаций
async def get_music_recommendations_fallback(genre=None, user_id=None):
    """
    Запасной вариант, когда API Spotify недоступен.
    Возвращает фиктивные данные для демонстрации работы бота.
    """
    # Генерируем случайный ID
    random_id = generate_random_id()
    
    # Выбираем фиктивную рекомендацию на основе жанра
    fallback_recommendations = {
        "pop": {
            "id": random_id,
            "track_name": "Популярный хит",
            "artists": "Известный исполнитель",
            "album_name": "Хитовый альбом 2025",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com"
        },
        "rock": {
            "id": random_id,
            "track_name": "Рок-классика",
            "artists": "Рок-группа",
            "album_name": "Великие хиты рока",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com" 
        },
        "hip-hop": {
            "id": random_id,
            "track_name": "Хип-хоп трек",
            "artists": "MC Артист",
            "album_name": "Городские ритмы",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com"
        },
        "electronic": {
            "id": random_id,
            "track_name": "Электронный бит",
            "artists": "DJ Продюсер",
            "album_name": "Электронные вибрации",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com"
        },
        "jazz": {
            "id": random_id,
            "track_name": "Джазовая импровизация",
            "artists": "Джаз квартет",
            "album_name": "Вечера джаза",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com"
        },
        "classical": {
            "id": random_id,
            "track_name": "Классическая симфония",
            "artists": "Выдающийся композитор",
            "album_name": "Классические произведения",
            "preview_url": None,
            "album_image": "https://via.placeholder.com/300",
            "spotify_url": "https://open.spotify.com"
        }
    }
    
    # Сохраняем рекомендацию в историю
    if user_id:
        save_recommendation_history(user_id, 'music', random_id)
    
    # Если жанр указан и он есть в нашем списке, возвращаем соответствующую рекомендацию
    if genre and genre in fallback_recommendations:
        return fallback_recommendations[genre]
    else:
        # Иначе возвращаем случайную рекомендацию
        random_genre = random.choice(list(fallback_recommendations.keys()))
        return fallback_recommendations[random_genre]

# Словарь соответствия жанров на русском языке
BOOK_GENRE_RUSSIAN = {
    "fiction": "художественная литература",
    "fantasy": "фэнтези",
    "science": "наука",
    "history": "история",
    "biography": "биография",
    "poetry": "поэзия"
}

async def get_book_recommendations_fallback(genre=None, user_id=None):
    """
    Запасной вариант, когда API Google Books недоступен.
    Возвращает фиктивные данные для демонстрации работы бота.
    """
    # Генерируем случайный ID
    random_id = generate_random_id()
    
    # Выбираем фиктивную рекомендацию на основе жанра
    fallback_recommendations = {
        "fiction": {
            "id": random_id,
            "title": "Великий роман",
            "authors": "Известный Писатель",
            "published_date": "2023",
            "description": "Увлекательная история о приключениях и испытаниях героя в загадочном мире.",
            "categories": "Художественная литература",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        },
        "fantasy": {
            "id": random_id,
            "title": "Хроники магического мира",
            "authors": "Фантаст Волшебников",
            "published_date": "2024",
            "description": "Эпическая сага о магии, драконах и великих сражениях.",
            "categories": "Фэнтези",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        },
        "science": {
            "id": random_id,
            "title": "Наука будущего",
            "authors": "Профессор Знаний",
            "published_date": "2025",
            "description": "Исследование последних научных достижений и их влияния на будущее человечества.",
            "categories": "Наука, Технологии",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        },
        "history": {
            "id": random_id,
            "title": "Забытые страницы истории",
            "authors": "Историк Летописцев",
            "published_date": "2024",
            "description": "Исследование малоизвестных исторических событий, изменивших ход истории.",
            "categories": "История",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        },
        "biography": {
            "id": random_id,
            "title": "Жизнь замечательных людей",
            "authors": "Биограф Жизнеписец",
            "published_date": "2023",
            "description": "Биография выдающейся личности, преодолевшей все трудности на пути к успеху.",
            "categories": "Биография",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        },
        "poetry": {
            "id": random_id,
            "title": "Сборник стихов о вечном",
            "authors": "Поэт Рифмоплётов",
            "published_date": "2025",
            "description": "Сборник проникновенных стихов о любви, жизни и поиске смысла.",
            "categories": "Поэзия",
            "image_url": "https://via.placeholder.com/300",
            "preview_link": "https://books.google.com"
        }
    }
    
    # Сохраняем рекомендацию в историю
    if user_id:
        try:
            save_recommendation_history(user_id, 'book', random_id)
        except Exception as e:
            logger.error(f"Ошибка при сохранении рекомендации в историю: {e}")
    
    # Если жанр указан и он есть в нашем списке, возвращаем соответствующую рекомендацию
    if genre and genre in fallback_recommendations:
        return fallback_recommendations[genre]
    else:
        # Иначе возвращаем случайную рекомендацию
        random_genre = random.choice(list(fallback_recommendations.keys()))
        return fallback_recommendations[random_genre]

async def get_book_recommendations(genre=None, user_id=None):
    """
    Получает рекомендации книг на русском языке с расширенным логированием для отладки.
    """
    try:
        # Формируем запрос с учетом русского языка
        if genre:
            # Используем русский эквивалент жанра, если он есть
            ru_query = BOOK_GENRE_RUSSIAN.get(genre, genre)
            query = f"subject:{genre} OR {ru_query}"
            logger.info(f"Поиск книг по запросу: {query}")
        else:
            # Случайные категории для поиска книг на русском
            categories = ["роман", "фантастика", "детектив", "история", "биография", "поэзия"]
            random_category = random.choice(categories)
            query = f"subject:{random_category}"
            logger.info(f"Поиск случайных книг по запросу: {query}")
        
        # Добавляем параметры для русского языка
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=40&langRestrict=ru&country=RU"
        if GOOGLE_BOOKS_API_KEY:
            url += f"&key={GOOGLE_BOOKS_API_KEY}"
        
        logger.info(f"URL запроса к Google Books API: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            
            # Если получаем ошибку доступа с API ключом, пробуем без него
            if response.status_code == 403 and GOOGLE_BOOKS_API_KEY:
                logger.warning("Ошибка доступа с API ключом Google Books, пробуем без ключа")
                url = url.replace(f"&key={GOOGLE_BOOKS_API_KEY}", "")
                response = requests.get(url, timeout=10)
            
            response.raise_for_status()  # Проверяем статус ответа
            data = response.json()
            
            logger.info(f"Статус ответа API: {response.status_code}")
            logger.info(f"Количество найденных книг: {len(data.get('items', []))}")
            
            if 'items' in data and data['items']:
                # Исключаем книги, которые уже были рекомендованы пользователю
                if user_id:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                    SELECT item_id FROM recommendation_history
                    WHERE user_id = ? AND category = 'book'
                    ''', (user_id,))
                    recommended_ids = [row['item_id'] for row in cursor.fetchall()]
                    conn.close()
                    
                    # Фильтруем только книги на русском языке
                    filtered_results = []
                    for book in data['items']:
                        if book['id'] not in recommended_ids:
                            volume_info = book.get('volumeInfo', {})
                            language = volume_info.get('language', '')
                            # Добавляем только русские книги или книги без указания языка
                            if language == 'ru' or not language:
                                filtered_results.append(book)
                    
                    if filtered_results:
                        book = random.choice(filtered_results)
                        logger.info(f"Выбрана новая книга (не из истории): {book.get('id', 'unknown')}")
                    else:
                        # Если все книги уже рекомендованы или нет русских книг, используем запасной вариант
                        logger.warning("Не найдено подходящих книг на русском, использую запасной вариант")
                        return await get_book_recommendations_fallback(genre, user_id)
                else:
                    # Фильтруем только книги на русском языке
                    russian_books = []
                    for book in data['items']:
                        volume_info = book.get('volumeInfo', {})
                        language = volume_info.get('language', '')
                        if language == 'ru' or not language:
                            russian_books.append(book)
                    
                    if russian_books:
                        book = random.choice(russian_books)
                        logger.info(f"Выбрана случайная книга на русском: {book.get('id', 'unknown')}")
                    else:
                        logger.warning("Не найдено книг на русском языке, использую запасной вариант")
                        return await get_book_recommendations_fallback(genre, user_id)
                
                # Сохраняем рекомендацию в историю
                if user_id:
                    try:
                        save_recommendation_history(user_id, 'book', book['id'])
                        logger.info(f"Рекомендация сохранена в историю для пользователя {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении рекомендации в историю: {e}")
                
                # Формируем информацию о книге
                volume_info = book.get('volumeInfo', {})
                title = volume_info.get('title', 'Название неизвестно')
                authors = ', '.join(volume_info.get('authors', ['Автор неизвестен']))
                published_date = volume_info.get('publishedDate', 'Дата неизвестна')
                if published_date and len(published_date) >= 4:
                    published_date = published_date[:4]  # Берем только год
                description = volume_info.get('description', 'Описание отсутствует')
                if description and len(description) > 300:
                    description = description[:300] + '...'  # Обрезаем описание
                categories = ', '.join(volume_info.get('categories', ['Категория неизвестна']))
                image_url = volume_info.get('imageLinks', {}).get('thumbnail')
                preview_link = volume_info.get('previewLink')
                
                # Собираем результат
                result = {
                    'id': book['id'],
                    'title': title,
                    'authors': authors,
                    'published_date': published_date,
                    'description': description,
                    'categories': categories,
                    'image_url': image_url,
                    'preview_link': preview_link
                }
                
                logger.info(f"Сформирован результат для книги: {title}")
                return result
            else:
                logger.warning(f"API вернул пустой список книг или отсутствует ключ 'items'")
                return await get_book_recommendations_fallback(genre, user_id)
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Google Books API: {e}")
            return await get_book_recommendations_fallback(genre, user_id)
        
    except Exception as e:
        logger.error(f"Общая ошибка при получении рекомендаций книг: {e}")
        return await get_book_recommendations_fallback(genre, user_id)

# Функции-обработчики команд бота

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    register_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
        [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
        [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот-рекомендатель фильмов, музыки и книг. Выбери категорию, и я предложу тебе что-нибудь интересное!",
        reply_markup=reply_markup
    )
    
    return START_ROUTES

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Справка по боту-рекомендателю* 🤖\n\n"
        "*Доступные команды:*\n"
        "/start - Начать взаимодействие с ботом\n"
        "/help - Показать эту справку\n"
        "/movies - Рекомендации фильмов\n"
        "/music - Рекомендации музыки\n"
        "/books - Рекомендации книг\n"
        "/history - Показать историю рекомендаций\n\n"
        "*Как пользоваться:*\n"
        "1. Выберите интересующую категорию\n"
        "2. Выберите жанр или получите случайную рекомендацию\n"
        "3. Оцените рекомендацию для улучшения будущих предложений\n\n"
        "Приятного использования! 😊",
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено. Чтобы начать заново, используйте команду /start"
    )
    return ConversationHandler.END

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "category_movies":
        movie_genres = [
            [
                InlineKeyboardButton("Боевик", callback_data="movie_genre_28"),
                InlineKeyboardButton("Комедия", callback_data="movie_genre_35")
            ],
            [
                InlineKeyboardButton("Драма", callback_data="movie_genre_18"),
                InlineKeyboardButton("Фантастика", callback_data="movie_genre_878")
            ],
            [
                InlineKeyboardButton("Ужасы", callback_data="movie_genre_27"),
                InlineKeyboardButton("Романтика", callback_data="movie_genre_10749")
            ],
            [
                InlineKeyboardButton("Случайный фильм", callback_data="movie_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(movie_genres)
        
        await query.edit_message_text(
            text="Выбери жанр фильма или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        return GENRE_SELECTION
    
    elif callback_data == "category_music":
        music_genres = [
            [
                InlineKeyboardButton("Поп", callback_data="music_genre_pop"),
                InlineKeyboardButton("Рок", callback_data="music_genre_rock")
            ],
            [
                InlineKeyboardButton("Хип-хоп", callback_data="music_genre_hip-hop"),
                InlineKeyboardButton("Электронная", callback_data="music_genre_electronic")
            ],
            [
                InlineKeyboardButton("Джаз", callback_data="music_genre_jazz"),
                InlineKeyboardButton("Классическая", callback_data="music_genre_classical")
            ],
            [
                InlineKeyboardButton("Случайная музыка", callback_data="music_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(music_genres)
        
        await query.edit_message_text(
            text="Выбери жанр музыки или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        return GENRE_SELECTION
    
    elif callback_data == "category_books":
        book_genres = [
            [
                InlineKeyboardButton("Фантастика", callback_data="book_genre_fiction"),
                InlineKeyboardButton("Фэнтези", callback_data="book_genre_fantasy")
            ],
            [
                InlineKeyboardButton("Наука", callback_data="book_genre_science"),
                InlineKeyboardButton("История", callback_data="book_genre_history")
            ],
            [
                InlineKeyboardButton("Биография", callback_data="book_genre_biography"),
                InlineKeyboardButton("Поэзия", callback_data="book_genre_poetry")
            ],
            [
                InlineKeyboardButton("Случайная книга", callback_data="book_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(book_genres)
        
        await query.edit_message_text(
            text="Выбери жанр книги или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        return GENRE_SELECTION
    
    elif callback_data == "help":
        help_keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(help_keyboard)
        
        await query.edit_message_text(
            text="🤖 *Справка по боту-рекомендателю* 🤖\n\n"
            "*Доступные команды:*\n"
            "/start - Начать взаимодействие с ботом\n"
            "/help - Показать эту справку\n"
            "/movies - Рекомендации фильмов\n"
            "/music - Рекомендации музыки\n"
            "/books - Рекомендации книг\n"
            "/history - Показать историю рекомендаций\n\n"
            "*Как пользоваться:*\n"
            "1. Выберите интересующую категорию\n"
            "2. Выберите жанр или получите случайную рекомендацию\n"
            "3. Оцените рекомендацию для улучшения будущих предложений\n\n"
            "Приятного использования! 😊",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return START_ROUTES
    
    elif callback_data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        return START_ROUTES
    
    elif callback_data == "start_over":
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        return START_ROUTES
    
    return START_ROUTES

async def handle_genre_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    if callback_data.startswith("movie_genre_"):
        genre_id = callback_data.split("_")[-1]
        
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу фильм в жанре... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_movies")]])
        )
        
        try:
            movie = await get_movie_recommendations(genre_id, user_id)
            
            if movie:
                context.user_data['current_movie'] = movie
                
                # Подготовка сообщения о фильме
                message_text = (
                    f"🎬 *{movie['title']}*\n"
                    f"({movie['original_title']}, {movie['year']})\n\n"
                    f"⭐ Рейтинг: {movie['rating']}/10\n"
                    f"🎭 Жанры: {movie['genres']}\n\n"
                    f"📝 *Описание:*\n{movie['overview']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_movie_{movie['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_movie_{movie['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще фильм", callback_data="movie_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if movie['poster_url']:
                    await query.message.reply_photo(
                        photo=movie['poster_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    await query.delete_message()
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return MOVIE_ACTIONS
            else:
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации фильмов. Пожалуйста, попробуйте позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении рекомендации фильма: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске фильма. Пожалуйста, попробуйте другой жанр или вернитесь позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data == "movie_random":
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу случайный фильм... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_movies")]])
        )
        
        try:
            movie = await get_movie_recommendations(None, user_id)
            
            if movie:
                context.user_data['current_movie'] = movie
                
                # Подготовка сообщения о фильме
                message_text = (
                    f"🎬 *{movie['title']}*\n"
                    f"({movie['original_title']}, {movie['year']})\n\n"
                    f"⭐ Рейтинг: {movie['rating']}/10\n"
                    f"🎭 Жанры: {movie['genres']}\n\n"
                    f"📝 *Описание:*\n{movie['overview']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_movie_{movie['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_movie_{movie['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще фильм", callback_data="movie_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if movie['poster_url']:
                    await query.message.reply_photo(
                        photo=movie['poster_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    await query.delete_message()
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return MOVIE_ACTIONS
            else:
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации фильмов. Пожалуйста, попробуйте позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении случайного фильма: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске фильма. Пожалуйста, попробуйте позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data.startswith("music_genre_"):
        genre = callback_data.split("_")[-1]
        logger.info(f"Запрос рекомендации музыки жанра: {genre}, пользователь: {user_id}")
        
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу музыку в жанре {genre}... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_music")]])
        )
        
        try:
            # Пробуем получить рекомендации
            music = await get_music_recommendations(genre, user_id)
            
            if music:
                context.user_data['current_music'] = music
                
                # Подготовка сообщения о музыке
                message_text = (
                    f"🎵 *{music['track_name']}*\n"
                    f"👤 Исполнитель: {music['artists']}\n"
                    f"💿 Альбом: {music['album_name']}\n\n"
                )
                
                # Если в URL изображения есть "placeholder", предупреждаем о демо-режиме
                if music['album_image'] and "placeholder" in music['album_image']:
                    message_text += "_❗ Примечание: используются демо-данные из-за временной недоступности API._\n\n"
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_music_{music['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_music_{music['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще музыка", callback_data="music_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")]
                ]
                
                # Добавляем кнопку для прослушивания, если есть ссылка
                if music['spotify_url']:
                    keyboard.insert(0, [InlineKeyboardButton("🎧 Слушать на Spotify", url=music['spotify_url'])])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if music['album_image']:
                    await query.message.reply_photo(
                        photo=music['album_image'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    try:
                        await query.message.delete()  # Удаляем сообщение о поиске
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение о поиске: {e}")
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return MUSIC_ACTIONS
            else:
                logger.warning(f"Не удалось получить рекомендации музыки для жанра: {genre}")
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации музыки. Пожалуйста, попробуйте другой жанр или вернитесь позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении рекомендации музыки: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте другой жанр или вернитесь позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data == "music_random":
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу случайную музыку... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_music")]])
        )
        
        try:
            # Выбираем случайный жанр
            random_genre = random.choice(list(SPOTIFY_GENRE_MAPPING.keys()))
            logger.info(f"Выбран случайный жанр для музыки: {random_genre}")
            
            # Получаем рекомендацию
            music = await get_music_recommendations(random_genre, user_id)
            
            if music:
                context.user_data['current_music'] = music
                
                # Подготовка сообщения о музыке
                message_text = (
                    f"🎵 *{music['track_name']}*\n"
                    f"👤 Исполнитель: {music['artists']}\n"
                    f"💿 Альбом: {music['album_name']}\n\n"
                )
                
                # Если в URL изображения есть "placeholder", предупреждаем о демо-режиме
                if music['album_image'] and "placeholder" in music['album_image']:
                    message_text += "_❗ Примечание: используются демо-данные из-за временной недоступности API._\n\n"
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_music_{music['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_music_{music['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще музыка", callback_data="music_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")]
                ]
                
                # Добавляем кнопку для прослушивания, если есть ссылка
                if music['spotify_url']:
                    keyboard.insert(0, [InlineKeyboardButton("🎧 Слушать на Spotify", url=music['spotify_url'])])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if music['album_image']:
                    await query.message.reply_photo(
                        photo=music['album_image'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    try:
                        await query.message.delete()  # Удаляем сообщение о поиске
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение о поиске: {e}")
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return MUSIC_ACTIONS
            else:
                logger.warning("Не удалось получить рекомендации случайной музыки")
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации музыки. Пожалуйста, попробуйте позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении случайной музыки: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске музыки. Пожалуйста, попробуйте позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data.startswith("book_genre_"):
        genre = callback_data.split("_")[-1]
        logger.info(f"Запрос рекомендации книги жанра: {genre}, пользователь: {user_id}")
        
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу книгу в жанре {genre}... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_books")]])
        )
        
        try:
            book = await get_book_recommendations(genre, user_id)
            logger.info(f"Результат запроса книги: {'Успешно' if book else 'Не найдено'}")
            
            if book:
                context.user_data['current_book'] = book
                
                # Подготовка сообщения о книге
                message_text = (
                    f"📚 *{book['title']}*\n"
                    f"✍️ Автор: {book['authors']}\n"
                    f"📅 Год: {book['published_date']}\n"
                    f"🏷️ Категории: {book['categories']}\n\n"
                    f"📝 *Описание:*\n{book['description']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_book_{book['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_book_{book['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще книга", callback_data="book_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")]
                ]
                
                # Добавляем кнопку для предпросмотра, если есть ссылка
                if book['preview_link']:
                    keyboard.insert(0, [InlineKeyboardButton("👁️ Предпросмотр", url=book['preview_link'])])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if book['image_url']:
                    await query.message.reply_photo(
                        photo=book['image_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    try:
                        await query.message.delete()  # Удаляем сообщение о поиске
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение о поиске: {e}")
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return BOOK_ACTIONS
            else:
                logger.warning(f"Не удалось получить рекомендации книг для жанра: {genre}")
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации книг. Пожалуйста, попробуйте другой жанр или вернитесь позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении рекомендации книги: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске книги. Пожалуйста, попробуйте другой жанр или вернитесь позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data == "book_random":
        # Сообщаем пользователю о поиске
        await query.edit_message_text(
            text=f"🔍 Ищу случайную книгу... Это может занять несколько секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏱️ Отмена", callback_data="category_books")]])
        )
        
        try:
            book = await get_book_recommendations(None, user_id)
            
            if book:
                context.user_data['current_book'] = book
                
                # Подготовка сообщения о книге
                message_text = (
                    f"📚 *{book['title']}*\n"
                    f"✍️ Автор: {book['authors']}\n"
                    f"📅 Год: {book['published_date']}\n"
                    f"🏷️ Категории: {book['categories']}\n\n"
                    f"📝 *Описание:*\n{book['description']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_book_{book['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_book_{book['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще книга", callback_data="book_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")]
                ]
                
                # Добавляем кнопку для предпросмотра, если есть ссылка
                if book['preview_link']:
                    keyboard.insert(0, [InlineKeyboardButton("👁️ Предпросмотр", url=book['preview_link'])])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if book['image_url']:
                    await query.message.reply_photo(
                        photo=book['image_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    try:
                        await query.message.delete()  # Удаляем сообщение о поиске
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение о поиске: {e}")
                else:
                    await query.edit_message_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return BOOK_ACTIONS
            else:
                # Создаем клавиатуру с кнопкой "Назад"
                keyboard = [
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text="К сожалению, не удалось получить рекомендации книг. Пожалуйста, попробуйте позже.",
                    reply_markup=reply_markup
                )
                return GENRE_SELECTION
        except Exception as e:
            logger.error(f"Ошибка при получении случайной книги: {e}")
            # Создаем клавиатуру с кнопкой "Назад"
            keyboard = [
                [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=f"Произошла ошибка при поиске книги. Пожалуйста, попробуйте позже.",
                reply_markup=reply_markup
            )
            return GENRE_SELECTION
    
    elif callback_data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        return START_ROUTES
    
    return GENRE_SELECTION

async def handle_movie_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    if callback_data.startswith("rate_movie_"):
        # Обработка оценки фильма
        _, _, movie_id, rating = callback_data.split("_")
        rating = int(rating)
        
        # Получаем текущий фильм из контекста
        movie = context.user_data.get('current_movie')
        if movie:
            # Сохраняем оценку в базу данных
            save_preference(user_id, 'movie', movie.get('genres', ''), movie_id, rating)
            
            # Сообщаем об успешном сохранении оценки
            await query.message.reply_text(
                f"Спасибо за твою оценку! Я учту твои предпочтения в будущих рекомендациях."
            )
        
        # Возвращаемся к жанрам фильмов
        keyboard = [
            [InlineKeyboardButton("🔄 Еще фильм", callback_data="movie_random")],
            [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "Что дальше?",
            reply_markup=reply_markup
        )
        return MOVIE_ACTIONS
    
    elif callback_data == "movie_random":
        # Отображаем сообщение о поиске и напрямую вызываем функцию для получения случайного фильма
        
        # Создаем клавиатуру для отмены
        cancel_keyboard = [[InlineKeyboardButton("⏱️ Отмена", callback_data="category_movies")]]
        cancel_markup = InlineKeyboardMarkup(cancel_keyboard)
        
        # Отправляем сообщение о поиске
        searching_message = await query.message.reply_text(
            "🔍 Ищу интересный фильм для вас... Это может занять несколько секунд.",
            reply_markup=cancel_markup
        )
        
        try:
            # Напрямую получаем случайный фильм
            movie = await get_movie_recommendations(None, user_id)
            
            if movie:
                context.user_data['current_movie'] = movie
                
                # Подготовка сообщения о фильме
                message_text = (
                    f"🎬 *{movie['title']}*\n"
                    f"({movie['original_title']}, {movie['year']})\n\n"
                    f"⭐ Рейтинг: {movie['rating']}/10\n"
                    f"🎭 Жанры: {movie['genres']}\n\n"
                    f"📝 *Описание:*\n{movie['overview']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_movie_{movie['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_movie_{movie['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще фильм", callback_data="movie_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_movies")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Удаляем сообщение о поиске
                await searching_message.delete()
                
                if movie['poster_url']:
                    await query.message.reply_photo(
                        photo=movie['poster_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await query.message.reply_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return MOVIE_ACTIONS
            else:
                # Удаляем сообщение о поиске
                await searching_message.delete()
                
                await query.message.reply_text(
                    text="К сожалению, не удалось получить рекомендации фильмов. Пожалуйста, попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="category_movies")]])
                )
                return MOVIE_ACTIONS
        
        except Exception as e:
            # Логируем ошибку и показываем сообщение пользователю
            logger.error(f"Ошибка при получении случайного фильма: {e}")
            
            # Удаляем сообщение о поиске, если оно еще существует
            try:
                await searching_message.delete()
            except:
                pass
            
            await query.message.reply_text(
                text="Произошла ошибка при поиске фильма. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="category_movies")]])
            )
            return MOVIE_ACTIONS
    
    elif callback_data == "category_movies":
        # Отправляем новое сообщение с выбором жанров фильмов
        movie_genres = [
            [
                InlineKeyboardButton("Боевик", callback_data="movie_genre_28"),
                InlineKeyboardButton("Комедия", callback_data="movie_genre_35")
            ],
            [
                InlineKeyboardButton("Драма", callback_data="movie_genre_18"),
                InlineKeyboardButton("Фантастика", callback_data="movie_genre_878")
            ],
            [
                InlineKeyboardButton("Ужасы", callback_data="movie_genre_27"),
                InlineKeyboardButton("Романтика", callback_data="movie_genre_10749")
            ],
            [
                InlineKeyboardButton("Случайный фильм", callback_data="movie_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(movie_genres)
        
        # Отправляем новое сообщение
        await query.message.reply_text(
            text="Выбери жанр фильма или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        return GENRE_SELECTION
    
    elif callback_data == "back_to_main":
        # Отображаем главное меню
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем новое сообщение с главным меню
        await query.message.reply_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        return START_ROUTES
    
    return MOVIE_ACTIONS

async def handle_music_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    if callback_data.startswith("rate_music_"):
        # Обработка оценки музыки
        _, _, music_id, rating = callback_data.split("_")
        rating = int(rating)
        
        # Получаем текущий трек из контекста
        music = context.user_data.get('current_music')
        if music:
            # Сохраняем оценку в базу данных
            save_preference(user_id, 'music', '', music_id, rating)
            
            # Сообщаем об успешном сохранении оценки
            await query.message.reply_text(
                f"Спасибо за твою оценку! Я учту твои предпочтения в будущих рекомендациях."
            )
        
        # Возвращаемся к жанрам музыки
        keyboard = [
            [InlineKeyboardButton("🔄 Еще музыка", callback_data="music_random")],
            [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_music")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "Что дальше?",
            reply_markup=reply_markup
        )
        return MUSIC_ACTIONS
    
    elif callback_data == "music_random":
        # Отправляем новое сообщение с выбором жанров
        music_genres = [
            [
                InlineKeyboardButton("Поп", callback_data="music_genre_pop"),
                InlineKeyboardButton("Рок", callback_data="music_genre_rock")
            ],
            [
                InlineKeyboardButton("Хип-хоп", callback_data="music_genre_hip-hop"),
                InlineKeyboardButton("Электронная", callback_data="music_genre_electronic")
            ],
            [
                InlineKeyboardButton("Джаз", callback_data="music_genre_jazz"),
                InlineKeyboardButton("Классическая", callback_data="music_genre_classical")
            ],
            [
                InlineKeyboardButton("Случайная музыка", callback_data="music_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(music_genres)
        
        # Отправляем новое сообщение вместо попытки редактировать существующее
        await query.message.reply_text(
            text="Выбери жанр музыки или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение (если это возможно)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        return GENRE_SELECTION
    
    elif callback_data == "category_music":
        # Отправляем новое сообщение с выбором жанров
        music_genres = [
            [
                InlineKeyboardButton("Поп", callback_data="music_genre_pop"),
                InlineKeyboardButton("Рок", callback_data="music_genre_rock")
            ],
            [
                InlineKeyboardButton("Хип-хоп", callback_data="music_genre_hip-hop"),
                InlineKeyboardButton("Электронная", callback_data="music_genre_electronic")
            ],
            [
                InlineKeyboardButton("Джаз", callback_data="music_genre_jazz"),
                InlineKeyboardButton("Классическая", callback_data="music_genre_classical")
            ],
            [
                InlineKeyboardButton("Случайная музыка", callback_data="music_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(music_genres)
        
        # Отправляем новое сообщение вместо попытки редактировать существующее
        await query.message.reply_text(
            text="Выбери жанр музыки или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение (если это возможно)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
            
        return GENRE_SELECTION
    
    elif callback_data == "back_to_main":
        # Отображаем главное меню
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем новое сообщение вместо попытки редактировать существующее
        await query.message.reply_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение (если это возможно)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
            
        return START_ROUTES
    
    return MUSIC_ACTIONS

async def handle_book_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    if callback_data.startswith("rate_book_"):
        # Обработка оценки книги
        _, _, book_id, rating = callback_data.split("_")
        rating = int(rating)
        
        # Получаем текущую книгу из контекста
        book = context.user_data.get('current_book')
        if book:
            # Сохраняем оценку в базу данных
            save_preference(user_id, 'book', book.get('categories', ''), book_id, rating)
            
            # Сообщаем об успешном сохранении оценки
            await query.message.reply_text(
                f"Спасибо за твою оценку! Я учту твои предпочтения в будущих рекомендациях."
            )
        
        # Возвращаемся к жанрам книг
        keyboard = [
            [InlineKeyboardButton("🔄 Еще книга", callback_data="book_random")],
            [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "Что дальше?",
            reply_markup=reply_markup
        )
        return BOOK_ACTIONS
    
    elif callback_data == "book_random":
        # Отображаем сообщение о поиске и напрямую вызываем функцию для получения случайной книги
        
        # Создаем клавиатуру для отмены
        cancel_keyboard = [[InlineKeyboardButton("⏱️ Отмена", callback_data="category_books")]]
        cancel_markup = InlineKeyboardMarkup(cancel_keyboard)
        
        # Отправляем сообщение о поиске
        searching_message = await query.message.reply_text(
            "🔍 Ищу интересную книгу для вас... Это может занять несколько секунд.",
            reply_markup=cancel_markup
        )
        
        try:
            # Напрямую получаем случайную книгу
            book = await get_book_recommendations(None, user_id)
            
            if book:
                context.user_data['current_book'] = book
                
                # Подготовка сообщения о книге
                message_text = (
                    f"📚 *{book['title']}*\n"
                    f"✍️ Автор: {book['authors']}\n"
                    f"📅 Год: {book['published_date']}\n"
                    f"🏷️ Категории: {book['categories']}\n\n"
                    f"📝 *Описание:*\n{book['description']}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("👍 Нравится", callback_data=f"rate_book_{book['id']}_5"),
                        InlineKeyboardButton("👎 Не нравится", callback_data=f"rate_book_{book['id']}_1")
                    ],
                    [InlineKeyboardButton("🔄 Еще книга", callback_data="book_random")],
                    [InlineKeyboardButton("◀️ Назад к жанрам", callback_data="category_books")]
                ]
                
                # Добавляем кнопку для предпросмотра, если есть ссылка
                if book['preview_link']:
                    keyboard.insert(0, [InlineKeyboardButton("👁️ Предпросмотр", url=book['preview_link'])])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Удаляем сообщение о поиске
                await searching_message.delete()
                
                if book['image_url']:
                    await query.message.reply_photo(
                        photo=book['image_url'],
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await query.message.reply_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                
                return BOOK_ACTIONS
            else:
                # Удаляем сообщение о поиске
                await searching_message.delete()
                
                await query.message.reply_text(
                    text="К сожалению, не удалось получить рекомендации книг. Пожалуйста, попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="category_books")]])
                )
                return BOOK_ACTIONS
        
        except Exception as e:
            # Логируем ошибку и показываем сообщение пользователю
            logger.error(f"Ошибка при получении случайной книги: {e}")
            
            # Удаляем сообщение о поиске, если оно еще существует
            try:
                await searching_message.delete()
            except:
                pass
            
            await query.message.reply_text(
                text="Произошла ошибка при поиске книги. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="category_books")]])
            )
            return BOOK_ACTIONS
    
    elif callback_data == "category_books":
        # Отправляем новое сообщение с выбором жанров книг
        book_genres = [
            [
                InlineKeyboardButton("Фантастика", callback_data="book_genre_fiction"),
                InlineKeyboardButton("Фэнтези", callback_data="book_genre_fantasy")
            ],
            [
                InlineKeyboardButton("Наука", callback_data="book_genre_science"),
                InlineKeyboardButton("История", callback_data="book_genre_history")
            ],
            [
                InlineKeyboardButton("Биография", callback_data="book_genre_biography"),
                InlineKeyboardButton("Поэзия", callback_data="book_genre_poetry")
            ],
            [
                InlineKeyboardButton("Случайная книга", callback_data="book_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(book_genres)
        
        # Отправляем новое сообщение
        await query.message.reply_text(
            text="Выбери жанр книги или получи случайную рекомендацию:",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        return GENRE_SELECTION
    
    elif callback_data == "back_to_main":
        # Отображаем главное меню
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем новое сообщение с главным меню
        await query.message.reply_text(
            text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
            reply_markup=reply_markup
        )
        
        # Пробуем удалить старое сообщение
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение: {e}")
        
        return START_ROUTES
    
    return BOOK_ACTIONS

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем историю рекомендаций для пользователя
    cursor.execute('''
    SELECT category, item_id, recommendation_date FROM recommendation_history
    WHERE user_id = ?
    ORDER BY recommendation_date DESC
    LIMIT 10
    ''', (user_id,))
    
    history = cursor.fetchall()
    conn.close()
    
    if not history:
        await update.message.reply_text(
            "У тебя еще нет истории рекомендаций. Получи свою первую рекомендацию!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ])
        )
        return
    
    # Формируем сообщение с историей
    message_text = "*Твоя история рекомендаций:*\n\n"
    
    for item in history:
        category, item_id, date = item
        category_emoji = "🎬" if category == "movie" else "🎵" if category == "music" else "📚"
        date_formatted = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
        
        if category == "movie":
            # Получаем информацию о фильме по ID
            try:
                url = f"https://api.themoviedb.org/3/movie/{item_id}?api_key={TMDB_API_KEY}&language=ru"
                response = requests.get(url, timeout=10)
                movie_data = response.json()
                title = movie_data.get('title', 'Название неизвестно')
                message_text += f"{category_emoji} *Фильм:* {title} ({date_formatted})\n"
            except:
                message_text += f"{category_emoji} *Фильм:* ID {item_id} ({date_formatted})\n"
        
        elif category == "music":
            # Для музыки мы не делаем дополнительный запрос, так как токен может быть устаревшим
            message_text += f"{category_emoji} *Музыка:* ID {item_id} ({date_formatted})\n"
        
        elif category == "book":
            # Получаем информацию о книге по ID
            try:
                url = f"https://www.googleapis.com/books/v1/volumes/{item_id}"
                if GOOGLE_BOOKS_API_KEY:
                    url += f"?key={GOOGLE_BOOKS_API_KEY}"
                response = requests.get(url, timeout=10)
                book_data = response.json()
                title = book_data.get('volumeInfo', {}).get('title', 'Название неизвестно')
                message_text += f"{category_emoji} *Книга:* {title} ({date_formatted})\n"
            except:
                message_text += f"{category_emoji} *Книга:* ID {item_id} ({date_formatted})\n"
    
    await update.message.reply_text(
        message_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ])
    )

async def movies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Создаем клавиатуру с жанрами фильмов
    movie_genres = [
        [
            InlineKeyboardButton("Боевик", callback_data="movie_genre_28"),
            InlineKeyboardButton("Комедия", callback_data="movie_genre_35")
        ],
        [
            InlineKeyboardButton("Драма", callback_data="movie_genre_18"),
            InlineKeyboardButton("Фантастика", callback_data="movie_genre_878")
        ],
        [
            InlineKeyboardButton("Ужасы", callback_data="movie_genre_27"),
            InlineKeyboardButton("Романтика", callback_data="movie_genre_10749")
        ],
        [
            InlineKeyboardButton("Случайный фильм", callback_data="movie_random"),
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(movie_genres)
    
    await update.message.reply_text(
        text="Выбери жанр фильма или получи случайную рекомендацию:",
        reply_markup=reply_markup
    )
    
    return GENRE_SELECTION

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Создаем клавиатуру с жанрами музыки
    music_genres = [
        [
            InlineKeyboardButton("Поп", callback_data="music_genre_pop"),
            InlineKeyboardButton("Рок", callback_data="music_genre_rock")
        ],
        [
            InlineKeyboardButton("Хип-хоп", callback_data="music_genre_hip-hop"),
            InlineKeyboardButton("Электронная", callback_data="music_genre_electronic")
        ],
        [
            InlineKeyboardButton("Джаз", callback_data="music_genre_jazz"),
            InlineKeyboardButton("Классическая", callback_data="music_genre_classical")
        ],
        [
            InlineKeyboardButton("Случайная музыка", callback_data="music_random"),
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(music_genres)
    
    await update.message.reply_text(
        text="Выбери жанр музыки или получи случайную рекомендацию:",
        reply_markup=reply_markup
    )
    
    return GENRE_SELECTION

async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Создаем клавиатуру с жанрами книг
    book_genres = [
        [
            InlineKeyboardButton("Фантастика", callback_data="book_genre_fiction"),
            InlineKeyboardButton("Фэнтези", callback_data="book_genre_fantasy")
        ],
        [
            InlineKeyboardButton("Наука", callback_data="book_genre_science"),
            InlineKeyboardButton("История", callback_data="book_genre_history")
        ],
        [
            InlineKeyboardButton("Биография", callback_data="book_genre_biography"),
            InlineKeyboardButton("Поэзия", callback_data="book_genre_poetry")
        ],
        [
            InlineKeyboardButton("Случайная книга", callback_data="book_random"),
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(book_genres)
    
    await update.message.reply_text(
        text="Выбери жанр книги или получи случайную рекомендацию:",
        reply_markup=reply_markup
    )
    
    return GENRE_SELECTION

async def handle_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает callback-запросы, которые выпали из конечного автомата."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    logger.warning(f"Получен необработанный callback: {callback_data}")
    
    if callback_data == "category_books":
        book_genres = [
            [
                InlineKeyboardButton("Фантастика", callback_data="book_genre_fiction"),
                InlineKeyboardButton("Фэнтези", callback_data="book_genre_fantasy")
            ],
            [
                InlineKeyboardButton("Наука", callback_data="book_genre_science"),
                InlineKeyboardButton("История", callback_data="book_genre_history")
            ],
            [
                InlineKeyboardButton("Биография", callback_data="book_genre_biography"),
                InlineKeyboardButton("Поэзия", callback_data="book_genre_poetry")
            ],
            [
                InlineKeyboardButton("Случайная книга", callback_data="book_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(book_genres)
        
        try:
            await query.edit_message_text(
                text="Выбери жанр книги или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await query.message.reply_text(
                text="Выбери жанр книги или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        
        # Возвращаем пользователя в правильное состояние конечного автомата
        return GENRE_SELECTION
    
    elif callback_data == "category_movies":
        movie_genres = [
            [
                InlineKeyboardButton("Боевик", callback_data="movie_genre_28"),
                InlineKeyboardButton("Комедия", callback_data="movie_genre_35")
            ],
            [
                InlineKeyboardButton("Драма", callback_data="movie_genre_18"),
                InlineKeyboardButton("Фантастика", callback_data="movie_genre_878")
            ],
            [
                InlineKeyboardButton("Ужасы", callback_data="movie_genre_27"),
                InlineKeyboardButton("Романтика", callback_data="movie_genre_10749")
            ],
            [
                InlineKeyboardButton("Случайный фильм", callback_data="movie_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(movie_genres)
        
        try:
            await query.edit_message_text(
                text="Выбери жанр фильма или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await query.message.reply_text(
                text="Выбери жанр фильма или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        
        return GENRE_SELECTION
    
    elif callback_data == "category_music":
        music_genres = [
            [
                InlineKeyboardButton("Поп", callback_data="music_genre_pop"),
                InlineKeyboardButton("Рок", callback_data="music_genre_rock")
            ],
            [
                InlineKeyboardButton("Хип-хоп", callback_data="music_genre_hip-hop"),
                InlineKeyboardButton("Электронная", callback_data="music_genre_electronic")
            ],
            [
                InlineKeyboardButton("Джаз", callback_data="music_genre_jazz"),
                InlineKeyboardButton("Классическая", callback_data="music_genre_classical")
            ],
            [
                InlineKeyboardButton("Случайная музыка", callback_data="music_random"),
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(music_genres)
        
        try:
            await query.edit_message_text(
                text="Выбери жанр музыки или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await query.message.reply_text(
                text="Выбери жанр музыки или получи случайную рекомендацию:",
                reply_markup=reply_markup
            )
        
        return GENRE_SELECTION
    
    elif callback_data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(
                text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            await query.message.reply_text(
                text="Выбери категорию, и я предложу тебе что-нибудь интересное!",
                reply_markup=reply_markup
            )
        
        return START_ROUTES
    
    else:
        # Для неизвестных callback-запросов возвращаем в главное меню
        keyboard = [
            [InlineKeyboardButton("🎬 Фильмы", callback_data="category_movies")],
            [InlineKeyboardButton("🎵 Музыка", callback_data="category_music")],
            [InlineKeyboardButton("📚 Книги", callback_data="category_books")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            text="Извините, произошла ошибка в обработке запроса. Пожалуйста, выберите категорию:",
            reply_markup=reply_markup
        )
        
        return START_ROUTES

def main() -> None:
    """Запуск бота."""
    # Инициализация базы данных
    init_db()
    
    # Создание бота и получение токена из переменных среды
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Не указан токен бота в переменной TELEGRAM_BOT_TOKEN")
        return
    
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
        # Добавляем это для отладки
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
    
    # Глобальный обработчик для всех callback-запросов, не обработанных ConversationHandler
    application.add_handler(CallbackQueryHandler(handle_fallback_callback))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
