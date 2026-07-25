from datetime import datetime
import os
import threading
from flask import Flask
import psycopg2
import pytz
import requests
import telebot
from telebot import types

# ==========================================
# 1. SOZLAMALAR VA KONFIGURATSIYA
# ==========================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8570550365:AAEgMz6KRm8vYZOqtBDZAMxbnJvRD-oIbXI"
)
WEATHER_API_KEY = "f6d4de7aafaecad64a98ca68a9f944be"

# PostgreSQL bulutli baza havolasi (Render Environment Variables bo'limidan)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgres://postgres:password@db.supabase.co:5432/postgres",
)

TELEGRAM_LINK = "https://t.me/uzkinomarket"
INSTAGRAM_LINK = (
    "https://www.instagram.com/uzkinomarket?igsh=MzBtY2t0YzhzMm55"
)
ADMIN_USERNAME = "@Uzkinomarket_admin"
ADMIN_ID = 5114804565

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 2. RENDER UCHUN FLASK WEB SERVER
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
  return "Bot tirik va ishlayapti!"


def run_web():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


# ==========================================
# 3. BAZA VA JANRLAR
# ==========================================
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
    "#boshqa": "Boshqa",
}


def get_db_connection():
  db_url = DATABASE_URL
  if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
  return psycopg2.connect(db_url)


def init_db():
  conn = get_db_connection()
  cursor = conn.cursor()

  # Kinolar va Seriallar asosiy jadvali
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE,
            title TEXT,
            caption TEXT,
            file_id TEXT,
            genre TEXT,
            is_series BOOLEAN DEFAULT FALSE
        )
    """)

  # Serial epizodlari jadvali
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            movie_code TEXT,
            season_num INT DEFAULT 1,
            episode_num INT,
            file_id TEXT
        )
    """)

  conn.commit()
  cursor.close()
  conn.close()


init_db()

# ==========================================
# 4. YORDAMCHI FUNKSIYALAR
# ==========================================


def get_movies_by_genre(genre_key):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT code, title FROM movies WHERE genre = %s", (genre_key,)
  )
  rows = cursor.fetchall()
  cursor.close()
  conn.close()
  return rows


def get_tashkent_weather():
  try:
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Tashkent&units=metric&appid={WEATHER_API_KEY}&lang=uz"
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
      data = response.json()
      temp = round(data["main"]["temp"])
      description = data["weather"][0]["description"].capitalize()
      return f"{description}, {temp}°C"
  except Exception as e:
    print("Ob-havo xatolik:", e)
  return "Ma'lumot olish imkoni bo'lmadi"


