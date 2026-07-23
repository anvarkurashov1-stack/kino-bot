import sqlite3
import requests
import pytz
import telebot
from telebot import types
from datetime import datetime

# ==========================================
# 1. SOZLAMALAR
# ==========================================
BOT_TOKEN = "8570550365:AAEB1BZm-Sb8xNIzhd8WObvyT0TcKgm0_OI"
STORAGE_CHANNEL_ID = -1004460317

# Ob-havo API kaliti
WEATHER_API_KEY = "f6d4de7aafaecad64"

# Majburiy obuna kanali va havolalar
MAIN_CHANNEL_ID = "@uzkinomarket"
TELEGRAM_LINK = "https://t.me/uzkinomarket"
INSTAGRAM_LINK = "https://www.instagram.com/uzkinomarket?igsh=MzBtY2t0YzhzMm55"

# Admin ID si
ADMIN_ID = 5114804565

bot = telebot.TeleBot(BOT_TOKEN)

# 19 ta janr ro'yxati
GENRES = {
    "#jangari": "Jangari",
    "#drama": "Drama",
    "#komediya": "Komediya",
    "#melodrama": "Melodrama",
    "#detektiv": "Detektiv",
    "#triller": "Triller",
    "#qorqinchli": "Qo'rqinchli",
    "#sarguzasht": "Sarguzasht",
    "#fantastika": "Fantastika",
    "#fentezi": "Fentezi",
    "#animatsiya": "Animatsiya",
    "#tarjima": "Tarjima kino",
    "#premyera": "Premyera",
    "#serial": "Serial",
    "#multfilm": "Multfilm",
    "#biografiya": "Biografiya",
    "#tarixiy": "Tarixiy",
    "#sport": "Sport",
    "#boshqa": "Boshqa"
}

