import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
from gtts import gTTS
from gtts import lang
import os
import math
import requests
# import signal
import atexit

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.messages = True
intents.members = True

# Set up the bot
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.run_loop = None
        self.queue = {}
        self.default_settings = {
            "language": "en",
            "accent": "com",
            "autoread": False,
            "timeout": 300
        }
        self.members_settings = {}
        self.servers_settings = {}
        self.voice_channel_timeouts = {}
        self.active_timeouts = {}

    async def setup_hook(self):
        print(f"Setup complete for {self.user}")

bot = Bot()

# Read the bot token from external file
with open('../token.txt', 'r') as file:
    TOKEN = file.read().strip()
    # print(TOKEN)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

    for guild in bot.guilds:
        bot.queue[guild.id] = {
            "queue": asyncio.Queue(),
            "task": bot.loop.create_task(process_queue(guild))
        }
        bot.loop.create_task(check_empty_channel(guild))

    """ bot.queue_task = bot.loop.create_task(process_queue())
    bot.loop.create_task(check_empty_channel())  # Start the empty channel check """

    # Print out all registered commands
    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(f"- /{command.name}")

async def process_queue(guild: discord.Guild):
    while True:
        print(f"{guild.name}: Waiting for the next message in the queue for...")
        message, text, voice_channel = await bot.queue[guild.id]["queue"].get()
        user_id = message.author.id
        print(f"{guild.name}: Processing message: {text}")

        # Convert the text to speech using gTTS
        
        # guild = message.guild
        guild_id = guild.id

        if user_id in bot.members_settings and "language" in bot.members_settings[user_id]:
            language = bot.members_settings[user_id]["language"]
        elif guild_id in bot.servers_settings and "language" in bot.servers_settings[guild_id]:
            language = bot.servers_settings[guild_id]["language"]
        else:
            language = bot.default_settings["language"]

        if user_id in bot.members_settings and "accent" in bot.members_settings[user_id]:
            accent = bot.members_settings[user_id]["accent"]
        elif guild_id in bot.servers_settings and "accent" in bot.servers_settings[guild_id]:
            accent = bot.servers_settings[guild_id]["accent"]
        else:
            accent = bot.default_settings["accent"]

        try:
            requests.get(f"https://translate.google.{accent}")
        except requests.ConnectionError:
            await message.reply(f"I cannot read your message because `https://translate.google.`**`{accent}`** is currently down. Please run `/setaccent` and specify another top-level domain or try again later.\n\nOtherwise, type `/stop`, and I will stop reading your messages.")
            continue

        else:
            tts = gTTS(text=text, lang=language, tld=accent)
            tts.save(f"voice_files/{guild_id}-tts.mp3")
            
            voice_client = guild.voice_client

            if voice_client and voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)
            elif not voice_client:
                await voice_channel.connect()

            voice_client = guild.voice_client

            if voice_client and voice_client.is_connected():
                def after_playing(error):
                    if error:
                        print(f"{guild.name}: Error occurred during playback: {error}")

                    # Indicate that the current task is done
                    bot.loop.call_soon_threadsafe(bot.tts_queue.task_done)

                    # Clean up the audio file
                    try:
                        os.remove(f"voice_files/{guild_id}-tts.mp3")
                        print(f"{guild.name}: Cleaned up the TTS file")
                    except OSError as remove_error:
                        print(f"{guild.name}: Error cleaning up the TTS file:\n\t{remove_error}")

                # Play the audio file in the voice channel
                print(f"{guild.name}: Playing the TTS message in {message.channel.name}...")
                voice_client.play(discord.FFmpegPCMAudio(f"voice_files/{guild_id}-tts.mp3", executable='bot-env/ffmpeg/bin/ffmpeg'), after=after_playing)
                # ffmpeg currently uses version 7.1 on windows and 7.0.2 on linux

                # Wait until the current message is finished playing
                while voice_client.is_playing():
                    await asyncio.sleep(1)
                print(f"{guild.name}: Audio finished playing")


                if guild_id in bot.active_timeouts:
                    bot.active_timeouts[guild_id].cancel()

                bot.active_timeouts[guild_id] = asyncio.create_task(leave_after_timeout(guild))

                bot.active_timeouts[guild_id]

            else:
                print(f"{guild.name}: Voice client is not connected; task done")
                bot.tts_queue.task_done()

