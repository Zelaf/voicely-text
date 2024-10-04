import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
from gtts import gTTS
from gtts import lang
import os
import time
import math

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
        self.tts_queue = asyncio.Queue()
        self.queue_task = None
        self.voice_channel_timeouts = {}
        self.active_timeouts = {}
        self.default_timeout = 300  # 5 minutes in seconds
        self.user_languages = {}
        self.user_accents = {}

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
    bot.queue_task = bot.loop.create_task(process_queue())
    bot.loop.create_task(check_empty_channel())  # Start the empty channel check

    # Print out all registered commands
    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(f"- /{command.name}")

async def process_queue():
    while True:
        print("Waiting for the next message in the queue...")
        message, text, voice_channel = await bot.tts_queue.get()
        print(f"Processing message: {text}")

        # Convert the text to speech using gTTS
        tts = gTTS(text=text, lang='en')
        tts.save("tts.mp3")
        
        if bot.voice_clients and bot.voice_clients[0].channel != voice_channel:
            await bot.voice_clients[0].move_to(voice_channel)
        elif not bot.voice_clients:
            await voice_channel.connect()
            
        voice_client = message.guild.voice_client

        if voice_client and voice_client.is_connected():
            def after_playing(error):
                if error:
                    print(f"Error occurred during playback: {error}")

                # Indicate that the current task is done
                bot.loop.call_soon_threadsafe(bot.tts_queue.task_done)

                # Clean up the audio file
                try:
                    os.remove("tts.mp3")
                    print("Cleaned up the TTS file")
                except OSError:
                    print("Error cleaning up the TTS file.")

            # Play the audio file in the voice channel
            print("Playing the TTS message in the voice channel...")
            voice_client.play(discord.FFmpegPCMAudio("tts.mp3", executable='bot-env/ffmpeg/bin/ffmpeg'), after=after_playing)
            # ffmpeg currently uses version 7.1 on windows and 7.0.2 on linux

            # Wait until the current message is finished playing
            while voice_client.is_playing():
                await asyncio.sleep(1)
            print("Audio finished playing")
            
            timeout = bot.default_timeout
            if message.guild.id in bot.voice_channel_timeouts:
                timeout = bot.voice_channel_timeouts[message.guild.id]
            bot.active_timeouts[message.guild.id] = time.time() + timeout  # Reset timeout
        else:
            print("Voice client is not connected; task done")
            bot.tts_queue.task_done()

# region When a message is sent
@bot.event
async def on_message(message):
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
        print("Message contains no text, skipping.")
        return

    # Check if there is a voice channel with the same name as the text channel
    text_channel_name = message.channel.name
    voice_channel = discord.utils.get(message.guild.voice_channels, name=text_channel_name)

    if voice_channel:
        # Add the filtered message content to the queue
        await bot.tts_queue.put((message, message_content, voice_channel))
        print(f"Added message to queue: {message_content}")

    await bot.process_commands(message)

# endregion

# region Leave voice channel when empty
# Check if the bot is alone in the voice channel and disconnect if empty
async def check_empty_channel():
    """Periodically check if the bot is alone in the voice channel and disconnect."""
    while True:
        for guild_id, timeout in list(bot.active_timeouts.items()):
            guild = bot.get_guild(guild_id)
            if guild and guild.voice_client:
                voice_channel = guild.voice_client.channel
                if len(voice_channel.members) == 1:  # Only the bot is in the channel
                    await guild.voice_client.disconnect()
                    print(f"Disconnected from {guild.name} as it was empty.")
                    del bot.active_timeouts[guild_id]
        await asyncio.sleep(60)  # Check every 60 seconds

# endregion

