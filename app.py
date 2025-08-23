import os
import logging
import requests
import threading
import time
from flask import Flask   
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔗 GitHub JSON raw URL
BAD_WORDS_URL = "https://github.com/harshit0069/telegram_gaali/blob/1c6867849885203796349887e2515df3589e7dfa/badwords.json"

BAD_WORDS = set()  # global storage

# === Flask app ===
app = Flask(__name__)

@app.route("/")
def home():
    return "Gaali Filter Bot is running ✅", 200


# === Fetch function ===
def get_bad_words():
    try:
        resp = requests.get(BAD_WORDS_URL, timeout=5)
        data = resp.json()
        return set(data.get("bad_words", []))
    except Exception as e:
        print("⚠️ API fetch error:", e)
        # fallback list
        return {"madarchod", "bhosdike", "chutiya"}


# === Background refresher ===
def refresh_bad_words():
    global BAD_WORDS
    while True:
        BAD_WORDS = get_bad_words()
        print(f"✅ Gaali list refreshed, {len(BAD_WORDS)} words loaded")
        time.sleep(3600)  # har 1 ghante me refresh


# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚨 KOI BABUCHAK GAALI NAHI DEGA IS GROUP ME!")


async def filter_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.lower()
    user = update.message.from_user

    if any(bad_word in msg for bad_word in BAD_WORDS):
        try:
            await update.message.delete()
        except Exception as e:
            logging.error(f"Delete error: {e}")

        warning = f"⚠️ @{user.username or user.first_name}, BABUCHAK GANDI BAAT KARTA HAI😡!"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=warning)


# === Main ===
def main():
    global BAD_WORDS
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN env var missing")
        return

    # Initial load
    BAD_WORDS = get_bad_words()

    # Start background refresher thread
    threading.Thread(target=refresh_bad_words, daemon=True).start()

    # Start Telegram bot (polling) in separate thread
    def run_bot():
        app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
        app_telegram.add_handler(CommandHandler("start", start))
        app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_message))
        print("🤖 Gaali Filter Bot Running...")
        app_telegram.run_polling()

    threading.Thread(target=run_bot, daemon=True).start()

    # Start Flask app (Render will expose this port)
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()