# region When a message is sent
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user or not message.guild:
        return

    # Remove emote IDs, leaving only emote names (e.g., :emote_name:) 
    # This replaces <emote_name:123456789> with :emote_name:
    message_content = re.sub(r'<:(\w+):\d+>', r':\1:', message.content)

    # Remove links, replacing it with an empty string
    message_content = re.sub(r'(https?://\S+|www\.\S+)', "", message_content)

    # Remove long numbers (e.g., numbers longer than 8 digits)
    # Replaces it with an empty string
    message_content = re.sub(r'\d{8,}', "", message_content)
    
    if message_content == "" or re.match(r'^[\s\t\n]+$', message_content, re.MULTILINE) != None:
        print(f"{message.guild.name}: Message contains no text, skipping.")
        return
    
    message_content = f"{message.author.display_name} says, " + message_content

    # Check if there is a voice channel with the same name as the text channel
    text_channel_name = message.channel.name
    voice_channel = discord.utils.get(message.guild.voice_channels, name=text_channel_name)

    if voice_channel:
        # Add the filtered message content to the queue
        await bot.queue[message.guild.id]["queue"].put((message, message_content, voice_channel))
        print(f"{message.guild.name}: Added message to queue: {message_content}")

    await bot.process_commands(message)

# endregion

# region Leave voice channel when empty
# Check if the bot is alone in the voice channel and disconnect if empty
async def check_empty_channel(guild: discord.Guild):
    """Periodically check if the bot is alone in the voice channel and disconnect."""
    while True:
        if guild.voice_client:
            voice_channel = guild.voice_client.channel
            if len(voice_channel.members) == 1:
                await guild.voice_client.disconnect()
                print(f"{guild.name}: Disconnected from voice channel as it was empty.")
                del bot.active_timeouts[guild.id]
        await asyncio.sleep(60)  # Check every 60 seconds

# endregion

# region leave after timeout
async def leave_after_timeout(guild: discord.Guild):
    """Disconnect from the voice channel after the timeout has passed."""

    print(f'Timeout set for {guild.name}.')
    try:
        timeout = bot.default_settings["timeout"]
        if guild.id in bot.voice_channel_timeouts:
            timeout = bot.voice_channel_timeouts[guild.id]
        await asyncio.sleep(timeout)
        
        await guild.voice_client.disconnect()
        print(f'Disconnected from {guild.name} due to timeout.')
    except asyncio.CancelledError:
        print(f'Timeout cancelled for {guild.name}')

# endregion

# region Commands
def to_lower(argument):
    if not argument or argument == "":
        return None
    return argument.lower()

# def same_or_none(argument):
#     if not argument or argument == "":
#         return None
#     return argument

# @bot.hybrid_group(name="User settings")

# region settings

# region members
# def member_commands(argument: str):
#     if not argument or argument == "":
#         return {
#             "language": None,
#             "accent": None,
#             "autoread": None
#         }

#     args = argument.lower().split()

#     return {
#         "language": args[0],
#         "accent": args[1],
#         "autoread": args[2]
#     }


# @bot.hybrid_command()
# @app_commands.describe(language="The IETF language tag (eg. 'en' or 'zh-TW') of the language you will write messages in.", accent="A localized top-level domain (as in www.google.<accent>) the accent will be read with.", autoread="Whether your messages are automatically read when you join a voice channel.")
# async def settings(ctx: commands.Context, language: to_lower = None, accent: to_lower = None, autoread: to_lower = None):
#     """Set up your personal settings for Voicely Text."""

#     success_message = []

#     error_message = []

#     settings = {}

#     if language:
#         langs = lang.tts_langs()

#         if language in langs:
#             settings["language"] = language
#             success_message.append(f"Your language has been set to {langs[key]}.")
#         else:
#             language_error = f"`{language}` is not a valid IETF language tag! Supported tags include:"
#             keys = list(langs.keys())
#             for key in keys:
#                 language_error += f"\n- `{key}` *({langs[key]})*"
                
#             error_message.append(language_error)
#     else:
#         success_message.append("Your language has been set to the server default.")

#     if accent:
#         settings["accent"] = accent
#         success_message.append(f"Your accent's top-level domain has been set to {accent}.\n**Please note:** there is currently no way to check whether the top-level domain is valid!")
#     else:
#         success_message.append("Your accent's top-level domain has been set to the server default.")
    


#     if autoread:
#         match autoread:
#             case "true":
#                 settings["autoread"] = True
#                 success_message.append(f"Autoread has been **enabled**.\nI will automatically read all of your messages when you join a voice channel without having to use `/start`.\nThis will be disabled when you leave the voice channel.")
#             case "false":
#                 settings["autoread"] = False
                    
