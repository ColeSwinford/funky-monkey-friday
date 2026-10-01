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
        GIF_DIR = settings["GifDirectory"]
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

# --- Token Loading ---
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN and "Token" in settings:
    TOKEN = settings["Token"]
    logger.warning("Loading Token from JSON. Move to Environment Variables for security.")

if not TOKEN:
    logger.critical("No 'DISCORD_TOKEN' found in environment variables. Terminating.")
    sys.exit(1)

# --- Dependency Check ---
if not shutil.which("ffmpeg"):
    logger.critical("FFmpeg not found. Voice features will fail. Install FFmpeg to PATH.")

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
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# --- Persistence Helpers ---

def load_data():
    """Loads JSON data into RAM."""
    global bot_config, user_balances
    
    with open(CONFIG_FILE, 'r') as f:
        try:
            bot_config = json.load(f)
        except json.JSONDecodeError:
            logger.error("Config file corrupted. Resetting.")
            bot_config = {}
    
    with open(USERS_FILE, 'r') as f:
        try:
            user_balances = json.load(f)
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
        if not os.path.exists(GIF_DIR):
            return None
        files = [f for f in os.listdir(GIF_DIR) if os.path.isfile(os.path.join(GIF_DIR, f))]
        if not files:
            return None
        return os.path.join(GIF_DIR, secrets.choice(files))
    except Exception as e:
        logger.error(f"Error reading GIF directory: {e}")
        return None

def get_random_sound_path():
    """Gets a random MP3/WAV from the configured directory."""
    try:
        if not os.path.exists(SOUND_DIR):
            return None
        files = [f for f in os.listdir(SOUND_DIR) if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
        if not files:
            return None
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
    if not random_monkey_noises.is_running():
        random_monkey_noises.start()
        
    await bot.change_presence(activity=discord.Game(name='playing around'))

# --- Background Tasks ---

@tasks.loop(seconds=60)
async def check_monkey_time():
    """Friday Text Alert Logic"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    
    for guild_id_str, cfg in bot_config.items():
        try:
            if 'timezone' not in cfg or 'hour' not in cfg or 'minute' not in cfg or 'channel_id' not in cfg:
                continue

            target_tz = pytz.timezone(cfg['timezone'])
            local_time = utc_now.astimezone(target_tz)

            if (local_time.weekday() == 4 and 
                local_time.hour == cfg['hour'] and 
                local_time.minute == cfg['minute']):
                
                today_str = local_time.strftime('%Y-%m-%d')
                cache_key = (guild_id_str, today_str)

                if cache_key in sent_cache:
                    continue

                channel = bot.get_channel(cfg['channel_id'])
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
                        logger.error(f"Failed to send alert to guild {guild_id_str}: {e}")

        except Exception as e:
            logger.error(f"Error processing text alert for guild {guild_id_str}: {e}")

@tasks.loop(hours=1)
async def random_monkey_noises():
    """Voice Channel Ambush Logic - checks once per hour"""
    for guild_id_str, cfg in bot_config.items():
        try:
            vc_id = cfg.get("voice_channel_id")
            mode = cfg.get("voice_mode", "off")
            
            if not vc_id or mode == "off":
                continue

            # Friday check
            if mode == "friday":
                tz_str = cfg.get("timezone", "UTC")
                local_now = datetime.datetime.now(pytz.timezone(tz_str))
                if local_now.weekday() != 4:
                    continue

            # Target channel validation
            voice_channel = bot.get_channel(vc_id)
            if not voice_channel:
                continue

            # Skip if the channel has no active human members
            active_listeners = [m for m in voice_channel.members if not m.bot]
            if not active_listeners:
                continue

            # Default: 10% chance per hour
            chance = cfg.get("voice_chance", 10)
            if secrets.randbelow(100) >= chance:
                continue

            sound_file = get_random_sound_path()
            if not sound_file:
                logger.warning(f"No sound files found for ambush in guild {guild_id_str}")
                continue

            logger.info(f"Ambush triggered for guild {guild_id_str} in channel '{voice_channel.name}'")

            try:
                vc = await voice_channel.connect()
            except discord.ClientException:
                logger.warning(f"Already connected to voice in guild {guild_id_str}, skipping.")
                continue
            except Exception as e:
                logger.error(f"Voice connection failed for guild {guild_id_str}: {e}")
                continue

            playback_done = asyncio.Event()

            def after_playing(error):
                if error:
                    logger.error(f"Playback error in guild {guild_id_str}: {error}")
                bot.loop.call_soon_threadsafe(playback_done.set)

            try:
                audio_source = discord.FFmpegPCMAudio(sound_file)
                vc.play(audio_source, after=after_playing)
                await playback_done.wait()
            except Exception as e:
                logger.error(f"Failed to play audio in guild {guild_id_str}: {e}")
            finally:
                if vc.is_connected():
                    await vc.disconnect()

        except Exception as e:
            logger.error(f"Error in monkey noises task for guild {guild_id_str}: {e}")

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
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("You must be in a voice channel to test this.")
        return

    sound_file = get_random_sound_path()
    if not sound_file:
        await ctx.send("Error: No sound files found in directory.")
        return

    try:
        vc = await ctx.author.voice.channel.connect()
    except discord.ClientException:
        await ctx.send("Already connected to a voice channel.")
        return
    except Exception as e:
        await ctx.send(f"Voice connection failed: {e}")
        return

    playback_done = asyncio.Event()

    def after_playing(error):
        if error:
            logger.error(f"Manual playback error: {error}")
        bot.loop.call_soon_threadsafe(playback_done.set)

    try:
        vc.play(discord.FFmpegPCMAudio(sound_file), after=after_playing)
        await playback_done.wait()
    except Exception as e:
        await ctx.send(f"Playback failed: {e}")
    finally:
        if vc.is_connected():
            await vc.disconnect()

@bot.command()
@commands.has_permissions(administrator=True)
async def voicecfg(ctx):
    """Sets up the voice ambush feature."""
    def check(m): 
        return m.author == ctx.author and m.channel == ctx.channel

    guild_id = str(ctx.guild.id)
    
    if guild_id not in bot_config:
        bot_config[guild_id] = {}

    try:
        # 1. Get Channel ID
        await ctx.send("🔊 **Voice Setup**\nPaste the **Voice Channel ID** to haunt (or type 'cancel'):")
        msg_id = await bot.wait_for('message', check=check, timeout=60)
        if msg_id.content.lower() == 'cancel': 
            return
        
        try:
            vc_id = int(msg_id.content)
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

        # 3. Get Trigger Chance
        await ctx.send("🎲 **Set Chance**:\nEnter trigger percentage per hour (1-100, default is 10):")
        msg_chance = await bot.wait_for('message', check=check, timeout=60)
        try:
            chance = int(msg_chance.content)
            if not 1 <= chance <= 100:
                chance = 10
        except ValueError:
            chance = 10

        # 4. Save
        bot_config[guild_id]["voice_channel_id"] = vc_id
        bot_config[guild_id]["voice_mode"] = mode
        bot_config[guild_id]["voice_chance"] = chance
        save_config()
        
        await ctx.send(
            f"✅ **Saved!**\nTarget: <#{vc_id}>\nMode: `{mode}`\nChance: {chance}% per hour (only triggers when users are present)."
        )

    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out.")

@bot.command()
@commands.has_permissions(administrator=True)
async def config(ctx):
    """Configures the scheduled text alerts."""
    def check(m): 
        return m.author == ctx.author and m.channel == ctx.channel

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
        pytz.timezone(msg_tz.content)

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