# Media faylni (Kino yoki Serial) bazaga saqlashning umumiy mantiqi
def process_and_save_media(file_id, caption, message):
  cap_lower = caption.lower()

  # A) AGAR SERIAL BO'LSA
  if "kod:" in cap_lower and "qism:" in cap_lower:
    try:
      parts = caption.split("|")
      code = ""
      season_num = 1
      ep_num = 1

      for part in parts:
        p = part.strip()
        if p.lower().startswith("kod:"):
          code = p.split(":")[1].strip()
        elif p.lower().startswith("fasl:"):
          season_num = int(p.split(":")[1].strip())
        elif p.lower().startswith("qism:"):
          ep_num = int(p.split(":")[1].strip())

      if not code:
        bot.reply_to(message, "❌ Serial kodi aniqlanmadi!")
        return

      conn = get_db_connection()
      cursor = conn.cursor()

      cursor.execute("SELECT id FROM movies WHERE code = %s", (code,))
      movie = cursor.fetchone()

      lines = [line.strip() for line in caption.split("\n") if line.strip()]
      title = "Serial"
      for line in lines:
        if "serial:" in line.lower() or "kino:" in line.lower():
          title = line.split(":", 1)[1].strip()
          break
      if title == "Serial" and lines:
        title = lines[0]

      if not movie:
        cursor.execute(
            """
                    INSERT INTO movies (code, title, caption, genre, is_series)
                    VALUES (%s, %s, %s, %s, TRUE)
                """,
            (code, title, caption, "#serial"),
        )

      cursor.execute(
          """
                INSERT INTO episodes (movie_code, season_num, episode_num, file_id)
                VALUES (%s, %s, %s, %s)
            """,
          (code, season_num, ep_num, file_id),
      )

      conn.commit()
      cursor.close()
      conn.close()

      bot.reply_to(
          message,
          f"✅ Serial qismi saqlandi!\n🔑 Kod: <code>{code}</code> | 🎬"
          f" {season_num}-fasl | 🍿 {ep_num}-qism",
          parse_mode="HTML",
      )
    except Exception as e:
      bot.reply_to(
          message,
          f"❌ Serial saqlashda xatolik! Format: `Kod: 55 | Fasl: 1 | Qism:"
          f" 1`\nXatolik: {e}",
      )

  # B) AGAR ODDIY KINO BO'LSA
  else:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
      code = None
      # Izohda kod berilgan bo'lsa, o'shani oladi
      if "kod:" in cap_lower:
        for line in caption.split("\n"):
          if "kod:" in line.lower():
            code = line.lower().split("kod:")[1].strip().split()[0]
            break

      # Izohda kod bo'lmasa, avtomatik raqam beradi
      if not code:
        cursor.execute("SELECT MAX(id) FROM movies WHERE is_series = FALSE")
        res = cursor.fetchone()[0]
        count = res if res else 0
        code = str(count + 1)

      detected_genre = "#boshqa"
      for key in GENRES.keys():
        if key in cap_lower:
          detected_genre = key
          break

      lines = [line.strip() for line in caption.split("\n") if line.strip()]
      title = lines[0] if lines else "Kino"
      if "kino:" in title.lower():
        title = title.split(":", 1)[1].strip()

      cursor.execute(
          """
                INSERT INTO movies (code, title, caption, file_id, genre, is_series)
                VALUES (%s, %s, %s, %s, %s, FALSE)
                ON CONFLICT (code) DO UPDATE 
                SET title = EXCLUDED.title, caption = EXCLUDED.caption, file_id = EXCLUDED.file_id, genre = EXCLUDED.genre
            """,
          (code, title, caption, file_id, detected_genre),
      )
      conn.commit()

      bot.reply_to(
          message,
          f"✅ Kino saqlandi!\n🔑 Kino kodi: <code>{code}</code>",
          parse_mode="HTML",
      )
    except Exception as e:
      bot.reply_to(message, f"❌ Xatolik yuz berdi: {e}")
    finally:
      cursor.close()
      conn.close()


# ==========================================
# 5. ADMIN HANDLERLARI (VIDEO VA URL)
# ==========================================


# 1. Tog'ridan-to'g'ri Video fayl kelganda
@bot.message_handler(content_types=["video"])
def handle_direct_video(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "Kechirasiz, bu funksiya faqat admin uchun.")
    return

  caption = message.caption if message.caption else "Kino"
  file_id = message.video.file_id
  process_and_save_media(file_id, caption, message)


# 2. Sayt havolasi (URL) kelganda (Trafik sarflanmaydi)
@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text
    and (
        message.text.startswith("http://")
        or message.text.startswith("https://")
    )
)
def handle_video_url(message):
  try:
    wait_msg = bot.reply_to(
        message,
        "⏳ Video URL orqali Telegram serveriga yuklanmoqda, kuting...",
    )

    lines = message.text.split("\n")
    video_url = lines[0].strip()
    caption = "\n".join(lines[1:]).strip() if len(lines) > 1 else "Kino"

    # Telegram API video URL orqali serverga fayl qilmasdan uzatadi
    sent_msg = bot.send_video(
        message.chat.id, video_url, caption=caption if caption else "Kino"
    )
    file_id = sent_msg.video.file_id

    bot.delete_message(message.chat.id, wait_msg.message_id)

    process_and_save_media(file_id, caption if caption else "Kino", message)

  except Exception as e:
    bot.reply_to(
        message,
        f"❌ URL orqali yuklashda xatolik!\nHavola to'g'ridan-to'g'ri MP4"
        f" faylga eltishi kerak.\nXatolik: {e}",
    )


