import os
import sqlite3
import datetime
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Enter your Telegram User ID as an environment variable or default integer
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# States for Admin Conversation
ADD_Q_TEXT, ADD_Q_OPTIONS, ADD_Q_CORRECT = range(3)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("brainarena.db")
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            correct_answers INTEGER DEFAULT 0,
            last_daily_date TEXT
        )
    """)
    
    # Questions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            opt_a TEXT,
            opt_b TEXT,
            opt_c TEXT,
            opt_d TEXT,
            correct_opt TEXT,
            is_daily INTEGER DEFAULT 0
        )
    """)
    
    # Seed initial questions if table is empty
    cursor.execute("SELECT COUNT(*) FROM questions")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
            INSERT INTO questions (question, opt_a, opt_b, opt_c, opt_d, correct_opt, is_daily)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            ("What is the capital of France?", "London", "Berlin", "Paris", "Madrid", "C", 0),
            ("Which planet is known as the Red Planet?", "Earth", "Mars", "Jupiter", "Venus", "B", 0),
            ("What is 12 x 12?", "124", "144", "148", "160", "B", 0),
            ("DAILY PUZZLE: What has keys but can't open locks?", "A Map", "A Piano", "A Clock", "A Vault", "B", 1)
        ])
    
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username):
    conn = sqlite3.connect("brainarena.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username or "Anonymous")
        )
        conn.commit()
    conn.close()

