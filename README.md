# Funky-Monkey-Friday-Bot

An open-source, configurable Discord bot that alerts your server when it's Funky Monkey Friday!
<sub>Banana gambling included.</sub>

Add it to your server here! https://discord.com/oauth2/authorize?client_id=927716084944076810&permissions=248832&integration_type=0&scope=bot

![Funkey Monkey Friday Bot](https://user-images.githubusercontent.com/19520329/148521703-a8c1fdb6-7352-4579-aca1-e60f80ffe477.png)  

## Commands

### Banana Economy (Everyone)
* `!daily` - Claim your free daily 100 bananas (24h cooldown).
* `!balance` - Check your current stash.
* `!gamble <amount>` - Bet bananas on a 50/50 coin flip. Type `all` to go all in.

### Configuration (Admins Only)
* `!config` - Interactive wizard to set the Friday alert time and timezone.
    * *Type "help" during the timezone step to search by country code.*
* `!test` - Trigger an immediate test alert (verifies permissions and file access).

*Commands timeout after 60 seconds.*

## Setup & Requirements

1.  **Environment:** Requires Docker
2.  **Configuration:**
    * Rename the included `template-appsettings.json` to `appsettings.json`.
    * Open the file and paste your Bot Token inside.
3.  **Permissions:** The bot requires the **Message Content Intent** (enabled in the Discord Developer Portal). For the role itself, grant:
    * `View Channels`
    * `Send Messages` & `Read Message History`
    * `Embed Links` & `Attach Files`
    * `Mention @everyone, @here, and All Roles`

    Permissions Integer: `248832`

## Deploy via SCP (One-Liner)

Replace `target` with your SSH alias or `user@ip`.

```bash
scp -r . target:~/FunkyMonkeyFriday; ssh target "cd FunkyMonkeyFriday && docker compose up -d --build"
```

## Privacy & Legal
- **Data Storage:** This bot stores server configurations (timezones) and user economy balances locally in JSON files. No messages are recorded.
- **Disclaimer:** I do not own the images or GIFs used by this bot.
