import os
import base64
import sqlite3
from threading import Thread
from flask import Flask
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # <--- New Key Name

# ---------------------------------------------------------
# CHANGE #1: PASTE YOUR TELEGRAM ADMIN ID HERE
# ---------------------------------------------------------
YOUR_TELEGRAM_ID = 1168032644 

# --- AI SETUP (GROQ) ---
client = Groq(api_key=GROQ_API_KEY)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, credits INTEGER, referrer_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- SERVER KEEPER ---
app = Flask('')
@app.route('/')
def home(): return "Groq Bot is Alive!"
def run_http(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): t = Thread(target=run_http); t.start()

# --- HELPER: ENCODE IMAGE ---
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    args = context.args 
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    if not c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone():
        referrer = None
        if args and args[0].startswith("ref_"):
            try:
                referrer = int(args[0].split("_")[1])
                if referrer != user_id:
                    await context.bot.send_message(referrer, "🎉 Referral Bonus! +1 Credit.")
            except: pass

        c.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 3, referrer))
        conn.commit()
        
        msg = (
            f"👋 **Welcome {first_name}!**\n\n"
            "I am your AI UPSC Mentor (Powered by Llama 3).\n"
            "You have **3 Free Credits**.\n\n"
            "🔥 **Features:**\n"
            "1. 📸 **Upload Photo** -> Check Answer\n"
            "2. 🧠 `/explain [Topic]` (Free)\n"
            "3. 📰 `/news [Link]` (Free)\n"
            "4. 💎 `/buy` -> Get Credits"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("Welcome back! Send /balance to check credits.")
    conn.close()

async def explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic:
        await update.message.reply_text("❌ Usage: `/explain [Topic]`")
        return
    
    await update.message.reply_text(f"🧠 **Thinking...**")
    try:
        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": f"Explain '{topic}' to a UPSC aspirant in simple English with an Indian example.",
            }],
            model="llama-3.1-8b-instant", 
        )
        await update.message.reply_text(chat_completion.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text(f"⚠️ AI Error: {e}")

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Usage: `/news [Paste Link/Text]`")
        return
    await update.message.reply_text("📰 **Summarizing...**")
    try:
        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": f"Summarize this for UPSC in 3 bullet points: {text[:2000]}",
            }],
            model="llama-3.1-8b-instant", 
        )
        await update.message.reply_text(chat_completion.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text(f"⚠️ AI Error: {e}")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # ---------------------------------------------------------
    # CHANGE #2: PASTE YOUR UPI ID BELOW
    # ---------------------------------------------------------
    YOUR_UPI_ID = "mayadupare9@okaxis" 
    
    msg = f"""
    💎 **Premium Credit Packs**
    
    • **Trial Pack:** ₹29 (3 Evaluations)
    • **Starter Pack:** ₹199 (20 Evaluations)
    • **Mains Warrior:** ₹499 (60 Evaluations)
    
    **How to Pay:**
    1. Send to: `{YOUR_UPI_ID}` 
    2. Send Screenshot + ID to Admin.
    
    🆔 **Your ID:** `{user_id}`
    """
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_TELEGRAM_ID: return 
    try:
        target_user = int(context.args[0])
        amount = int(context.args[1])
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET credits=credits+? WHERE user_id=?", (amount, target_user))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Added {amount} credits to {target_user}")
        await context.bot.send_message(target_user, f"💎 Payment Received! {amount} Credits added.")
    except:
        await update.message.reply_text("❌ Usage: `/add [User_ID] [Amount]`")

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    row = c.execute("SELECT credits, referrer_id FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if not row or row[0] <= 0:
        await update.message.reply_text("❌ **0 Credits!** Please `/buy` more.")
        conn.close()
        return

    msg = await update.message.reply_text("🔍 **Llama Vision is checking...**")
    
    # Download Photo (Groq accepts jpg/png)
    file_name = "temp.jpg"
    try:
        photo_file = await update.message.photo[-1].get_file()
        await photo_file.download_to_drive(file_name)
        
        # Encode for Groq
        base64_image = encode_image(file_name)
        
        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "You are a strict UPSC Examiner. Transcribe 1 sentence. Check Intro, Body, Conclusion. Score out of 10."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            }],
            model="llama-3.2-11b-vision-preview", 
        )
        
        # Deduct Credit
        c.execute("UPDATE users SET credits=credits-1 WHERE user_id=?", (user_id,))
        if row[1]: 
             c.execute("UPDATE users SET credits=credits+1 WHERE user_id=?", (row[1],))
        conn.commit()
        
        await update.message.reply_text(chat_completion.choices[0].message.content)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")
        print(f"Error: {e}")
    
    conn.close()
    if os.path.exists(file_name): os.remove(file_name)
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg.message_id)

if __name__ == '__main__':
    keep_alive()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("explain", explain))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("add", add_credits))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.run_polling()