# --- HELPER FUNCTIONS ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎮 Play Quiz", callback_data="play_quiz"), InlineKeyboardButton("🧩 Daily Challenge", callback_data="daily_challenge")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"), InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username)
    
    welcome_text = (
        f"🧠 *Welcome to BrainArena, {user.first_name}!* 🧠\n\n"
        "Test your knowledge, climb the leaderboard, and solve daily puzzles!\n\n"
        "Choose an option below to get started:"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "menu":
        await start(update, context)

    elif data == "play_quiz":
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, question, opt_a, opt_b, opt_c, opt_d FROM questions WHERE is_daily = 0 ORDER BY RANDOM() LIMIT 1")
        q = cursor.fetchone()
        conn.close()

        if not q:
            await query.edit_message_text("No quiz questions available right now!", reply_markup=main_menu_keyboard())
            return

        q_id, q_text, a, b, c, d = q
        keyboard = [
            [InlineKeyboardButton(f"A) {a}", callback_data=f"ans_{q_id}_A"), InlineKeyboardButton(f"B) {b}", callback_data=f"ans_{q_id}_B")],
            [InlineKeyboardButton(f"C) {c}", callback_data=f"ans_{q_id}_C"), InlineKeyboardButton(f"D) {d}", callback_data=f"ans_{q_id}_D")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]
        await query.edit_message_text(f"❓ *Quiz Question:*\n\n{q_text}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("ans_"):
        _, q_id, user_ans = data.split("_")
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT correct_opt FROM questions WHERE id = ?", (q_id,))
        correct_opt = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET games_played = games_played + 1 WHERE user_id = ?", (user_id,))

        if user_ans == correct_opt:
            cursor.execute("UPDATE users SET points = points + 10, correct_answers = correct_answers + 1 WHERE user_id = ?", (user_id,))
            result_text = "🎉 *Correct!* You earned +10 points."
        else:
            result_text = f"❌ *Wrong!* The correct option was *{correct_opt}*."

        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton("🎮 Play Again", callback_data="play_quiz"), InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(result_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "daily_challenge":
        today = datetime.date.today().isoformat()
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT last_daily_date FROM users WHERE user_id = ?", (user_id,))
        last_date = cursor.fetchone()[0]

        if last_date == today:
            conn.close()
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
            await query.edit_message_text("⏳ You have already completed today's challenge! Check back tomorrow.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        cursor.execute("SELECT id, question, opt_a, opt_b, opt_c, opt_d FROM questions WHERE is_daily = 1 ORDER BY RANDOM() LIMIT 1")
        q = cursor.fetchone()
        conn.close()

        if not q:
            await query.edit_message_text("No daily challenge set for today!", reply_markup=main_menu_keyboard())
            return

        q_id, q_text, a, b, c, d = q
        keyboard = [
            [InlineKeyboardButton(f"A) {a}", callback_data=f"dans_{q_id}_A"), InlineKeyboardButton(f"B) {b}", callback_data=f"dans_{q_id}_B")],
            [InlineKeyboardButton(f"C) {c}", callback_data=f"dans_{q_id}_C"), InlineKeyboardButton(f"D) {d}", callback_data=f"dans_{q_id}_D")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]
        ]
        await query.edit_message_text(f"🧩 *Daily Challenge:*\n\n{q_text}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("dans_"):
        _, q_id, user_ans = data.split("_")
        today = datetime.date.today().isoformat()
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT correct_opt FROM questions WHERE id = ?", (q_id,))
        correct_opt = cursor.fetchone()[0]

        cursor.execute("UPDATE users SET last_daily_date = ?, games_played = games_played + 1 WHERE user_id = ?", (today, user_id))

        if user_ans == correct_opt:
            cursor.execute("UPDATE users SET points = points + 50, correct_answers = correct_answers + 1 WHERE user_id = ?", (user_id,))
            result_text = "🌟 *Bonus Master!* Correct! You earned +50 Daily Points!"
        else:
            result_text = f"❌ Incorrect! The correct answer was *{correct_opt}*. Try again tomorrow!"

        conn.commit()
        conn.close()

        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(result_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "leaderboard":
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
        top_users = cursor.fetchall()
        conn.close()

        lb_text = "🏆 *BrainArena Leaderboard (Top 10)* 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, (username, points) in enumerate(top_users, start=1):
            prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
            lb_text += f"{prefix} *{username}*: {points} pts\n"

        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(lb_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "my_stats":
        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, games_played, correct_answers FROM users WHERE user_id = ?", (user_id,))
        stats = cursor.fetchone()
        conn.close()

        points, games, correct = stats if stats else (0, 0, 0)
        accuracy = round((correct / games * 100), 1) if games > 0 else 0.0

        stats_text = (
            "📊 *Your Stats*\n\n"
            f"⭐ Total Points: `{points}`\n"
            f"🎮 Games Played: `{games}`\n"
            f"🎯 Accuracy: `{accuracy}%` ({correct}/{games})\n"
        )

        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(stats_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_panel":
        if ADMIN_ID != 0 and user_id != ADMIN_ID:
            await query.edit_message_text("🚫 Access Denied: You are not authorized to view the admin panel.", reply_markup=main_menu_keyboard())
            return

        conn = sqlite3.connect("brainarena.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM questions")
        total_q = cursor.fetchone()[0]
        conn.close()

        admin_text = (
            "⚙️ *Admin Panel*\n\n"
            f"👥 Total Players: `{total_users}`\n"
            f"❓ Total Questions: `{total_q}`\n\n"
            "Use /addquestion to add a new quiz question."
        )

        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]
        await query.edit_message_text(admin_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ADMIN ADD QUESTION CONVERSATION ---
async def start_add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Unauthorized command.")
        return ConversationHandler.END

    await update.message.reply_text("Type the *Question Text*:", parse_mode="Markdown")
    return ADD_Q_TEXT

async def get_q_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['q_text'] = update.message.text
    await update.message.reply_text("Enter 4 options separated by commas (e.g., Option A, Option B, Option C, Option D):")
    return ADD_Q_OPTIONS

async def get_q_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opts = [o.strip() for o in update.message.text.split(",")]
    if len(opts) != 4:
        await update.message.reply_text("⚠️ Please provide exactly 4 options separated by commas.")
        return ADD_Q_OPTIONS
    
    context.user_data['opts'] = opts
    await update.message.reply_text("Enter the correct option letter (A, B, C, or D):")
    return ADD_Q_CORRECT

async def get_q_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = update.message.text.strip().upper()
    if correct not in ["A", "B", "C", "D"]:
        await update.message.reply_text("⚠️ Invalid option. Enter A, B, C, or D:")
        return ADD_Q_CORRECT

    q_text = context.user_data['q_text']
    opts = context.user_data['opts']

    conn = sqlite3.connect("brainarena.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO questions (question, opt_a, opt_b, opt_c, opt_d, correct_opt, is_daily)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (q_text, opts[0], opts[1], opts[2], opts[3], correct))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Question added successfully!", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation canceled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- MAIN ENGINE ---
if __name__ == '__main__':
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is missing!")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Admin Conversation
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("addquestion", start_add_question)],
        states={
            ADD_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q_text)],
            ADD_Q_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q_options)],
            ADD_Q_CORRECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_q_correct)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("BrainArena Bot is running live...")
    app.run_polling()
