import discord
from discord.ext import commands, tasks
import os
import secrets
import datetime
import json
import pytz
import asyncio
import sys
import logging
import shutil
from logging.handlers import TimedRotatingFileHandler

# --- Initialization & Configuration ---

try:
    with open("appsettings.json", "r") as f:
        settings = json.load(f)
        TOKEN = settings["Token"]
        GIF_DIR = settings["GifDirectory"]
        # Directory for voice alert audio files
        SOUND_DIR = settings.get("SoundDirectory", "./sounds") 
        CONFIG_FILE = settings["ConfigFile"]
        USERS_FILE = settings["UsersFile"]
        LOG_RETENTION_DAYS = settings.get("LogRetentionDays", 7)
except FileNotFoundError:
    print("CRITICAL: 'appsettings.json' not found. Terminating.")
    sys.exit(1)
except KeyError as e:
    print(f"CRITICAL: Missing setting {e} in 'appsettings.json'. Terminating.")
    sys.exit(1)

# --- Dependency Check ---
if not shutil.which("ffmpeg"):
    print("CRITICAL: FFmpeg not found. Voice features will fail. Install FFmpeg to path.")
    # Execution continues; voice commands will raise errors if invoked

# --- Logging Setup ---
if not os.path.exists("logs"):
    os.makedirs("logs")

logger = logging.getLogger("FunkyMonkey")
logger.setLevel(logging.INFO)

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

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# --- File Integrity ---
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

# --- Bot Initialization ---
intents = discord.Intents.default()
intents.message_content = True
# Enable voice intent to detect user presence in channels
intents.voice_states = True 
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help') 

# --- Persistence Helpers ---

def load_data():
    """Loads JSON data into RAM."""
    global bot_config, user_balances
    
    with open(CONFIG_FILE, 'r') as f:
        try: bot_config = json.load(f)
        except json.JSONDecodeError: 
            logger.error("Config file corrupted. Resetting.")
            bot_config = {}
    
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
    """Gets a random GIF from the configured directory."""
    try:
        if not os.path.exists(GIF_DIR): return None
        files = [f for f in os.listdir(GIF_DIR) if os.path.isfile(os.path.join(GIF_DIR, f))]
        if not files: return None
        return os.path.join(GIF_DIR, secrets.choice(files))
    except Exception as e:
        logger.error(f"Error reading GIF directory: {e}")
        return None

def get_random_sound_path():
    """Gets a random MP3/WAV from the configured directory."""
    try:
        if not os.path.exists(SOUND_DIR): return None
        files = [f for f in os.listdir(SOUND_DIR) if f.endswith(('.mp3', '.wav'))]
        if not files: return None
        return os.path.join(SOUND_DIR, secrets.choice(files))
    except Exception as e:
        logger.error(f"Error reading Sound directory: {e}")
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
    
    # Start voice activity task
    if not random_monkey_noises.is_running():
        random_monkey_noises.start()
        
    await bot.change_presence(activity=discord.Game(name='playing around'))

# --- Background Tasks ---

