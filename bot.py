from datetime import datetime
import sqlite3
import requests
import pytz
import telebot
from telebot import types

# ==========================================
# 1. SOZLAMALAR
# ==========================================
BOT_TOKEN = "8570550365:AAEgMz6KRm8vYZOqtBDZAMxbnJvRD-oIbXI"

# O'zingizdagi OpenWeatherMap API kalitini shu yerga yozing:
WEATHER_API_KEY = "f6d4de7aafaecad64a98ca68a9f944be" 

MAIN_CHANNEL_ID = "@uzkinomarket"
TELEGRAM_LINK = "https://t.me/uzkinomarket"
INSTAGRAM_LINK = "https://www.instagram.com/uzkinomarket?igsh=MzBtY2t0YzhzMm55"
ADMIN_USERNAME = "@Uzkinomarket_admin"

ADMIN_ID = 5114804565

bot = telebot.TeleBot(BOT_TOKEN)

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
# 3. MAJBURIY OBUNA VA ANIQ OB-HAVO
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

def get_tashkent_weather():
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Tashkent&units=metric&appid={WEATHER_API_KEY}&lang=uz"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            temp = round(data['main']['temp'])
            description = data['weather'][0]['description'].capitalize()
            return f"{description}, {temp}°C"
    except Exception as e:
        print("Ob-havo xatolik:", e)
    return "Ma'lumot olish imkoni bo'lmadi"

# ==========================================
# 4. ADMIN KINONI QO'SHISHI
# ==========================================
@bot.message_handler(content_types=['video'])
def handle_direct_video(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "Kechirasiz, bu funksiya faqat admin uchun.")
        return

    caption = message.caption if message.caption else "Kino"
    file_id = message.video.file_id

    conn = sqlite3.connect("movies.db", check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(id) FROM movies")
        res = cursor.fetchone()[0]
        count = res if res else 0
        code = str(count + 1)

        detected_genre = "#boshqa"
        for key in GENRES.keys():
            if key in caption.lower():
                detected_genre = key
                break

        lines = caption.split('\n')
        title = lines[0].replace("🎬 Kino:", "").strip() if lines else "Kino"

        cursor.execute("""
            INSERT INTO movies (code, title, caption, file_id, genre)
            VALUES (?, ?, ?, ?, ?)
        """, (code, title, caption, file_id, detected_genre))
        conn.commit()

        bot.reply_to(
            message,
            f"✅ Kino bazaga muvaffaqiyatli qo'shildi!\n🔑 Kino kodi: <code>{code}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik yuz berdi: {e}")
    finally:
        conn.close()

# ==========================================
# 5. /START VA ASOSIY MENYU
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

    first_name = message.from_user.first_name if message.from_user.first_name else "Foydalanuvchi"
    username = f" (@{message.from_user.username})" if message.from_user.username else ""

    # O'zbekiston vaqti (Tashkent vaqt mintaqasi)
    tz = pytz.timezone('Asia/Tashkent')
    current_time = datetime.now(tz).strftime("%d.%m.%Y | %H:%M")

    # Ob-havo
    weather = get_tashkent_weather()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📂 Janrlar", "📢 Reklama")

    welcome_text = (
        f"Assalomu alaykum, **{first_name}{username}**! 👋\n\n"
        f"🇺🇿 Toshkent vaqti: {current_time}\n"
        f"🌤 Toshkent ob-havosi: {weather}\n\n"
        f"🎬 Kino qidirish uchun shunchaki kanalimizdan olingan raqamli kodni yuboring yoki quyidagi tugmadan foydalaning:"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
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

@bot.message_handler(func=lambda message: message.text == "📢 Reklama")
def ad_info(message):
    ad_text = (
        f"📢 **Reklama berish uchun:**\n"
        f"Agar botimizda o'z reklamangizni joylashtirmoqchi bo'lsangiz, quyidagi manzilga murojaat qiling:\n"
        f"👉 Murojaat uchun: {ADMIN_USERNAME}\n\n"
        f"🌐 **Bizning sahifalarimiz:**\n"
        f"• Telegram: {TELEGRAM_LINK}\n"
        f"• Instagram: {INSTAGRAM_LINK}"
    )
    bot.send_message(message.chat.id, ad_text, parse_mode="Markdown")

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
