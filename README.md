# Funky-Monkey-Friday

An open-source, configurable Discord bot that alerts your server when it's Funky Monkey Friday!

<sub>Now with 100% more screaming.</sub>

Add it to your server here! [here](https://discord.com/oauth2/authorize?client_id=927716084944076810&permissions=3394560&integration_type=0&scope=bot)

![Funkey Monkey Friday Bot](https://user-images.githubusercontent.com/19520329/148521703-a8c1fdb6-7352-4579-aca1-e60f80ffe477.png)  

## Features

* **Friday Alerts:** Posts a random monkey GIF to a specific channel at a specific time (Timezone aware).
* **Banana Economy:** A complete gambling system where users can collect and bet fake currency.
* **Voice Ambush:** The bot can randomly join a voice channel (5% chance/hour) to play a sound effect and leave immediately.

## Commands

### 🍌 Banana Economy (Everyone)

* `!daily` - Claim your free daily 100 bananas (24h cooldown).
* `!balance` - Check your current stash.
* `!gamble <amount>` - Bet bananas on a 50/50 coin flip. Type `all` to go all in.

### Configuration (Admins Only)

* `!config` - Interactive wizard to set the Friday **text** alert time and timezone.
    * *Type "help" during the timezone step to search by country code.*
* `!voicecfg` - Setup the **voice** ambush (Target Channel + Mode).
    * **Modes:** `friday` (Friday only), `always` (Every day), `off` (Disable).
* `!test` - Trigger an immediate text alert (verifies permissions and GIFs).
* `!testvoice` - Trigger an immediate voice alert (verifies audio and FFmpeg).

*Commands timeout after 60 seconds.*

## Setup & Requirements

1. **Environment:** Requires Docker
2. **Permissions:** The bot requires the **Message Content Intent** (enabled in the Discord Developer Portal). For the role itself, grant:
    * `View Channels`
    * `Send Messages` & `Read Message History`
    * `Embed Links` & `Attach Files`
    * `Mention @everyone, @here, and All Roles`
    * `Connect` & `Speak`

    Permissions Integer: `3394560`

## Deploy

Execute this script to perform a first install or in place upgrade and start the container.

*Replace `YOUR_TOKEN` with your actual Discord Bot Token.*

```bash
# 1. Clone source repo regardless if it exists already or not
git clone https://github.com/ColeSwinford/Python--Funky-Monkey-Friday-Bot.git FunkyMonkeyFriday 2>/dev/null || true

# 2. Enter folder, Force-Sync code (Fixes conflicts), and Start
cd FunkyMonkeyFriday && \
git fetch --all && \
git reset --hard origin/main && \
docker rm -f funky_monkey_friday 2>/dev/null || true && \
DISCORD_TOKEN=YOUR_TOKEN docker compose up -d --build
```

**Note:** this will take some time, especially on a pi, as resources like ffmpeg are huge

## Privacy & Legal

- **Data Storage:** This bot stores server configurations (timezones) and user economy balances locally in JSON files.
- **Disclaimer:** I do not own the images or GIFs used by this bot.