# ==========================================
# 6. FOYDALANUVCHILAR UCHUN BUYRUTMALAR
# ==========================================
@bot.message_handler(commands=["start"])
def send_welcome(message):
  first_name = (
      message.from_user.first_name
      if message.from_user.first_name
      else "Foydalanuvchi"
  )
  username = f" (@{message.from_user.username})" if message.from_user.username else ""

  tz = pytz.timezone("Asia/Tashkent")
  current_time = datetime.now(tz).strftime("%d.%m.%Y | %H:%M")
  weather = get_tashkent_weather()

  markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
  markup.row("📂 Janrlar", "📢 Reklama")

  welcome_text = (
      f"Assalomu alaykum, <b>{first_name}{username}</b>! 👋\n\n"
      f"🇺🇿 Toshkent vaqti: {current_time}\n"
      f"🌤 Toshkent ob-havosi: {weather}\n\n"
      f"🎬 Yangi kinolarni manashu kanaldan topasiz: {TELEGRAM_LINK}\n\n"
      "Kino yoki serial qidirish uchun shunchaki uning raqamli kodini yuboring."
  )

  bot.send_message(
      message.chat.id, welcome_text, reply_markup=markup, parse_mode="HTML"
  )


@bot.message_handler(func=lambda message: message.text == "📂 Janrlar")
def show_genres(message):
  markup = types.InlineKeyboardMarkup(row_width=2)
  for key, name in GENRES.items():
    markup.add(types.InlineKeyboardButton(name, callback_data=f"genre_{key}"))

  bot.send_message(
      message.chat.id, "📂 Kerakli janrni tanlang:", reply_markup=markup
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("genre_"))
def callback_genre(call):
  genre_key = call.data.replace("genre_", "")
  movies = get_movies_by_genre(genre_key)

  if not movies:
    bot.answer_callback_query(
        call.id, "Bu janrda hozircha kinolar yo'q.", show_alert=True
    )
    return

  text = f"<b>{GENRES.get(genre_key, 'Janr')} bo'yicha kinolar:</b>\n\n"
  for code, title in movies:
    text += f"🔑 Kod: <code>{code}</code> — {title}\n"

  bot.send_message(call.message.chat.id, text, parse_mode="HTML")


@bot.message_handler(func=lambda message: message.text == "📢 Reklama")
def ad_info(message):
  ad_text = (
      f"📢 <b>Reklama berish uchun:</b>\n"
      "Agar botimizda o'z reklamangizni joylashtirmoqchi bo'lsangiz, quyidagi"
      f" manzilga murojaat qiling:\n👉 Murojaat uchun: {ADMIN_USERNAME}\n\n🌐"
      " <b>Bizning sahifalarimiz:</b>\n• Telegram:"
      f" {TELEGRAM_LINK}\n• Instagram: {INSTAGRAM_LINK}"
  )
  bot.send_message(message.chat.id, ad_text, parse_mode="HTML")


# ==========================================
# 7. QIDIRUV MANTIQI (KINO VA SERIAL)
# ==========================================
@bot.message_handler(func=lambda message: True)
def find_movie_or_series(message):
  code = message.text.strip()

  conn = get_db_connection()
  cursor = conn.cursor()

  # 1. Avval serial qismlarini tekshirish
  cursor.execute(
      "SELECT DISTINCT season_num FROM episodes WHERE movie_code = %s ORDER BY"
      " season_num ASC",
      (code,),
  )
  seasons = cursor.fetchall()

  if seasons:
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            f"🎬 {s_num}-Fasl", callback_data=f"season_{code}_{s_num}"
        )
        for (s_num,) in seasons
    ]
    markup.add(*buttons)

    cursor.execute("SELECT title FROM movies WHERE code = %s", (code,))
    m_row = cursor.fetchone()
    s_title = m_row[0] if m_row else f"Serial #{code}"

    bot.send_message(
        message.chat.id,
        f"🎬 <b>{s_title} (Kodi: {code})</b>\n\nIltimos, kerakli faslni tanlang"
        " 👇",
        reply_markup=markup,
        parse_mode="HTML",
    )
    cursor.close()
    conn.close()
    return

  # 2. Oddiy kino bo'lsa
  cursor.execute(
      "SELECT title, caption, file_id FROM movies WHERE code = %s AND is_series"
      " = FALSE",
      (code,),
  )
  movie = cursor.fetchone()
  cursor.close()
  conn.close()

  if movie:
    title, caption, file_id = movie
    bot.send_video(message.chat.id, file_id, caption=caption, parse_mode="HTML")
  else:
    bot.send_message(
        message.chat.id,
        "❌ Bunday kodli kino yoki serial topilmadi. Iltimos, kodingizni qayta"
        " tekshiring.",
    )