# ==========================================
# 2. BAZA BILAN ISHLASH
# ==========================================
def init_db():
    conn = sqlite3.connect("movies.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            caption TEXT,
            file_id TEXT,
            genre TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_movie_to_db(code, title, caption, file_id, genre):
    conn = sqlite3.connect("movies.db", check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO movies (code, title, caption, file_id, genre)
            VALUES (?, ?, ?, ?, ?)
        """, (code, title, caption, file_id, genre))
        conn.commit()
    except Exception as e:
        print("DB Error:", e)
    finally:
        conn.close()

def get_movie_by_code(code):
    conn = sqlite3.connect("movies.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT title, caption, file_id, genre FROM movies WHERE code = ?", (code,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_movies_by_genre(genre_key):
    conn = sqlite3.connect("movies.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM movies WHERE genre = ?", (genre_key,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# ==========================================
# 3. MAJBURIY OBUNANI TEKSHIRISH
# ==========================================
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        print("Obunani tekshirishda xatolik:", e)
    return False

def sub_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Telegram kanalga obuna", url=TELEGRAM_LINK))
    markup.add(types.InlineKeyboardButton("📸 Instagram sahifaga obuna", url=INSTAGRAM_LINK))
    markup.add(types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub"))
    return markup

# ==========================================
# 4. KANALDAN VIDEOLARNI QABUL QILISH
# ==========================================
@bot.channel_post_handler(content_types=['video'])
def handle_channel_video(message):
    if message.chat.id == STORAGE_CHANNEL_ID:
        caption = message.caption if message.caption else "Kino"
        file_id = message.video.file_id

        # Kod generatsiya qilish
        conn = sqlite3.connect("movies.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        count = cursor.fetchone()[0]
        code = str(count + 1)
        conn.close()

        # Janrni aniqlash
        detected_genre = "#boshqa"
        for key in GENRES.keys():
            if key in caption.lower():
                detected_genre = key
                break

        # Kino nomini olish (birinchi qator)
        lines = caption.split('\n')
        title = lines[0].replace("🎬 Kino:", "").strip() if lines else "Kino"

        # Bazaga qo'shish
        add_movie_to_db(code, title, caption, file_id, detected_genre)

        # Kanalga kodni yuborish
        bot.send_message(
            STORAGE_CHANNEL_ID,
            f"✅ Kino bazaga qo'shildi!\n🔑 Kino kodi: <code>{code}</code>",
            parse_mode="HTML",
            reply_to_message_id=message.message_id
        )

# ==========================================
# 5. SALOMLASHISH VA ASOSIY MENYU
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        bot.send_message(
            message.chat.id,
            "⚠️ Botimizdan to'liq foydalanish uchun avval quyidagi sahifalarimizga a'zo bo'ling:",
            reply_markup=sub_keyboard()
        )
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎬 Kinolar", "📂 Janrlar")
    markup.row("🌤 Ob-havo", "ℹ️ Ma'lumot")

    bot.send_message(
        message.chat.id,
        f"Assalomu alaykum, **{message.from_user.first_name}**! 👋\n\n"
        f"🎬 Kino qidirish botiga xush kelibsiz.\n"
        f"Kerakli kino kodini yuboring yoki pastdagi menyulardan foydalaning:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_sub(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.answer_callback_query(call.id, "Rahmat! Obuna tasdiqlandi ✅")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome(call.message)
    else:
        bot.answer_callback_query(call.id, "Siz hali kanalga a'zo bo'lmadingiz! ❌", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "📂 Janrlar")
def show_genres(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(message.chat.id, "Iltimos, avval sahifalarimizga obuna bo'ling:", reply_markup=sub_keyboard())
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for key, name in GENRES.items():
        markup.add(types.InlineKeyboardButton(name, callback_data=f"genre_{key}"))

    bot.send_message(message.chat.id, "📂 Kerakli janrni tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("genre_"))
def callback_genre(call):
    user_id = call.from_user.id
    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "Iltimos, avval kanalga obuna bo'ling!", show_alert=True)
        return

    genre_key = call.data.replace("genre_", "")
    movies = get_movies_by_genre(genre_key)

    if not movies:
        bot.answer_callback_query(call.id, "Bu janrda hozircha kinolar yo'q.", show_alert=True)
        return

    text = f"<b>{GENRES.get(genre_key, 'Janr')} bo'yicha kinolar:</b>\n\n"
    for code, title in movies:
        text += f"🔑 Kod: <code>{code}</code> — {title}\n"

    bot.send_message(call.message.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🎬 Kinolar")
def all_movies_info(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(message.chat.id, "Iltimos, avval sahifalarimizga obuna bo'ling:", reply_markup=sub_keyboard())
        return
    bot.send_message(message.chat.id, "🎬 Kino olish uchun kanaldan olingan raqamli kodni (masalan: 1, 2, 3...) yuboring.")

@bot.message_handler(func=lambda message: message.text == "🌤 Ob-havo")
def get_weather(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(message.chat.id, "Iltimos, avval sahifalarimizga obuna bo'ling:", reply_markup=sub_keyboard())
        return
    try:
        url = f"https://wttr.in/Tashkent?format=3&lang=uz"
        response = requests.get(url)
        weather_text = response.text if response.status_code == 200 else "Ob-havo ma'lumotini olishda xatolik yuz berdi."
    except Exception:
        weather_text = "Ob-havo xizmati vaqtincha ishlamayapti."

    bot.send_message(message.chat.id, f"🌤 Hozirgi ob-havo:\n{weather_text}")

@bot.message_handler(func=lambda message: message.text == "ℹ️ Ma'lumot")
def info_bot(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(message.chat.id, "Iltimos, avval sahifalarimizga obuna bo'ling:", reply_markup=sub_keyboard())
        return
    bot.send_message(
        message.chat.id,
        f"🤖 Bu bot yopiq kanaldagi kinolarni avtomatik tarzda kodlab bazaga saqlaydi va foydalanuvchilarga taqdim etadi.\n\n"
        f"📢 Bizning sahifalarimiz:\n"
        f"• Telegram: {TELEGRAM_LINK}\n"
        f"• Instagram: {INSTAGRAM_LINK}"
    )

@bot.message_handler(func=lambda message: True)
def find_movie(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.send_message(message.chat.id, "Iltimos, avval sahifalarimizga obuna bo'ling:", reply_markup=sub_keyboard())
        return

    code = message.text.strip()
    movie = get_movie_by_code(code)

    if movie:
        title, caption, file_id, genre = movie
        bot.send_video(message.chat.id, file_id, caption=caption, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ Bunday kodli kino topilmadi. Iltimos, to'g'ri kod kiriting.")

print("Bot ishga tushdi...")
bot.infinity_polling()