#                 success_message.append(f"Autoread has been **disabled**.\nYou will need to type `/start` for me to start reading your messages.\nAlternatively, you can type `/tts [your message]` for me to read a single message.")
#             case _:
#                 error_message.append(f"`enabled` must be set to either `true` or `false`.")
#     else:
#         success_message.append("Autoread has been set to the server default.")

#     if len(error_message) != 0:
#         final_error = "\n\n".join(error_message)
#         print(f"{ctx.author.name} used `/settings` but received {len(error_message)} errors.")
#         await ctx.send(final_error, ephemeral=True)
#     elif not language and not accent and not autoread:
#         print(f"{ctx.author.name} used `/settings` but did not provide any values.")
#         await ctx.send("You must provide at least one value!", ephemeral=True)
#     else:
#         final_message = "\n\n".join(success_message)
#         bot.members_settings[ctx.author.id] = {}
#         print(f"{ctx.author.name}'s settings were set to: {settings}")
#         await ctx.send(final_message, ephemeral=True)

        
# endregion

# region servers
# endregion

# endregion

# region autoread

# region members
@bot.hybrid_command()
@app_commands.describe(enabled="'True' or 'False'")
async def autoread(ctx: commands.Context, enabled: to_lower):
    """Set whether your messages are automatically read when you join a voice channel."""

    match enabled:
        case "true":
            enabled_bool = True
            confirm_message = f"Autoread has been **enabled**.\n\nI will automatically read all of your messages when you join a voice channel without having to use `/start`.\n\nThis will be disabled when you leave the voice channel."
        case "false":
            enabled_bool = False
            confirm_message = f"Autoread has been **disabled**.\n\nYou will need to type `/start` for me to start reading your messages.\n\nAlternatively, you can type `/tts [your message]` for me to read a single message."
        case "reset":
            if ctx.author.id in bot.members_settings and "autoread" in bot.members_settings[ctx.author.id]:
                del bot.members_settings[ctx.author.id]["autoread"]
            
            if ctx.guild.id in bot.servers_settings and "autoread" in bot.servers_settings[ctx.guild.id]:
                default = bot.servers_settings[ctx.guild.id]["autoread"]
            else:
                default = bot.default_settings["autoread"]
            await ctx.send(f"Autoread has been **reset** to the server default: `{default}`", ephemeral=True)
            return
        case _:
            await ctx.send(f"`enabled` must be set to either `True` or `False`.", ephemeral=True)
            return

    if ctx.author.id in bot.members_settings:
        bot.members_settings[ctx.author.id]["autoread"] = enabled_bool
    else:
        bot.members_settings[ctx.author.id] = {"autoread": enabled_bool}
    await ctx.send(confirm_message, ephemeral=True)

# endregion

# region servers
""" @bot.hybrid_command()
async def serversautoread() """
# endregion

# endregion

# region Languages and accents

# region Languages
""" class Languages(discord.ui.Select):
    def __init__(self):
        options = []
        langs = lang.tts_langs()
        for thisLang in langs:
            options.append(discord.SelectOption(label=thisLang, value=thisLang, description=langs[thisLang]))
        
        super().__init__(placeholder="Select a language", max_values=1, min_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(content=f"Your choice is {self.values[0]}! ", ephemeral=True) """

