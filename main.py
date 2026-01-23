import discord
from discord.ext import commands, tasks
import os
import secrets  # For better randomization
import datetime
import json
import pytz
import asyncio
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

# --- Initialization & Configuration ---

# Load settings
try:
    with open("appsettings.json", "r") as f:
        settings = json.load(f)
        TOKEN = settings["Token"]
        GIF_DIR = settings["GifDirectory"]
        CONFIG_FILE = settings["ConfigFile"]
        USERS_FILE = settings["UsersFile"]
        LOG_RETENTION_DAYS = settings.get("LogRetentionDays", 7)
except FileNotFoundError:
    print("CRITICAL: 'appsettings.json' not found. Terminating.")
    sys.exit(1)
except KeyError as e:
    print(f"CRITICAL: Missing setting {e} in 'appsettings.json'. Terminating.")
    sys.exit(1)

# --- Logging Setup (Minimalist) ---
if not os.path.exists("logs"):
    os.makedirs("logs")

logger = logging.getLogger("FunkyMonkey")
logger.setLevel(logging.INFO)

# Handler: Rotate logs at midnight, keep last X days
handler = TimedRotatingFileHandler(
    filename="logs/bot.log",
    when="midnight",
    interval=1,
    backupCount=LOG_RETENTION_DAYS,
    encoding="utf-8"
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Console Handler (only for startup/errors)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- File Integrity Checks ---
def ensure_file_exists(filepath, default_content):
    if not os.path.exists(filepath):
        logger.info(f"Creating missing file: {filepath}")
        with open(filepath, 'w') as f:
            json.dump(default_content, f, indent=4)

ensure_file_exists(CONFIG_FILE, {})
ensure_file_exists(USERS_FILE, {})

# --- Runtime Memory ---
bot_config = {}       
user_balances = {}    
sent_cache = set()    
users_dirty = False   

# Initialize Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help') 

# --- Persistence Helpers ---

def load_data():
    """Loads JSON data into RAM."""
    global bot_config, user_balances
    
    # Load Config
    with open(CONFIG_FILE, 'r') as f:
        try: bot_config = json.load(f)
        except json.JSONDecodeError: 
            logger.error("Config file corrupted. Resetting.")
            bot_config = {}
    
    # Load Users
    with open(USERS_FILE, 'r') as f:
        try: user_balances = json.load(f)
        except json.JSONDecodeError: 
            logger.error("User file corrupted. Resetting.")
            user_balances = {}

def save_config():
    """Immediate save for server config changes."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(bot_config, f, indent=4)

def save_users():
    """Flush user RAM data to disk."""
    with open(USERS_FILE, 'w') as f:
        json.dump(user_balances, f, indent=4)

def get_random_monkey_path():
    try:
        if not os.path.exists(GIF_DIR):
            logger.warning(f"GIF Directory {GIF_DIR} not found.")
            return None
        files = os.listdir(GIF_DIR)
        if not files: 
            return None
        # secrets.choice is cryptographically secure
        return os.path.join(GIF_DIR, secrets.choice(files))
    except Exception as e:
        logger.error(f"Error reading GIF directory: {e}")
        return None

# --- Events ---

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    load_data()
    
    if not check_monkey_time.is_running():
        check_monkey_time.start()
    if not autosave_users.is_running():
        autosave_users.start()
        
    await bot.change_presence(activity=discord.Game(name='playing around'))

# --- Background Tasks ---

@tasks.loop(seconds=60)
async def check_monkey_time():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    
    for guild_id_str, settings in bot_config.items():
        try:
            target_tz = pytz.timezone(settings['timezone'])
            local_time = utc_now.astimezone(target_tz)

            if (local_time.weekday() == 4 and 
                local_time.hour == settings['hour'] and 
                local_time.minute == settings['minute']):
                
                today_str = local_time.strftime('%Y-%m-%d')
                cache_key = (guild_id_str, today_str)

                if cache_key in sent_cache: continue

                channel = bot.get_channel(settings['channel_id'])
                file_path = get_random_monkey_path()

                if channel and file_path:
                    try:
                        await channel.send(
                            "@everyone **IT'S FUNKY MONKEY FRIDAY! SEIZE THE DAY!**", 
                            file=discord.File(file_path)
                        )
                        logger.info(f"Alert sent to guild {guild_id_str}")
                        sent_cache.add(cache_key)
                    except Exception as e:
                        logger.error(f"Failed to send to guild {guild_id_str}: {e}")

        except Exception as e:
            logger.error(f"Error processing guild {guild_id_str}: {e}")

@tasks.loop(minutes=5)
async def autosave_users():
    """Saves user data every 5 minutes if changed."""
    global users_dirty
    if users_dirty:
        save_users()
        users_dirty = False

@check_monkey_time.before_loop
@autosave_users.before_loop
async def before_tasks():
    await bot.wait_until_ready()

# --- Custom Help Command ---

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🍌 Funky Monkey Assistance",
        description="You're in the ape zone; here we serve monkeys and (banana) gambling.",
        color=0xFFD700 
    )
    
    embed.add_field(
        name="🎲 **Banana Economy**", 
        value="`!daily` - Claim your free daily bananas\n`!balance` - Check your stash\n`!gamble <amount>` - Double or nothing!", 
        inline=False
    )
    
    embed.add_field(
        name="⚙️ **Configuration (Admins Only)**", 
        value="`!config` - Setup Friday alerts & Timezone\n`!test` - Test the alert immediately", 
        inline=False
    )
    
    embed.set_footer(text="Commands timeout after 60 seconds")
    await ctx.send(embed=embed)

# --- Economy Commands ---

@bot.command()
async def daily(ctx):
    global users_dirty
    user_id = str(ctx.author.id)
    now = datetime.datetime.now().timestamp()
    
    user_data = user_balances.get(user_id, {"balance": 0, "last_daily": 0})
    
    if now - user_data["last_daily"] < 86400:
        next_claim = int(user_data["last_daily"] + 86400)
        await ctx.send(f"🍌 **Hold on!** You can claim again <t:{next_claim}:R>.")
        return

    user_data["balance"] += 100
    user_data["last_daily"] = now
    user_balances[user_id] = user_data
    users_dirty = True
    
    await ctx.send(f"🍌 **Fresh Delivery!** You claimed 100 bananas. Balance: **{user_data['balance']}**")

@bot.command()
async def balance(ctx):
    user_id = str(ctx.author.id)
    bal = user_balances.get(user_id, {}).get("balance", 0)
    await ctx.send(f"💳 **{ctx.author.display_name}**, you have **{bal}** bananas.")

@bot.command()
async def gamble(ctx, amount: str):
    global users_dirty
    user_id = str(ctx.author.id)
    user_data = user_balances.get(user_id, {"balance": 0, "last_daily": 0})
    current_bal = user_data["balance"]

    if amount.lower() == "all":
        bet = current_bal
    else:
        try:
            bet = int(amount)
        except ValueError:
            await ctx.send("Please enter a valid number or 'all'.")
            return

    if bet <= 0:
        await ctx.send("You can't bet nothing, you coward.")
        return
    if bet > current_bal:
        await ctx.send(f"🚫 You only have **{current_bal}** bananas!")
        return

    # Use secrets for cryptographically strong random numbers
    # randbelow(100) returns 0 to 99. 
    # 0-49 = Win (50%), 50-99 = Loss (50%)
    roll = secrets.randbelow(100)
    
    if roll < 50:
        user_data["balance"] += bet
        msg = f"🎰 **WINNER!** You won **{bet}** bananas!"
    else:
        user_data["balance"] -= bet
        msg = f"📉 **OUCH.** You lost **{bet}** bananas."

    user_balances[user_id] = user_data
    users_dirty = True
    
    await ctx.send(f"{msg}\nNew Balance: **{user_data['balance']}**")

# --- Config Commands ---

@bot.command()
@commands.has_permissions(administrator=True)
async def test(ctx):
    file_path = get_random_monkey_path()
    if file_path:
        await ctx.send("**TEST:**", file=discord.File(file_path))
    else:
        await ctx.send("Error: No gifs found.")

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    try:
        await ctx.send('Enter alert hour (0-23):')
        msg_h = await bot.wait_for('message', check=check, timeout=60)
        hour = int(msg_h.content)
        
        await ctx.send('Enter alert minute (0-59):')
        msg_m = await bot.wait_for('message', check=check, timeout=60)
        minute = int(msg_m.content)

        while True:
            await ctx.send('Enter timezone (e.g. US/Eastern) or type **help**:')
            msg_tz = await bot.wait_for('message', check=check, timeout=60)
            if msg_tz.content.lower() == 'help':
                await ctx.send("Enter country code (e.g. US, GB):")
                cc = (await bot.wait_for('message', check=check, timeout=60)).content.upper()
                if cc in pytz.country_timezones:
                    await ctx.send(f"Timezones:\n`" + "\n".join(pytz.country_timezones[cc]) + "`")
            else:
                pytz.timezone(msg_tz.content)
                bot_config[str(ctx.guild.id)] = {
                    "channel_id": ctx.channel.id, "hour": hour, "minute": minute, "timezone": msg_tz.content
                }
                save_config()
                await ctx.send("✅ Configuration saved.")
                break
    except Exception as e:
        await ctx.send(f"Setup cancelled: {e}")

# --- Main Execution with Safe Shutdown ---
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"Bot crashed with error: {e}")
    finally:
        # Force a save when the bot shuts down (Ctrl+C or Error)
        if users_dirty:
            save_users()
            logger.info("Shutdown: User data saved to disk.")
        else:
            logger.info("Shutdown: No user data changes to save.")