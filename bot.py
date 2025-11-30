import os
import time
import sqlite3
from threading import Thread
from flask import Flask
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# ---------------------------------------------------------
# CHANGE #1: PASTE YOUR TELEGRAM USER ID HERE (No Quotes)
# ---------------------------------------------------------
YOUR_TELEGRAM_ID = 1168032644 

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

# --- SERVER KEEPER ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive!"
def run_http(): app.run(host='0.0.0.0', port=8080)
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
                    await context.bot.send_message(referrer, "🎉 Referral Bonus! +1 Credit.")
            except: pass
        
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 3, referrer))
        conn.commit()
        
        # UPDATED WELCOME MESSAGE
        msg = (
            f"👋 **Welcome {first_name}!**\n\n"
            "I am your AI UPSC Mentor. You have **3 Free Credits**.\n\n"
            "🔥 **Features:**\n"
            "1. 📎 **Upload PDF/Photo** -> Check Answer\n"
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
        await update.message.reply_text("❌ Usage: `/explain [Topic]`\nExample: `/explain GDP`")
        return
    
    # Send a "Thinking..." message so user knows it's working
    status_msg = await update.message.reply_text(f"🧠 **Explaining '{topic}'...**")
    
    try:
        prompt = f"Explain '{topic}' to a UPSC aspirant in simple English with an Indian example."
        response = model.generate_content(prompt)
        # Removed parse_mode to prevent Markdown errors
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text("⚠️ Error connecting to AI. Please try again.")
        print(f"Explain Error: {e}")
    
    # Delete the "Thinking..." message
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Usage: `/news [Paste Link/Text]`")
        return
        
    status_msg = await update.message.reply_text("📰 **Summarizing...**")
    
    try:
        prompt = f"Summarize this for UPSC in 3 bullet points: {text[:2000]}"
        response = model.generate_content(prompt)
        # Removed parse_mode to prevent Markdown errors
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text("⚠️ Error reading news. Please try again.")
    
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status_msg.message_id)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # ---------------------------------------------------------
    # CHANGE #2: PASTE YOUR UPI ID BELOW inside the backticks
    # ---------------------------------------------------------
    msg = f"""
    💎 **Premium Credit Packs**
    
    • **Trial Pack:** ₹29 (3 Evaluations)
    • **Starter Pack:** ₹199 (20 Evaluations)
    • **Mains Warrior:** ₹499 (60 Evaluations)
    
    **How to Pay:**
    1. Send to: `mayadupare9@okaxis` 
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

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT credits, referrer_id FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if not row or row[0] <= 0:
        await update.message.reply_text(f"❌ **0 Credits!** Please `/buy` more.")
        conn.close()
        return

    msg = await update.message.reply_text("🔍 **Strict Examiner is checking...**\n(Reading file, please wait...)")
    
    file_name = "temp_file"
    if update.message.document:
        file_obj = await update.message.document.get_file()
        file_name = "temp.pdf"
    elif update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
        file_name = "temp.jpg"
    else:
        return

    await file_obj.download_to_drive(file_name)
    
    prompt = """
    You are a strict UPSC Mains Examiner.
    1. Read the attached document (Handwritten Answer).
    2. Transcribe the first 1 sentence to prove you read it.
    3. Evaluate: Structure, Content, Presentation.
    4. Score out of 10.
    5. List 2 Critical Flaws.
    """
    
    try:
        uploaded_file = genai.upload_file(path=file_name, display_name="Student Answer")
        
        # Wait for processing
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)

        response = model.generate_content([uploaded_file, prompt])
        
        c.execute("UPDATE users SET credits=credits-1 WHERE user_id=?", (user_id,))
        if row[1]: 
            c.execute("UPDATE users SET credits=credits+1 WHERE user_id=?", (row[1],))
        conn.commit()
        
        # Removed parse_mode here too for safety
        await update.message.reply_text(response.text)
        
    except Exception as e:
        await update.message.reply_text("⚠️ Error reading file. Please try again.")
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
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.PDF, handle_file))
    app.run_polling()