# ==========================================
# 8. SERIAL INTERFAYS CALLBACK'LARI
# ==========================================


# Fasl tanlanganda qismlarni ko'rsatish
@bot.callback_query_handler(func=lambda call: call.data.startswith("season_"))
def show_episodes(call):
  _, code, season_num = call.data.split("_")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT episode_num FROM episodes WHERE movie_code = %s AND season_num ="
      " %s ORDER BY episode_num ASC",
      (code, season_num),
  )
  episodes = cursor.fetchall()
  cursor.close()
  conn.close()

  markup = types.InlineKeyboardMarkup(row_width=3)
  buttons = [
      types.InlineKeyboardButton(
          f"🍿 {ep_num}-qism", callback_data=f"play_{code}_{season_num}_{ep_num}"
      )
      for (ep_num,) in episodes
  ]

  back_button = types.InlineKeyboardButton(
      "⬅️ Fasllarga qaytish", callback_data=f"back_seasons_{code}"
  )

  markup.add(*buttons)
  markup.add(back_button)

  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=f"🎬 <b>{season_num}-Fasl qismlari:</b>\n\nKerakli qismni tanlang 👇",
      reply_markup=markup,
      parse_mode="HTML",
  )


# Qism tanlanganda videoni yuborish
@bot.callback_query_handler(func=lambda call: call.data.startswith("play_"))
def send_episode(call):
  _, code, season_num, ep_num = call.data.split("_")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT file_id FROM episodes WHERE movie_code = %s AND season_num = %s"
      " AND episode_num = %s",
      (code, season_num, ep_num),
  )
  row = cursor.fetchone()
  cursor.close()
  conn.close()

  if row:
    file_id = row[0]
    bot.send_video(
        call.message.chat.id,
        file_id,
        caption=f"🎬 Kod: {code} | 🍿 {season_num}-Fasl, {ep_num}-qism",
    )
    bot.answer_callback_query(call.id)
  else:
    bot.answer_callback_query(call.id, "❌ Qism topilmadi!", show_alert=True)


# Fasllarga qaytish
@bot.callback_query_handler(
    func=lambda call: call.data.startswith("back_seasons_")
)
def back_to_seasons(call):
  code = call.data.replace("back_seasons_", "")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT DISTINCT season_num FROM episodes WHERE movie_code = %s ORDER BY"
      " season_num ASC",
      (code,),
  )
  seasons = cursor.fetchall()

  cursor.execute("SELECT title FROM movies WHERE code = %s", (code,))
  m_row = cursor.fetchone()
  s_title = m_row[0] if m_row else f"Serial #{code}"
  cursor.close()
  conn.close()

  markup = types.InlineKeyboardMarkup(row_width=2)
  buttons = [
      types.InlineKeyboardButton(
          f"🎬 {s_num}-Fasl", callback_data=f"season_{code}_{s_num}"
      )
      for (s_num,) in seasons
  ]
  markup.add(*buttons)

  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=(
          f"🎬 <b>{s_title} (Kodi: {code})</b>\n\nIltimos, kerakli faslni tanlang"
          " 👇"
      ),
      reply_markup=markup,
      parse_mode="HTML",
  )


# ==========================================
# 9. ISHGA TUSHIRISH
# ==========================================
if __name__ == "__main__":
  t = threading.Thread(target=run_web)
  t.start()

  print("Bot muvaffaqiyatli ishga tushdi...")
  bot.infinity_polling()
