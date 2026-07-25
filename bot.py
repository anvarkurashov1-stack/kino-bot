from datetime import datetime
import os
import sqlite3
import threading
import time
from flask import Flask
import pytz
import requests
import telebot
from telebot import types

# ==========================================
# 1. SOZLAMALAR VA KONFIGURATSIYA (XAVFSIZ)
# ==========================================
# Maxfiy kalitlarni muhit o'zgaruvchilaridan olish afzal
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8570550365:AAGpZdxSfWQwf4Z5-KgMvD6zLG8awXH7rjU"
)
WEATHER_API_KEY = os.environ.get(
    "WEATHER_API_KEY", "f6d4de7aafaecad64a98ca68a9f944be"
)

TELEGRAM_LINK = "https://t.me/uzkinomarket"
INSTAGRAM_LINK = (
    "https://www.instagram.com/uzkinomarket?igsh=MzBtY2t0YzhzMm55"
)
ADMIN_USERNAME = "@Uzkinomarket_admin"

# Admin ID integer ekanligini ta'minlaymiz
try:
  ADMIN_ID = int(os.environ.get("ADMIN_ID", 5114804565))
except ValueError:
  ADMIN_ID = 5114804565

bot = telebot.TeleBot(BOT_TOKEN)

# Admin holatlarini va anti-spam taymerlarini saqlash
ADMIN_STATES = {}
USER_LAST_MESSAGE = {}  # Rate Limiting uchun

# ==========================================
# 2. FLASK WEB SERVER
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
  return "Bot tirik va ishlayapti!"


def run_web():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ==========================================
# 3. BAZA (SQLite) VA JANRLAR
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
  conn = sqlite3.connect("database.db", check_same_thread=False)
  return conn


def init_db():
  conn = get_db_connection()
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            title TEXT,
            caption TEXT,
            file_id TEXT,
            genre TEXT,
            is_series INTEGER DEFAULT 0
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_code TEXT,
            season_num INTEGER DEFAULT 1,
            episode_num INTEGER,
            file_id TEXT
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

  conn.commit()
  conn.close()


init_db()

# ==========================================
# 4. YORDAMCHI FUNKSIYALAR & XAVFSIZLIK
# ==========================================


def is_spam(user_id, limit_seconds=0.7):
  """Anti-Spam: Foydalanuvchi juda tez-tez so'rov yuborsa cheklaydi."""
  now = time.time()
  last_time = USER_LAST_MESSAGE.get(user_id, 0)
  if now - last_time < limit_seconds:
    return True
  USER_LAST_MESSAGE[user_id] = now
  return False