class LanguagesView(discord.ui.View):
    langs = lang.tts_langs()
    keys = list(langs.keys())
    
    options = []
    
    select_count = math.ceil(len(langs) / 25)

    for x in range(select_count):
        options.append([])

        new_keys = keys[(x * 25):min((x * 25) + 25, len(keys))]

        for y in range(len(new_keys)):
            key = new_keys[y]
            options[x].append(discord.SelectOption(label=langs[key], value=key, description=key))

    
    async def select_language(self, interaction: discord.Interaction, select: discord.ui.Select):
        langs = lang.tts_langs()
        user_id = interaction.user.id
        if user_id in bot.members_settings:
            bot.members_settings[user_id]["language"] = select.values[0]
        else:
            bot.members_settings[user_id] = {"language": select.values[0]}
        
        select.disabled = True

        """ for component in interaction.message.components:
            component.disabled = True """
        return await interaction.response.send_message(f"Your language has been set to **{langs[select.values[0]]}**.", ephemeral=True)

    @discord.ui.select(placeholder="Select a language (1)", options=options[0])
    async def select_language_1(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_language(interaction, select)
    
    @discord.ui.select(placeholder="Select a language (2)", options=options[1])
    async def select_language_2(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_language(interaction, select)
    
    @discord.ui.select(placeholder="Select a language (3)", options=options[2])
    async def select_language_3(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_language(interaction, select)


@bot.hybrid_command()
async def setlanguage(ctx: commands.Context, languagetag: str = None):
    """Set the language you want me to read your messages in."""

    if languagetag:
        langs = lang.tts_langs()

        if languagetag in langs:
            if ctx.author.id in bot.members_settings:
                bot.members_settings[ctx.author.id]["language"] = languagetag
            else:
                bot.members_settings[ctx.author.id] = {"language": languagetag}
            
            await ctx.send(f"Your language has been set to **{langs[languagetag]}**.", ephemeral=True)
        else:
            language_error = f"`{languagetag}` is not a valid IETF language tag! Supported tags include:"
            keys = list(langs.keys())
            for key in keys:
                language_error += f"\n- `{key}` - *{langs[key]}*"

            language_error += "\nRerun `/setlanguage` without arguments to generate dropdowns to choose from."
            
            await ctx.send(language_error, ephemeral=True)
    else:
        embed = discord.Embed(title="Set your preferred language", description='Choose from the dropdown below to have me read your messages in that language.')

        await ctx.send(embed=embed, view=LanguagesView(), ephemeral=True)

# endregion

# region Command for accents

accent_embed = discord.Embed(title="Set your preferred accent", description='Choose from the list of top-level domains below, and I will read your messages as though I am from a region that uses that domain.')

async def select_accent(self, interaction: discord.Interaction, select: discord.ui.Select):
    user_id = interaction.user.id
    if user_id in bot.members_settings:
        bot.members_settings[user_id]["accent"] = select.values[0]
    else:
        bot.members_settings[user_id] = {"accent": select.values[0]}

    return await interaction.response.send_message(f"Your accent's **top-level domain** has been set to `{select.values[0]}`.", ephemeral=True)

def get_tlds():
    response = requests.get("https://www.google.com/supported_domains")

    if response.status_code == 200:
        string = response.text.strip('.google.')
        tld_list = string.split('\n.google.')

        options = []
        
        select_count = math.ceil(len(tld_list) / 25)

        print(select_count)

        for x in range(select_count):
            options.append([])

            new_list = tld_list[(x * 25):min((x * 25) + 25, len(tld_list))]

            for y in range(len(new_list)):
                options[x].append(discord.SelectOption(label=new_list[y], value=new_list[y], description=f"translate.google.{new_list[y]}"))
        return options
    else:
        print("\nError: You should restart the bot because I was unable to fetch https://www.google.com/supported_domains for accents!")
        return []

tld_list = get_tlds()

class AccentsView1(discord.ui.View):
    @discord.ui.select(placeholder="Select a top-level domain (1)", options=tld_list[0])
    async def select_accent_1(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (2)", options=tld_list[1])
    async def select_accent_2(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (3)", options=tld_list[2])
    async def select_accent_3(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (4)", options=tld_list[3])
    async def select_accent_4(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.button(label="Next page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=accent_embed, view=AccentsView2(), ephemeral=True)

class AccentsView2(discord.ui.View):        
    @discord.ui.select(placeholder="Select a top-level domain (5)", options=tld_list[4])
    async def select_accent_5(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (6)", options=tld_list[5])
    async def select_accent_6(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (7)", options=tld_list[6])
    async def select_accent_7(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.select(placeholder="Select a top-level domain (8)", options=tld_list[7])
    async def select_accent_8(self, interaction: discord.Interaction, select: discord.ui.Select):
        await select_accent(self, interaction, select)

    @discord.ui.button(label="Previous page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=accent_embed, view=AccentsView1(), ephemeral=True)


@bot.hybrid_command()
@app_commands.describe(tld="A localized top-level domain from which the accent will be read.")
async def setaccent(ctx: commands.Context, tld: to_lower = None):
    """Set the accent you want me to read your messages in."""

    if tld:
        try:
            requests.get(f"https://translate.google.{tld}")
        except requests.ConnectionError:
            await ctx.send(f"`{tld}` is not a valid top-level domain!\n\n`https://translate.google.`**`{tld}`** is **not a valid url** or is otherwise temporarily unavailable.\n\nEither try another value or try again later. Here is an incomplete [**list of top-level domains**](https://gtts.readthedocs.io/en/latest/module.html#localized-accents) you can use.\n\nAlternatively, rerun `/setaccent` without arguments to generate dropdowns to choose from.", ephemeral=True, suppress_embeds=True)

        else:
            user_id = ctx.author.id
            if user_id in bot.members_settings:
                bot.members_settings[user_id]["accent"] = tld
            else:
                bot.members_settings[user_id] = {"accent": tld}
            await ctx.send(f"Your accent's **top-level domain** has been set to `{tld}`.", ephemeral=True)
    elif len(tld_list) != 0:
        await ctx.send(embed=accent_embed, view=AccentsView1(), ephemeral=True)
    else:
        await ctx.send(f"Cannot fetch list of domains because https://www.google.com/supported_domains was unavailable when I logged in. Please specify a `tld` parameter or tell <@339841608134557696> to restart the bot.\n\nHere is an incomplete [**list of top-level domains**](https://gtts.readthedocs.io/en/latest/module.html#localized-accents) you can use.")
            




# endregion

# endregion

# region Set timeout
def return_seconds(argument):
    try:
        return int(argument)
    except:
        return argument.lower()

@bot.hybrid_command()
@commands.has_guild_permissions(administrator=True)
@app_commands.describe(seconds="Timeout duration in seconds. Type 'reset' to reset to default.")
async def settimeout(ctx: commands.Context, seconds: return_seconds):
    """Set the number of seconds of inactivity after which the bot will leave the voice channel."""

    error_message = f"Please enter a **positive whole number** to set the **timeout duration** in **seconds**.\n\nAlternatively, type `reset` to **reset the timeout** to the default value *({bot.default_settings['timeout']} seconds)*."

    if seconds == "reset" or seconds == bot.default_settings["timeout"]:
        if ctx.guild.id in bot.voice_channel_timeouts:
            del bot.voice_channel_timeouts[ctx.guild.id]
        await ctx.send(f"Timeout reset to **{bot.default_settings['timeout']} seconds**.", ephemeral=True)
    elif isinstance(seconds, int):
        if seconds <= 0:
            await ctx.send(error_message, ephemeral=True)
            return
        
        if seconds > 1:
            unit = "seconds"
        else:
            unit = "second"

        bot.voice_channel_timeouts[ctx.guild.id] = seconds
        await ctx.send(f"Timeout set to **{seconds} {unit}**.", ephemeral=True)
    else:
        await ctx.send(error_message, ephemeral=True)


    


# endregion

# region Leave
@bot.hybrid_command()
@commands.has_permissions(administrator=True)
async def leave(ctx: commands.Context):
    """Make the bot leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

# endregion

# region Sync
@bot.hybrid_command()
@commands.has_guild_permissions(administrator=True)
@app_commands.describe(guild="The server ID of the server you want to sync commands to.")
async def sync(ctx: commands.Context, guild: discord.Guild = None):
    """Sync slash commands either globally or for a specific guild."""

    # print("sync triggered")

    if guild:
        synced_commands = await bot.tree.sync(guild=guild)
        command_list = ""
        for command in synced_commands:
            command_list += f"\n- `/{command.name}`"
        await ctx.send(f"Commands synced to the guild: {guild.name}{command_list}\nPlease note it may take up to an hour to propagate globally.", ephemeral=True)
    else:
        try:
            synced_commands = await bot.tree.sync()
        except discord.app_commands.CommandSyncFailure as error:
            print(f"CommandSyncFailure: {error}")
        except discord.HTTPException as error:
            print(f"HTTPException: {error}")
        except discord.Forbidden as error:
            print(f"Forbidden: {error}")
        except discord.app_commands.TranslationError as error:
            print(f"TranslationError: {error}")
        # print("synced commands globally")
        command_list = ""
        for command in synced_commands:
            command_list += f"\n- `/{command.name}`"
        await ctx.send(f"Commands synced globally:{command_list}\nPlease note it may take up to an hour to propagate globally.", ephemeral=True)

# endregion

# endregion

# region shutdown
# shutdown function for graceful exit

async def shutdown(loop: asyncio.AbstractEventLoop):
    """Handles graceful shutdown of the bot and its tasks."""
    print("Shutting down the bot...")
    for queue_group in bot.queue.values():
        if queue_group["task"] is not None:
            queue_group["task"].cancel()
            try:
                await queue_group["task"]
            except asyncio.CancelledError:
                print("Queue task has been cancelled")
    await bot.close()
    print("Voicely Text has exited.")
# endregion

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # atexit.register(shutdown, loop)
    # signal.signal(signal.SIGINT, shutdown(loop))
    # signal.signal(signal.SIGTERM, shutdown(loop))

    try:
        loop.run_until_complete(bot.start(TOKEN))
    except KeyboardInterrupt:
        print("Bot is shutting down...")
        loop.run_until_complete(shutdown(loop))
    finally:
        loop.close()
        print("Bot has exited.")

if __name__ == "__main__":
    run_bot()