# region Commands

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
    options = []
    
    langs = lang.tts_langs()
    keys = list(langs.keys())
    # iterated = 0

    select_count = math.ceil(len(langs) / 25)
    # print(f"select_count = {select_count}")
    
    for x in range(select_count):
        options.append([])
        # print(f"x = {x}")

        new_keys = keys[(x * 25):min((x * 25) + 25, len(keys))]

        for y in range(len(new_keys)):
            key = keys[y]
            options[x].append(discord.SelectOption(label=langs[key], value=key, description=key))

        # options.append(options)
        # iterated += 1

        @discord.ui.select(placeholder=f"Select a language ({x})", options=options[x], custom_id=f"language_dropdown_{x}")
        async def select_language(self, interaction: discord.Interaction, select: discord.ui.Select):
            langs = lang.tts_langs()
            user_id = interaction.user.id
            bot.user_languages[user_id] = select.values[0]
            return await interaction.response.send_message(f"Your language has been set to {langs[select.values[0]]}", ephemeral=True)

    """ @discord.ui.select(placeholder="Select a language/accent", options=options[0])
    async def select_language(self, interaction: discord.Interaction, select: discord.ui.Select):
        langs = lang.tts_langs()
        user_id = interaction.user.id
        bot.user_languages[user_id] = select.values[0]
        return await interaction.response.send_message(f"Your language has been set to {langs[select.values[0]]}", ephemeral=True)
    
    @discord.ui.select(placeholder="Select a language/accent", options=options[1])
    async def select_language(self, interaction: discord.Interaction, select: discord.ui.Select):
        langs = lang.tts_langs()
        user_id = interaction.user.id
        bot.user_languages[user_id] = select.values[0]
        return await interaction.response.send_message(f"Your language has been set to {langs[select.values[0]]}", ephemeral=True)
    
    @discord.ui.select(placeholder="Select a language/accent", options=options[2])
    async def select_language(self, interaction: discord.Interaction, select: discord.ui.Select):
        langs = lang.tts_langs()
        user_id = interaction.user.id
        bot.user_languages[user_id] = select.values[0]
        return await interaction.response.send_message(f"Your language has been set to {langs[select.values[0]]}", ephemeral=True) """


@bot.hybrid_command()
async def setlanguage(ctx):
    """Set the language and accent you want me to read your messages in."""

    embed = discord.Embed(title="Set your preferred language", description='Choose from the dropdown below to have me read your messages in that language.')

    await ctx.send(embed=embed, view=LanguagesView(), ephemeral=True)

# endregion

# region Command for accents

def to_lower(argument):
    return argument.lower()

@bot.hybrid_command()
@app_commands.describe(tld="A localized top-level domain the accent will be read with (eg. us, co.uk, com.au, etc).")
async def setaccent(ctx, tld: to_lower):
    """Set the accent you want me to read your messages in."""

    user_id = ctx.author.id
    bot.user_accents[user_id] = tld
    await ctx.send(f"Your top-level domain has been set to {tld}", ephemeral=True)


# endregion

# region Slash command to set timeout
@bot.hybrid_command()
@app_commands.describe(seconds="Timeout duration in seconds")
async def settimeout(ctx, seconds: int):
    """Set the inactivity timeout duration."""
    if seconds <= 0:
        await ctx.send("Please enter a valid timeout duration in seconds (greater than 0).", ephemeral=True)
        return

    bot.voice_channel_timeouts[ctx.guild.id] = seconds
    if seconds < 1:
        unit = "seconds"
    else:
        unit = "second"

    await ctx.send(f"Timeout set to {seconds} {unit}.", ephemeral=True)

# endregion

# region Command to make bot leave voice channel
@bot.hybrid_command()
async def leave(ctx):
    """Make the bot leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

# endregion

# region Manual sync command to sync slash commands globally or to a specific guild
@bot.hybrid_command()
async def sync(ctx: commands.Context, guild: discord.Guild = None):
    """Sync slash commands either globally or for a specific guild."""
    if guild:
        synced_commands = await bot.tree.sync(guild=guild)
        command_list = ""
        for command in synced_commands:
            command_list += f"\n- {command.name}"
            
        await ctx.send(f"Commands synced to the guild: {guild.name}{command_list}", ephemeral=True)
        
    else:
        synced_commands = await bot.tree.sync()
        command_list = ""
        for command in synced_commands:
            command_list += f"\n- {command.name}"

        await ctx.send(f"Commands synced globally:{command_list}\nPlease note it may take up to an hour to propagate globally.", ephemeral=True)

# endregion

# endregion

# region Shutdown function for graceful exit
async def shutdown():
    """Handles graceful shutdown of the bot and its tasks."""
    print("Shutting down the bot...")
    if bot.queue_task is not None:
        bot.queue_task.cancel()
        try:
            await bot.queue_task
        except asyncio.CancelledError:
            print("Queue task has been cancelled")

    await bot.close()
# endregion

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(bot.start(TOKEN))
    except KeyboardInterrupt:
        print("Bot is shutting down...")
        loop.run_until_complete(shutdown())
    finally:
        loop.close()
        print("Bot has exited.")

if __name__ == "__main__":
    run_bot()
