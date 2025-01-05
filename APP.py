import os
import requests
import logging
import sqlite3
from flask import Flask, request, redirect
from threading import Thread
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta

# Configuration for the GitHub OAuth app and Telegram bot
TELEGRAM_TOKEN = '7568210216:AAE_eIbDx7wyQKClq8j_kswx4htkiqeyBa8'
CHAT_ID = '7733181684'
CLIENT_ID = 'Iv23liCXzHQiT9gmF5RN'
CLIENT_SECRET = '2b202997707e5ce742de764cfcc75ea534daac6'
REDIRECT_URI = 'https://3a82-41-248-212-178.ngrok-free.app/callback'
OAUTH_URL = 'https://github.com/login/oauth/authorize'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_API = 'https://api.github.com/user'
DATABASE = 'tokens.db'

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app initialization
app = Flask(__name__)

# SQLite database setup
def create_table():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS repos (
            user_id TEXT,
            repo_name TEXT
        )
    ''')
    conn.commit()
    conn.close()

create_table()

# Flask route to initiate GitHub OAuth login
@app.route('/')
def home():
    oauth_url = f"{OAUTH_URL}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=repo"
    return redirect(oauth_url)

# Flask route for GitHub OAuth callback
@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Authorization failed", 400

    # Exchange code for access token
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    headers = {'Accept': 'application/json'}
    response = requests.post(TOKEN_URL, data=payload, headers=headers)
    data = response.json()

    if 'access_token' not in data:
        return "Error during authentication", 400

    access_token = data['access_token']

    # Fetch user info from GitHub
    headers = {'Authorization': f'token {access_token}'}
    user_info = requests.get(GITHUB_API, headers=headers).json()

    # Get Telegram user ID from the request
    telegram_user_id = request.args.get('state')  # Make sure you pass this from the / login flow

    # Save token to database with Telegram user ID
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO tokens (user_id, access_token) VALUES (?, ?)", 
                   (telegram_user_id, access_token))
    conn.commit()
    conn.close()

    return "Authorization successful! You are now connected with GitHub.", 200

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)  # This is the Telegram user ID

    logger.info(f"User {user_id} is requesting the start command.")

    # Check if user is authenticated by Telegram user ID
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token FROM tokens WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    logger.info(f"Result from DB: {result}")
    conn.close()

    if result:
        access_token = result[0]
        # Validate the token with GitHub
        headers = {'Authorization': f'token {access_token}'}
        response = requests.get(GITHUB_API, headers=headers)

        if response.status_code == 200:
            user_info = response.json()
            message = (
                f"Welcome back, {user_info.get('login')}! 👋\n\n"
                "You are authenticated with GitHub. Here's what you can do:\n\n"
                "1. **/github** - Reconnect your GitHub account (if needed).\n"
                "2. **/addrepo [repo_name]** - Add a repository to track.\n"
                "3. **/repos** - See the repositories you're tracking.\n"
                "4. **/remove** - Disconnect your GitHub account.\n"
                "5. **/clear** - Clear all tracked repositories.\n\n"
                "If you have any questions, just ask me! I’m here to help. 🚀"
            )
        else:
            message = (
                "Your GitHub authentication token seems to be invalid or expired.\n\n"
                "Please use /github to reconnect your account."
            )
    else:
        message = (
            "Welcome to BradyBot! 🎉\n\n"
            "I’m here to help you track your GitHub repositories directly through Telegram.\n\n"
            "### Here’s how you can get started:\n"
            "1. **/github** - Connect your GitHub account to BradyBot. After you connect, you can use various features like adding repositories or viewing your current repositories.\n"
            "2. **/addrepo [repo_name]** - Add a repository you want to track. Simply provide the repository name, and I’ll store it for you.\n"
            "3. **/repos** - View the list of repositories you're currently tracking.\n"
            "4. **/remove** - Disconnect your GitHub account if you'd like to reauthorize or no longer want to track repositories.\n"
            "5. **/clear** - Clear the list of repositories you're tracking. Use this carefully as it will remove all your tracked repositories.\n\n"
            "If you ever lose connection to GitHub or your token expires, just use **/github** to reconnect.\n\n"
            "I’m here to make your GitHub experience easier and more fun. Let’s get started! 🚀"
        )

    await update.message.reply_text(message)

async def github(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login_url = "https://3a82-41-248-212-178.ngrok-free.app"
    message = (
        "To connect your GitHub account, click here: "
        f"{login_url}\n\n"
        "After connecting, use /addrepo to track repositories."
    )
    await update.message.reply_text(message)

async def addrepo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT access_token FROM tokens WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        access_token = result[0]
        headers = {'Authorization': f'token {access_token}'}
        repo_name = ' '.join(context.args)  # Expecting the repo name to be passed as arguments
        
        # Fetch repository details
        repo_info = requests.get(f"https://api.github.com/repos/{repo_name}", headers=headers)
        
        if repo_info.status_code == 200:
            repo_details = repo_info.json()
            # Store the repository info in the database
            conn = sqlite3.connect(DATABASE, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO repos (user_id, repo_name) VALUES (?, ?)", (user_id, repo_name))
            conn.commit()
            conn.close()
            message = f"Repository {repo_name} has been added successfully!"
        else:
            message = f"Could not fetch information for repository: {repo_name}. Please check the name and try again."
    else:
        message = "You are not authenticated with GitHub. Use /github to connect your account first."

    await update.message.reply_text(message)

async def repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT repo_name FROM repos WHERE user_id=?", (user_id,))
    repos = cursor.fetchall()
    conn.close()

    if repos:
        repo_list = '\n'.join([repo[0] for repo in repos])
        message = f"Your tracked repositories:\n{repo_list}"
    else:
        message = "You haven't added any repositories yet. Use /addrepo to track some!"

    await update.message.reply_text(message)

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    message = "Your GitHub account has been disconnected."
    await update.message.reply_text(message)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)

    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM repos WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    message = "All tracked repositories have been cleared."
    await update.message.reply_text(message)

# Function to start the bot
def start_bot():
    asyncio.set_event_loop(asyncio.new_event_loop())  # Set the new event loop for the thread
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("github", github))
    application.add_handler(CommandHandler("addrepo", addrepo))
    application.add_handler(CommandHandler("repos", repos))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("clear", clear))

    application.run_polling()

def run_flask():
    app.run(host='0.0.0.0', port=5000)

# Start Flask and Telegram bot in separate threads
if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Start the bot with asyncio event loop
    bot_thread = Thread(target=start_bot)
    bot_thread.start()