@tasks.loop(seconds=60)
async def check_monkey_time():
    """Friday Text Alert Logic"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    
    for guild_id_str, settings in bot_config.items():
        try:
            # Check if text config exists
            if 'timezone' not in settings or 'hour' not in settings:
                continue

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

@tasks.loop(hours=1)
async def random_monkey_noises():
    """Voice Channel Ambush Logic (5% chance per hour)"""
    for guild_id_str, settings in bot_config.items():
        try:
            # 1. Check if voice is configured
            vc_id = settings.get("voice_channel_id")
            mode = settings.get("voice_mode", "off") # off, always, friday
            
            if not vc_id or mode == "off":
                continue

            # 2. Check "Friday Only" constraint
            if mode == "friday":
                # Uses the text timezone if set, else UTC
                tz_str = settings.get("timezone", "UTC")
                local_now = datetime.datetime.now(pytz.timezone(tz_str))
                if local_now.weekday() != 4: # 4 is Friday
                    continue

            # 3. Random Chance Execution (5%)
            # secrets.randbelow(100) returns 0-99
            if secrets.randbelow(100) < 5:
                voice_channel = bot.get_channel(vc_id)
                sound_file = get_random_sound_path()
                
                if voice_channel and sound_file:
                    logger.info(f"🎲 Ambush triggered for {guild_id_str}")
                    
                    # Connect
                    try:
                        vc = await voice_channel.connect()
                    except discord.ClientException:
                        logger.warning(f"Already in voice for {guild_id_str}, skipping.")
                        continue
                    except Exception as e:
                        logger.error(f"Voice connection failed: {e}")
                        continue

                    # Play Audio
                    try:
                        vc.play(discord.FFmpegPCMAudio(sound_file))
                        while vc.is_playing():
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Audio playback failed: {e}")
                    finally:
                        await vc.disconnect()
        
        except Exception as e:
            logger.error(f"Error in monkey noises task for {guild_id_str}: {e}")

@tasks.loop(minutes=5)
async def autosave_users():
    global users_dirty
    if users_dirty:
        save_users()
        users_dirty = False

@check_monkey_time.before_loop
@autosave_users.before_loop
@random_monkey_noises.before_loop
async def before_tasks():
    await bot.wait_until_ready()

# --- Custom Help Command ---

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🍌 Funky Monkey Assistance",
        description="You're in the ape zone.",
        color=0xFFD700 
    )
    
    embed.add_field(
        name="🎲 **Economy**", 
        value="`!daily` - Free bananas\n`!balance` - Check stash\n`!gamble <amt>` - Double or nothing", 
        inline=False
    )
    
    embed.add_field(
        name="⚙️ **Config (Admin)**", 
        value="`!config` - Setup Text Alerts\n`!voicecfg` - Setup Voice Ambush\n`!test` - Test Text\n`!testvoice` - Test Voice", 
        inline=False
    )
    
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
        await ctx.send("You can't bet nothing.")
        return
    if bet > current_bal:
        await ctx.send(f"🚫 You only have **{current_bal}** bananas!")
        return

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
async def testvoice(ctx):
    """Manually triggers the voice sound in the user's channel."""
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to test this.")
        return

    sound_file = get_random_sound_path()
    if not sound_file:
        await ctx.send("Error: No sound files found in directory.")
        return

    vc = await ctx.author.voice.channel.connect()
    try:
        vc.play(discord.FFmpegPCMAudio(sound_file))
        while vc.is_playing():
            await asyncio.sleep(1)
    finally:
        await vc.disconnect()

@bot.command()
@commands.has_permissions(administrator=True)
async def voicecfg(ctx):
    """Sets up the voice ambush feature."""
    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    guild_id = str(ctx.guild.id)
    
    # Initialize config if not exists
    if guild_id not in bot_config:
        bot_config[guild_id] = {}

    try:
        # 1. Get Channel ID
        await ctx.send("🔊 **Voice Setup**\nPaste the **Voice Channel ID** to haunt (or type 'cancel'):")
        msg_id = await bot.wait_for('message', check=check, timeout=60)
        if msg_id.content.lower() == 'cancel': return
        
        try:
            vc_id = int(msg_id.content)
            # Verify channel exists
            if not bot.get_channel(vc_id):
                await ctx.send("❌ Channel not found.")
                return
        except ValueError:
            await ctx.send("❌ Invalid ID.")
            return

        # 2. Get Mode
        await ctx.send("🗓️ **Select Mode**:\nType `friday`, `always`, or `off`:")
        msg_mode = await bot.wait_for('message', check=check, timeout=60)
        mode = msg_mode.content.lower()
        if mode not in ['friday', 'always', 'off']:
            await ctx.send("❌ Invalid mode.")
            return

        # 3. Save
        bot_config[guild_id]["voice_channel_id"] = vc_id
        bot_config[guild_id]["voice_mode"] = mode
        save_config()
        
        await ctx.send(f"✅ **Saved!**\nTarget: <#{vc_id}>\nMode: `{mode}`\nChance: 5% per hour.")

    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out.")

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    """Configures the scheduled text alerts."""
    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    guild_id = str(ctx.guild.id)
    if guild_id not in bot_config:
        bot_config[guild_id] = {}

    try:
        await ctx.send('Enter alert hour (0-23):')
        msg_h = await bot.wait_for('message', check=check, timeout=60)
        hour = int(msg_h.content)
        
        await ctx.send('Enter alert minute (0-59):')
        msg_m = await bot.wait_for('message', check=check, timeout=60)
        minute = int(msg_m.content)

        await ctx.send('Enter timezone (e.g. US/Eastern):')
        msg_tz = await bot.wait_for('message', check=check, timeout=60)
        pytz.timezone(msg_tz.content) # Validate

        # Update specific keys instead of overwriting the whole dict
        bot_config[guild_id]["channel_id"] = ctx.channel.id
        bot_config[guild_id]["hour"] = hour
        bot_config[guild_id]["minute"] = minute
        bot_config[guild_id]["timezone"] = msg_tz.content
        
        save_config()
        await ctx.send("✅ Text Configuration saved.")

    except Exception as e:
        await ctx.send(f"Setup cancelled: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"Bot crashed with error: {e}")
    finally:
        if users_dirty:
            save_users()
            logger.info("Shutdown: User data saved.")