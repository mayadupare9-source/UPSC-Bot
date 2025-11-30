import os
import sqlite3
from threading import Thread
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
YOUR_TELEGRAM_ID = 1168032644  # <--- REPLACE THIS NUMBER WITH YOUR ID!

# --- AI SETUP ---
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, credits INTEGER, referrer_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- SERVER KEEPER (Keeps bot alive) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive!"
def run_http(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): t = Thread(target=run_http); t.start()

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    args = context.args 
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    
    if not c.fetchone():
        referrer = None
        if args and args[0].startswith("ref_"):
            try:
                referrer = int(args[0].split("_")[1])
                if referrer != user_id:
                    await context.bot.send_message(referrer, "🎉 Referral Bonus! You get +1 Credit when they check an answer.")
            except: pass
        
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 3, referrer))
        conn.commit()
        
        msg = (
            f"👋 **Welcome {first_name}!**\n\n"
            "I am your AI UPSC Mentor. You have **3 Free Credits**.\n\n"
            "🔥 **Features:**\n"
            "1. 📸 **Check Answers:** Upload a photo (Paid)\n"
            "2. 🧠 **Explain:** `/explain Inflation` (Free)\n"
            "3. 📰 **News:** `/news [Link]` (Free)\n"
            "4. 💎 **Buy Credits:** `/buy`"
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
    await update.message.reply_text(f"🧠 **Explaining '{topic}'...**")
    prompt = f"Explain '{topic}' to a beginner UPSC aspirant in simple English using an Indian example. Keep it short."
    response = model.generate_content(prompt)
    await update.message.reply_text(response.text, parse_mode="Markdown")

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Usage: `/news [Paste Link or Text]`")
        return
    await update.message.reply_text("📰 **Summarizing...**")
    prompt = f"Summarize this for a UPSC Aspirant in 3 bullet points. Text: {text[:2000]}"
    response = model.generate_content(prompt)
    await update.message.reply_text(response.text, parse_mode="Markdown")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = f"""
    💎 **Premium Credit Packs**
    
    • **Trial Pack:** ₹29 (3 Evaluations)
    • **Starter Pack:** ₹199 (20 Evaluations)
    • **Mains Warrior:** ₹499 (60 Evaluations)
    
    **How to Pay:**
    1. Send amount to: `YOUR_UPI_ID@okaxis` (Replace with your UPI)
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
    c.execute("SELECT credits, referrer_id FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if not row or row[0] <= 0:
        ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        await update.message.reply_text(f"❌ **0 Credits!**\n\nInvite a friend (+1 Credit):\n`{ref_link}`\n\nOr buy a pack: `/buy`", parse_mode="Markdown")
        conn.close()
        return

    await update.message.reply_text("🔍 **Strict Examiner is checking...**")
    photo = await update.message.photo[-1].get_file()
    await photo.download_to_drive("temp.jpg")
    
    prompt = """
    You are a strict UPSC Examiner.
    1. Transcribe the first 10 words.
    2. Check: Intro, Body, Conclusion.
    3. Score out of 10.
    4. If blurry, output ONLY: "ERROR: UNREADABLE".
    """
    try:
        sample_file = genai.upload_file(path="temp.jpg", display_name="Ans")
        response = model.generate_content([sample_file, prompt])
        bot_reply = response.text
        
        if "ERROR: UNREADABLE" in bot_reply:
            await update.message.reply_text("⚠️ **Photo is blurry!** Credit NOT deducted.")
        else:
            c.execute("UPDATE users SET credits=credits-1 WHERE user_id=?", (user_id,))
            if row[1]: 
                c.execute("UPDATE users SET credits=credits+1 WHERE user_id=?", (row[1],))
            conn.commit()
            await update.message.reply_text(bot_reply)
    except:
        await update.message.reply_text("⚠️ Server Error. Try again.")
    
    conn.close()
    if os.path.exists("temp.jpg"): os.remove("temp.jpg")

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