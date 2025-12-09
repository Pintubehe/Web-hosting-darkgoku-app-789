import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import json
import os
import logging
from datetime import datetime

# Configuration
BOT_TOKEN = "8567577176:AAFVrL4iqI1ceyL7aDtokMBaztDhpCgJmso"  # Replace with your bot token
ADMIN_ID = 8333354105      # Replace with your Telegram ID
DB_FILE = "anonymous_chat.db"  # SQLite database file
LOG_FILE = "bot.log"           # Log file
UPLOAD_FOLDER = "uploads"      # Flask upload folder

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        registration_date TEXT,
        last_activity TEXT,
        message_count INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        admin_message_id INTEGER,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def log_user_activity(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Check if user exists
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    
    if exists:
        # Update last activity
        cursor.execute('''
        UPDATE users 
        SET last_activity = ?, message_count = message_count + 1
        WHERE user_id = ?
        ''', (now, user_id))
    else:
        # Insert new user
        cursor.execute('''
        INSERT INTO users 
        (user_id, username, first_name, last_name, registration_date, last_activity, message_count)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (user_id, username, first_name, last_name, now, now))
    
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT registration_date, last_activity, message_count 
    FROM users 
    WHERE user_id = ?
    ''', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {
            'registration_date': result[0],
            'last_activity': result[1],
            'message_count': result[2]
        }
    return None

def is_user_blocked(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    return bool(result)

def block_user(user_id, admin_id, reason=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    cursor.execute('''
    INSERT OR REPLACE INTO blocked_users 
    (user_id, blocked_by, block_date, reason)
    VALUES (?, ?, ?, ?)
    ''', (user_id, admin_id, now, reason))
    
    conn.commit()
    conn.close()

def unblock_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
    
    conn.commit()
    conn.close()

# Admin commands
@bot.message_handler(commands=['pre'])
def toggle_premium_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        username = message.text.split()[1]
        with open('users.json', 'r') as f:
            users = json.load(f)
        
        if username in users:
            users[username]['is_premium'] = not users[username].get('is_premium', False)
            status = "Premium" if users[username]['is_premium'] else "Normal"
            
            with open('users.json', 'w') as f:
                json.dump(users, f)
            
            bot.reply_to(message, f"User {username} set to {status}")
        else:
            bot.reply_to(message, "User not found")
    except:
        bot.reply_to(message, "Usage: /pre <username>")

@bot.message_handler(commands=['ls'])
def list_files_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    response = "📁 Hosted Files:\n\n"
    file_count = 0
    
    for username in os.listdir(UPLOAD_FOLDER):
        user_dir = os.path.join(UPLOAD_FOLDER, username)
        if os.path.isdir(user_dir):
            files = os.listdir(user_dir)
            py_files = [f for f in files if f.endswith('.py')]
            
            if py_files:
                response += f"👤 {username}:\n"
                for file in py_files:
                    response += f"  - {file}\n"
                file_count += len(py_files)
    
    if file_count == 0:
        response = "No files hosted yet"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['ban'])
def ban_user_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        username = message.text.split()[1]
        with open('users.json', 'r') as f:
            users = json.load(f)
        
        if username in users:
            users[username]['is_blocked'] = True
            with open('users.json', 'w') as f:
                json.dump(users, f)
            
            # Stop user's processes
            with open('processes.json', 'r') as pf:
                processes = json.load(pf)
            
            for pid, process in list(processes.items()):
                if process['username'] == username:
                    try:
                        subprocess.run(['kill', str(process['pid'])])
                    except:
                        pass
                    processes.pop(pid)
            
            with open('processes.json', 'w') as pf:
                json.dump(processes, pf)
            
            bot.reply_to(message, f"User {username} banned")
        else:
            bot.reply_to(message, "User not found")
    except:
        bot.reply_to(message, "Usage: /ban <username>")

@bot.message_handler(commands=['unban'])
def unban_user_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        username = message.text.split()[1]
        with open('users.json', 'r') as f:
            users = json.load(f)
        
        if username in users:
            users[username]['is_blocked'] = False
            with open('users.json', 'w') as f:
                json.dump(users, f)
            
            bot.reply_to(message, f"User {username} unbanned")
        else:
            bot.reply_to(message, "User not found")
    except:
        bot.reply_to(message, "Usage: /unban <username>")

@bot.message_handler(commands=['list'])
def list_commands_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    commands = """
📋 Admin Commands:
/pre <username> - Toggle premium status
/ls - List all hosted files
/ban <username> - Block a user
/unban <username> - Unblock a user
/users - List all users
/stats - Show bot statistics
"""
    bot.reply_to(message, commands)

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    with open('users.json', 'r') as f:
        users = json.load(f)
    
    response = "👥 Registered Users:\n\n"
    for username, data in users.items():
        status = "🚫 Blocked" if data.get('is_blocked', False) else "✅ Active"
        premium = "🌟 Premium" if data.get('is_premium', False) else "🔹 Normal"
        response += f"👤 {username} - {status} - {premium}\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['stats'])
def bot_stats_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    with open('users.json', 'r') as f:
        users = json.load(f)
    
    total_users = len(users)
    active_users = sum(1 for u in users.values() if not u.get('is_blocked', False))
    premium_users = sum(1 for u in users.values() if u.get('is_premium', False))
    blocked_users = sum(1 for u in users.values() if u.get('is_blocked', False))
    
    # Count hosted files
    file_count = 0
    for username in os.listdir(UPLOAD_FOLDER):
        user_dir = os.path.join(UPLOAD_FOLDER, username)
        if os.path.isdir(user_dir):
            files = os.listdir(user_dir)
            file_count += len([f for f in files if f.endswith('.py')])
    
    response = f"""
📊 Bot Statistics:
👥 Total Users: {total_users}
✅ Active Users: {active_users}
🚫 Blocked Users: {blocked_users}
🌟 Premium Users: {premium_users}
📁 Hosted Files: {file_count}
"""
    bot.reply_to(message, response)

# Notify admin when a new user registers
def notify_new_user(username):
    bot.send_message(ADMIN_ID, f"👤 New user registered: {username}")

# Start the bot
def run_bot():
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.infinity_polling()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            time.sleep(10)

if __name__ == '__main__':
    logger.info("Anonymous Chat Bot starting...")
    run_bot()