def add_user(user_id, first_name, username):
  try:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
            INSERT OR IGNORE INTO users (user_id, first_name, username, joined_at)
            VALUES (?, ?, ?, ?)
        """,
        (user_id, first_name, username, now),
    )
    conn.commit()
  except Exception as e:
    print(f"Baza xatosi (add_user): {e}")
  finally:
    conn.close()


def get_channels():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute("SELECT value FROM settings WHERE key = 'channels'")
  row = cursor.fetchone()
  conn.close()
  if row and row[0]:
    return [ch.strip() for ch in row[0].split(",") if ch.strip()]
  return []


def add_channel_to_db(channel):
  channels = get_channels()
  if channel not in channels:
    channels.append(channel)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('channels', ?)",
        (",".join(channels),),
    )
    conn.commit()
    conn.close()


def remove_channel_from_db(channel):
  channels = get_channels()
  if channel in channels:
    channels.remove(channel)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('channels', ?)",
        (",".join(channels),),
    )
    conn.commit()
    conn.close()


def check_subscription(user_id):
  channels = get_channels()
  unsubscribed = []
  for ch in channels:
    try:
      member = bot.get_chat_member(ch, user_id)
      if member.status in ["left", "kicked"]:
        unsubscribed.append(ch)
    except Exception as e:
      print(f"Kanalni tekshirishda xatolik ({ch}): {e}")
  return unsubscribed


def get_subscription_markup(unsubscribed_channels):
  markup = types.InlineKeyboardMarkup(row_width=1)
  for ch in unsubscribed_channels:
    ch_clean = ch.replace("@", "")
    url = f"https://t.me/{ch_clean}"
    markup.add(
        types.InlineKeyboardButton(
            text=f"➕ Kanalka a'zo bo'lish ({ch})", url=url
        )
    )
  markup.add(
      types.InlineKeyboardButton(
          text="✅ Tekshirish", callback_data="check_sub"
      )
  )
  return markup


def get_movies_by_genre(genre_key):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT DISTINCT code, title FROM movies WHERE genre = ?", (genre_key,)
  )
  rows = cursor.fetchall()
  conn.close()
  return rows


def get_tashkent_weather():
  try:
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Tashkent&units=metric&appid={WEATHER_API_KEY}&lang=uz"
    response = requests.get(url, timeout=4)
    if response.status_code == 200:
      data = response.json()
      temp = round(data["main"]["temp"])
      description = data["weather"][0]["description"].capitalize()
      return f"{description}, {temp}°C"
  except Exception as e:
    print("Ob-havo xatolik:", e)
  return "Ma'lumot olish imkoni bo'lmadi"


def process_and_save_media(file_id, caption, message):
  cap_lower = caption.lower()

  # A) SERIAL YOKI KINO QISMLARI BO'LSA
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
        bot.reply_to(message, "❌ Kod aniqlanmadi!")
        return

      conn = get_db_connection()
      cursor = conn.cursor()

      lines = [line.strip() for line in caption.split("\n") if line.strip()]
      title = "Kino / Serial"
      for line in lines:
        if "kino:" in line.lower() or "serial:" in line.lower():
          title = line.split(":", 1)[1].strip()
          break

      cursor.execute("SELECT id FROM movies WHERE code = ?", (code,))
      movie = cursor.fetchone()

      if not movie:
        cursor.execute(
            """
                    INSERT INTO movies (code, title, caption, genre, is_series)
                    VALUES (?, ?, ?, ?, 1)
                """,
            (code, title, caption, "#serial"),
        )

      cursor.execute(
          """
                INSERT INTO episodes (movie_code, season_num, episode_num, file_id)
                VALUES (?, ?, ?, ?)
            """,
          (code, season_num, ep_num, file_id),
      )

      conn.commit()
      conn.close()

      bot.reply_to(
          message,
          f"✅ Qism saqlandi!\n🔑 Kod: <code>{code}</code> | 🎬 {season_num}-fasl"
          f" | 🍿 {ep_num}-qism",
          parse_mode="HTML",
      )
    except Exception as e:
      bot.reply_to(
          message,
          f"❌ Qismni saqlashda xatolik! Format: `Kod: 5 | Qism: 1` yoki `Kod: 5"
          f" | Fasl: 1 | Qism: 1`\nXatolik: {e}",
      )

  # B) BIR QISMLI ODDIY KINO BO'LSA
  else:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
      code = None
      if "kod:" in cap_lower:
        for line in caption.split("\n"):
          if "kod:" in line.lower():
            code = line.lower().split("kod:")[1].strip().split()[0]
            break

      if not code:
        cursor.execute("SELECT MAX(id) FROM movies WHERE is_series = 0")
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
                VALUES (?, ?, ?, ?, ?, 0)
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
      conn.close()


# ==========================================
# 5. ADMIN HANDLERLARI (STRICT AUTHORIZATION)
# ==========================================
@bot.message_handler(
    commands=["admin"], func=lambda m: m.from_user.id == ADMIN_ID
)
def admin_panel(message):
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
  markup.add(
      "📊 Statistika",
      "📢 Xabar tarqatish",
      "➕ Kanal qo'shish",
      "➖ Kanal o'chirish",
      "📋 Kanallar ro'yxati",
      "❌ Chiqish",
  )

  bot.send_message(
      message.chat.id,
      "🛠 <b>Admin paneliga xush kelibsiz!</b>",
      reply_markup=markup,
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "❌ Chiqish"
)
def exit_admin(message):
  ADMIN_STATES.pop(ADMIN_ID, None)
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
  markup.row("📂 Janrlar", "📢 Reklama")
  bot.send_message(
      message.chat.id,
      "Admin panelidan chiqdingiz.",
      reply_markup=markup,
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "📊 Statistika"
)
def admin_stats(message):
  conn = get_db_connection()
  cursor = conn.cursor()

  cursor.execute("SELECT COUNT(*) FROM users")
  users_count = cursor.fetchone()[0]

  cursor.execute("SELECT COUNT(*) FROM movies WHERE is_series = 0")
  movies_count = cursor.fetchone()[0]

  cursor.execute("SELECT COUNT(*) FROM movies WHERE is_series = 1")
  series_count = cursor.fetchone()[0]

  cursor.execute("SELECT COUNT(*) FROM episodes")
  episodes_count = cursor.fetchone()[0]

  conn.close()

  stats_text = (
      f"📊 <b>Bot Statistikasi:</b>\n\n"
      f"👤 Foydalanuvchilar: <b>{users_count}</b> ta\n"
      f"🎬 Kinolar: <b>{movies_count}</b> ta\n"
      f"📺 Seriallar: <b>{series_count}</b> ta\n"
      f"🍿 Serial qismlari: <b>{episodes_count}</b> ta"
  )
  bot.send_message(message.chat.id, stats_text, parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "📋 Kanallar ro'yxati"
)
def admin_list_channels(message):
  channels = get_channels()
  if not channels:
    bot.send_message(
        message.chat.id, "⚠️ Hozircha majburiy obuna kanallari yo'q."
    )
    return

  text = "📋 <b>Majburiy obuna kanallari:</b>\n\n"
  for ch in channels:
    text += f"• {ch}\n"
  bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "➕ Kanal qo'shish"
)
def admin_add_channel_start(message):
  ADMIN_STATES[ADMIN_ID] = "waiting_for_add_channel"
  bot.send_message(
      message.chat.id,
      "➕ Qo'shmoqchi bo'lgan kanalingiz username'ini yuboring:\n<i>(Masalan:"
      " @uzkinomarket)</i>\n\n<b>Muhim:</b> Bot ushbu kanalda administrator"
      " bo'lishi kerak!",
      parse_mode="HTML",
  )


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "➖ Kanal o'chirish"
)
def admin_remove_channel_start(message):
  channels = get_channels()
  if not channels:
    bot.send_message(
        message.chat.id, "⚠️ O'chirish uchun kanallar mavjud emas."
    )
    return

  ADMIN_STATES[ADMIN_ID] = "waiting_for_remove_channel"
  text = "➖ O'chirmoqchi bo'lgan kanalingiz username'ini kiriting:\n\n"
  for ch in channels:
    text += f"• <code>{ch}</code>\n"
  bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.message_handler(
    func=lambda message: message.from_user.id == ADMIN_ID
    and message.text == "📢 Xabar tarqatish"
)
def admin_broadcast_start(message):
  ADMIN_STATES[ADMIN_ID] = "waiting_for_broadcast"
  bot.send_message(
      message.chat.id,
      "📢 Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting (rasm,"
      " video, matn va h.k.):",
  )


@bot.message_handler(
    content_types=["video"], func=lambda m: m.from_user.id == ADMIN_ID
)
def handle_direct_video(message):
  caption = message.caption if message.caption else "Kino"
  file_id = message.video.file_id
  process_and_save_media(file_id, caption, message)


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

    sent_msg = bot.send_video(
        message.chat.id, video_url, caption=caption if caption else "Kino"
    )
    file_id = sent_msg.video.file_id

    bot.delete_message(message.chat.id, wait_msg.message_id)
    process_and_save_media(file_id, caption if caption else "Kino", message)

  except Exception as e:
    bot.reply_to(message, f"❌ URL orqali yuklashda xatolik!\nXatolik: {e}")


# ==========================================
# 6. FOYDALANUVCHILAR VA BUYRUQLAR
# ==========================================
@bot.message_handler(commands=["start"])
def send_welcome(message):
  if is_spam(message.from_user.id):
    return

  add_user(
      message.from_user.id,
      message.from_user.first_name,
      message.from_user.username,
  )

  unsubscribed = check_subscription(message.from_user.id)
  if unsubscribed:
    bot.send_message(
        message.chat.id,
        "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>",
        reply_markup=get_subscription_markup(unsubscribed),
        parse_mode="HTML",
    )
    return

  first_name = (
      message.from_user.first_name
      if message.from_user.first_name
      else "Foydalanuvchi"
  )
  username = (
      f" (@{message.from_user.username})" if message.from_user.username else ""
  )

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


@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
  unsubscribed = check_subscription(call.from_user.id)
  if unsubscribed:
    bot.answer_callback_query(
        call.id,
        "❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!",
        show_alert=True,
    )
  else:
    try:
      bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
      pass
    bot.send_message(
        call.message.chat.id,
        "✅ Rahmat! Kanallarga muvaffaqiyatli a'zo bo'ldingiz.\nKino kodini"
        " yuborishingiz mumkin.",
    )


@bot.message_handler(func=lambda message: message.text == "📂 Janrlar")
def show_genres(message):
  if is_spam(message.from_user.id):
    return

  unsubscribed = check_subscription(message.from_user.id)
  if unsubscribed:
    bot.send_message(
        message.chat.id,
        "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>",
        reply_markup=get_subscription_markup(unsubscribed),
        parse_mode="HTML",
    )
    return

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
  if is_spam(message.from_user.id):
    return

  ad_text = (
      f"📢 <b>Reklama berish uchun:</b>\n"
      f"Murojaat uchun: {ADMIN_USERNAME}\n\n"
      f"• Telegram: {TELEGRAM_LINK}\n"
      f"• Instagram: {INSTAGRAM_LINK}"
  )
  bot.send_message(message.chat.id, ad_text, parse_mode="HTML")


# ==========================================
# 7. QIDIRUV MANTIQI VA ADMIN HOLATLARINI QABUL QILISH
# ==========================================
@bot.message_handler(
    content_types=["text", "photo", "video", "document", "audio", "voice"]
)
def handle_all_messages(message):
  user_id = message.from_user.id

  # Spam tekshiruvi
  if is_spam(user_id):
    return

  add_user(user_id, message.from_user.first_name, message.from_user.username)

  # Admin buyruqlarini qabul qilish
  if user_id == ADMIN_ID and user_id in ADMIN_STATES:
    state = ADMIN_STATES[user_id]

    if state == "waiting_for_add_channel":
      ch = message.text.strip()
      if not ch.startswith("@"):
        ch = "@" + ch
      add_channel_to_db(ch)
      ADMIN_STATES.pop(user_id, None)
      bot.send_message(
          message.chat.id, f"✅ Kanal muvaffaqiyatli qo'shildi: {ch}"
      )
      return

    elif state == "waiting_for_remove_channel":
      ch = message.text.strip()
      if not ch.startswith("@"):
        ch = "@" + ch
      remove_channel_from_db(ch)
      ADMIN_STATES.pop(user_id, None)
      bot.send_message(message.chat.id, f"✅ Kanal o'chirildi: {ch}")
      return

    elif state == "waiting_for_broadcast":
      ADMIN_STATES.pop(user_id, None)
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute("SELECT user_id FROM users")
      users = cursor.fetchall()
      conn.close()

      bot.send_message(
          message.chat.id,
          f"🚀 Xabar tarqatish boshlandi... Jami foydalanuvchilar: {len(users)}",
      )

      success = 0
      failed = 0

      # XAFSIZ BROADCAST: FloodWait cheklovining oldini olish uchun taymer kiritildi
      for i, (u_id,) in enumerate(users):
        try:
          bot.copy_message(u_id, message.chat.id, message.message_id)
          success += 1
        except Exception:
          failed += 1

        # Har 25 ta xabardan so'ng 1 soniya kutamiz
        if i % 25 == 0:
          time.sleep(1)

      bot.send_message(
          message.chat.id,
          f"✅ Xabar tarqatib bo'lindi!\n\n"
          f"🟢 Muvaffaqiyatli: {success} ta\n"
          f"🔴 Yetib bormadi (bloklangan): {failed} ta",
      )
      return

  # Oddiy foydalanuvchilar uchun obunani tekshirish
  unsubscribed = check_subscription(user_id)
  if unsubscribed:
    bot.send_message(
        message.chat.id,
        "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>",
        reply_markup=get_subscription_markup(unsubscribed),
        parse_mode="HTML",
    )
    return

  # Kino qidirish mantiqi
  if message.text:
    code = message.text.strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Epizodlar bor-yo'qligini tekshiramiz
    cursor.execute(
        "SELECT DISTINCT season_num FROM episodes WHERE movie_code = ? ORDER BY"
        " season_num ASC",
        (code,),
    )
    seasons = cursor.fetchall()

    if seasons:
      cursor.execute("SELECT title FROM movies WHERE code = ?", (code,))
      m_row = cursor.fetchone()
      s_title = m_row[0] if m_row else f"Kino / Serial #{code}"

      # Agar faqat 1 ta fasl bo'lsa
      if len(seasons) == 1:
        s_num = seasons[0][0]
        cursor.execute(
            "SELECT episode_num FROM episodes WHERE movie_code = ? AND"
            " season_num = ? ORDER BY episode_num ASC",
            (code, s_num),
        )
        episodes = cursor.fetchall()

        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton(
                f"🎬 {ep_num}-Qism",
                callback_data=f"play_{code}_{s_num}_{ep_num}",
            )
            for (ep_num,) in episodes
        ]
        markup.add(*buttons)

        bot.send_message(
            message.chat.id,
            f"🎬 <b>{s_title} (Kodi: {code})</b>\n\nKerakli qismni tanlang 👇",
            reply_markup=markup,
            parse_mode="HTML",
        )
      else:
        # Ko'p faslli serial bo'lsa
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton(
                f"🎬 {s_num}-Fasl", callback_data=f"season_{code}_{s_num}"
            )
            for (s_num,) in seasons
        ]
        markup.add(*buttons)

        bot.send_message(
            message.chat.id,
            f"🎬 <b>{s_title} (Kodi: {code})</b>\n\nIltimos, kerakli faslni tanlang"
            " 👇",
            reply_markup=markup,
            parse_mode="HTML",
        )

      conn.close()
      return

    # 2. Oddiy bir qismli kino bo'lsa
    cursor.execute(
        "SELECT title, caption, file_id FROM movies WHERE code = ? AND"
        " is_series = 0",
        (code,),
    )
    movie = cursor.fetchone()
    conn.close()

    if movie:
      title, caption, file_id = movie
      bot.send_video(
          message.chat.id, file_id, caption=caption, parse_mode="HTML"
      )
    else:
      bot.send_message(
          message.chat.id,
          "❌ Bunday kodli kino yoki serial topilmadi. Kodingizni qayta"
          " tekshiring.",
      )


# ==========================================
# 8. CALLBACK HANDLERLAR
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("season_"))
def show_episodes(call):
  _, code, season_num = call.data.split("_")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT episode_num FROM episodes WHERE movie_code = ? AND season_num = ?"
      " ORDER BY episode_num ASC",
      (code, season_num),
  )
  episodes = cursor.fetchall()
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


@bot.callback_query_handler(func=lambda call: call.data.startswith("play_"))
def send_episode(call):
  _, code, season_num, ep_num = call.data.split("_")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT file_id FROM episodes WHERE movie_code = ? AND season_num = ? AND"
      " episode_num = ?",
      (code, season_num, ep_num),
  )
  row = cursor.fetchone()
  conn.close()

  if row:
    file_id = row[0]
    bot.send_video(
        call.message.chat.id,
        file_id,
        caption=f"🎬 Kod: {code} | 🍿 {ep_num}-Qism",
    )
    bot.answer_callback_query(call.id)
  else:
    bot.answer_callback_query(call.id, "❌ Qism topilmadi!", show_alert=True)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("back_seasons_")
)
def back_to_seasons(call):
  code = call.data.replace("back_seasons_", "")

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT DISTINCT season_num FROM episodes WHERE movie_code = ? ORDER BY"
      " season_num ASC",
      (code,),
  )
  seasons = cursor.fetchall()

  cursor.execute("SELECT title FROM movies WHERE code = ?", (code,))
  m_row = cursor.fetchone()
  s_title = m_row[0] if m_row else f"Kino / Serial #{code}"
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
  t.daemon = True
  t.start()

  try:
    bot.remove_webhook()
  except Exception as e:
    print("Webhook tozalandi:", e)

  print("Bot xavfsiz rejimda ishga tushdi...")
  bot.infinity_polling(skip_pending=True)
