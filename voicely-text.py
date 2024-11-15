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
import datetime
import json
import builtins
from bs4 import BeautifulSoup
from enum import Enum
from typing import List
# import signal

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
            "accent": "en",
            "region": "com",
            "autoread": False,
            "timeout": 300
            # "prefix": "!"
        }
        self.active_timeouts = {}
        self.last_speakers = {}
        self.members_to_read = []
        self.to_skip = {}
        # to_skip will look like:
        # {
        #     guild_id: {
        #         text_channel_id: {
        #             user_id: amount_to_skip
        #         }
        #     }
        # }

    async def setup_hook(self):
        print(f"Setup complete for {self.user}")

bot = Bot()

# Read the bot token from external file
with open('../token', 'r') as file:
    TOKEN = file.read().strip()

# region save and load settings
# region members settings
# Load notify data from file (or return an empty dictionary if the file doesn't exist)
def load_members_settings():
    try:
        with open('data/members_settings.json', 'r') as f:
            # Load JSON data into a dictionary
            return json.load(f)
    except FileNotFoundError:
        print('Cannot open data/members_settings.json: File not found.')
        # If the file doesn't exist, return an empty dictionary
        return {}

# Store users who want to be notified in a dictionary {guild_id: set(user_ids)}
# Load the data from the JSON file when the bot starts
members_settings = load_members_settings()

# Save the current notify data to a JSON file
def save_members_settings():
    with open('data/members_settings.json', 'w') as f:
        # Write the dictionary to the JSON file
        json.dump(members_settings, f)

# endregion

# region server settings
# Load notify data from file (or return an empty dictionary if the file doesn't exist)
def load_servers_settings():
    try:
        with open('data/servers_settings.json', 'r') as f:
            # Load JSON data into a dictionary
            return json.load(f)
    except FileNotFoundError:
        print('Cannot open data/servers_settings.json: File not found.')
        # If the file doesn't exist, return an empty dictionary
        return {}

# Store users who want to be notified in a dictionary {guild_id: set(user_ids)}
# Load the data from the JSON file when the bot starts
servers_settings = load_servers_settings()

# Save the current notify data to a JSON file
def save_servers_settings():
    with open('data/servers_settings.json', 'w') as f:
        # Write the dictionary to the JSON file
        json.dump(servers_settings, f)


# endregion

# endregion

# region bot events

# region on ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

    for guild in bot.guilds:
        bot.queue[guild.id] = {
            "queue": asyncio.Queue(),
            "task": bot.loop.create_task(process_queue(guild))
        }
        bot.loop.create_task(check_empty_channel(guild)) # Start the empty channel check

    # Print out all registered commands
    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(f"- /{command.name}")
# endregion

# region on guild join
@bot.event
async def on_guild_join(guild: discord.Guild):
    if not guild.id in bot.queue:
        bot.queue[guild.id] = {
            "queue": asyncio.Queue(),
            "task": bot.loop.create_task(process_queue(guild))
        }
    else:
        bot.queue[guild.id]["queue"] = asyncio.Queue()
        bot.queue[guild.id]["task"] = bot.loop.create_task(process_queue(guild))
    
    bot.loop.create_task(check_empty_channel(guild))

    print(f"Bot added to guild: {guild.name}")

# endregion

# region on guild remove
@bot.event
async def on_guild_remove(guild: discord.Guild):
    if guild.id in bot.queue:
        if bot.queue[guild.id]["task"] is not None:
            bot.queue[guild.id]["task"].cancel()
            try:
                await bot.queue[guild.id]["task"]
            except asyncio.CancelledError:
                print(f"{guild.name}: Queue task has been cancelled")

        del bot.queue[guild.id]

        print(f"Bot removed from guild: {guild.name}")

# endregion

def return_nickname(user: discord.User | discord.Member, guild_id: int):
    guild_id_str = str(guild_id)
    user_id_str = str(user.id)
    if user_id_str in members_settings and "nickname" in members_settings[user_id_str]:
        if guild_id_str in members_settings[user_id_str]["nickname"]:
            return members_settings[user_id_str]["nickname"][guild_id_str]
        elif "default" in members_settings[user_id_str]["nickname"]:
            return members_settings[user_id_str]["nickname"]["default"]
        else:
            return user.display_name
    else:
        return user.display_name

async def process_queue(guild: discord.Guild):
    while True:
        print(f"{guild.name}: Waiting for the next message in the queue for...")
        message, text, user, voice_channel, accent_override, tld_override = await bot.queue[guild.id]["queue"].get()
        guild_id = guild.id
        user_id = user.id

        def should_play():
            if not guild_id in bot.to_skip:
                return True
            if not message.channel.id in bot.to_skip[guild_id]:
                return True
            if user_id in bot.to_skip[guild_id][message.channel.id] and bot.to_skip[guild_id][message.channel.id][user_id] > 0:
                return False
            if "admin" in bot.to_skip[guild_id][message.channel.id] and bot.to_skip[guild_id][message.channel.id]["admin"] > 0:
                return False
            else:
                if user_id in bot.to_skip[guild_id][message.channel.id]:
                    del bot.to_skip[guild_id][message.channel.id][user_id]
                if "admin" in bot.to_skip[guild_id][message.channel.id]:
                    del bot.to_skip[guild_id][message.channel.id]["admin"]
                return True
            
        def decrement_skips():
            if guild_id in bot.to_skip and message.channel.id in bot.to_skip[guild_id]:
                if user_id in bot.to_skip[guild_id][message.channel.id]:
                    bot.to_skip[guild_id][message.channel.id][user_id] -= 1
                    if bot.to_skip[guild_id][message.channel.id][user_id] <= 0:
                        del bot.to_skip[guild_id][message.channel.id][user_id]

                if "admin" in bot.to_skip[guild_id][message.channel.id]:
                    bot.to_skip[guild_id][message.channel.id]["admin"] -= 1
                    if bot.to_skip[guild_id][message.channel.id]["admin"] <= 0:
                        del bot.to_skip[guild_id][message.channel.id]["admin"]

                if len(bot.to_skip[guild_id][message.channel.id]) == 0:
                    del bot.to_skip[guild_id][message.channel.id]
                if len(bot.to_skip[guild_id]) == 0:
                    del bot.to_skip[guild_id]
        
        if not should_play():
            decrement_skips()
            print(f"{guild.name}: {user.global_name}'s message was skipped.")
            bot.loop.call_soon_threadsafe(bot.queue[guild_id]["queue"].task_done)
            continue
        
        # region reset timeout
        if guild_id in bot.active_timeouts:
            bot.active_timeouts[guild_id].cancel()

        bot.active_timeouts[guild_id] = asyncio.create_task(leave_after_timeout(guild))
        bot.active_timeouts[guild_id]
        # endregion

        print(f"{guild.name}: Processing message: {text}")
        
        # region set accent and region
        user_id_str = str(user_id)
        guild_id_str = str(guild_id)

        if accent_override:
            accent = accent_override
        elif user_id_str in members_settings and "accent" in members_settings[user_id_str]:
            accent = members_settings[user_id_str]["accent"]
        elif guild_id_str in servers_settings and "accent" in servers_settings[guild_id_str]:
            accent = servers_settings[guild_id_str]["accent"]
        else:
            accent = bot.default_settings["accent"]

        if tld_override:
            region = tld_override
        elif user_id_str in members_settings and "region" in members_settings[user_id_str]:
            region = members_settings[user_id_str]["region"]
        elif guild_id_str in servers_settings and "region" in servers_settings[guild_id_str]:
            region = servers_settings[guild_id_str]["region"]
        else:
            region = bot.default_settings["region"]
        
        # endregion

        try:
            requests.get(f"https://translate.google.{region}")
        except requests.ConnectionError:
            await message.reply(f"I cannot read your message because `https://translate.google.`**`{region}`** is currently down. Please run `/set region` and specify another top-level domain or try again later.\n\nOtherwise, type `/tts stop`, and I will stop reading your messages.")
            # Indicate that the current task is done
            bot.loop.call_soon_threadsafe(bot.queue[guild_id]["queue"].task_done)
            continue

        else:

            # region Prepend display name
            nickname = return_nickname(user, guild_id)
            
            if guild_id in bot.last_speakers and user_id is bot.last_speakers[guild_id]["user_id"]:
                last_time: datetime.datetime = bot.last_speakers[guild_id]["time"]
                time_diff = datetime.datetime.today() - last_time
                if time_diff.total_seconds() > 30:
                    text = nickname + ' says, ' + text
            else:
                text = nickname + ' says, ' + text
            # endregion

            # Convert the text to speech using gTTS
            tts = gTTS(text=text, lang=accent, tld=region)
            tts.save(f"voice_files/{guild_id}-tts.mp3")
            
            voice_client = guild.voice_client

            if voice_client and voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)
            elif not voice_client:
                await voice_channel.connect()

            voice_client: discord.VoiceClient = guild.voice_client

            if voice_client and voice_client.is_connected():
                def after_playing(error):
                    if error:
                        print(f"{guild.name}: Error occurred during playback: {error}")

                    # region add last_speakers
                    if guild_id in bot.last_speakers:
                        bot.last_speakers[guild_id]["user_id"] = user_id
                        bot.last_speakers[guild_id]["time"] = datetime.datetime.today()
                    else:
                        bot.last_speakers[guild_id] = {
                            "user_id": user_id,
                            "time": datetime.datetime.today()
                        }
                    # endregion

                    # Clean up the audio file
                    try:
                        os.remove(f"voice_files/{guild_id}-tts.mp3")
                        print(f"{guild.name}: Cleaned up the TTS file")
                    except OSError as remove_error:
                        print(f"{guild.name}: Error cleaning up the TTS file:\n\t{remove_error}")
                    finally:    
                        # Indicate that the current task is done
                        bot.loop.call_soon_threadsafe(bot.queue[guild_id]["queue"].task_done)

                # Play the audio file in the voice channel
                print(f"{guild.name}: Playing the TTS message in {message.channel.name}...")
                voice_client.play(discord.FFmpegPCMAudio(f"voice_files/{guild_id}-tts.mp3", executable='bot-env/ffmpeg/bin/ffmpeg'), after=after_playing)
                # ffmpeg currently uses version 7.1 on windows and 7.0.2 on linux

                # Wait until the current message is finished playing
                while voice_client.is_playing() and should_play():
                    await asyncio.sleep(1)
                if not should_play():
                    decrement_skips()
                    voice_client.stop()

                print(f"{guild.name}: Audio finished playing")
            else:
                print(f"{guild.name}: Voice client is not connected; task done")
                bot.queue[guild_id]["queue"].task_done()

# region When a message is sent

async def process_message(ctx: commands.Context | discord.Message, text: str, accent: str = None, tld: str = None):
    if ctx.author == bot.user or not ctx.guild:
        return

    for command in bot.commands:
        if text.startswith(f"{bot.command_prefix}{command}"):
            print(f"{ctx.guild.name}: Message is a command, skipping.")
            return
    
    text_channel_name = ctx.channel.name
    voice_channel = discord.utils.get(ctx.guild.voice_channels, name=text_channel_name)
    if ctx.channel is not voice_channel:
        print(f'{ctx.guild.name}: text channel is not the same voice channel.')
        return
    
    # Remove emote IDs, leaving only emote names (e.g., :emote_name:) 
    # This replaces <emote_name:123456789> with :emote_name:
    message_content = re.sub(r'<:(\w+):\d+>', r':\1:', text)

    # Remove links, replacing it with an empty string
    message_content = re.sub(r'(https?://\S+|www\.\S+)', "", message_content)

    # Replace mentions with user nickname.
    mentions = re.finditer(r'<@(\d{18,19})>', message_content)
    for mention in mentions:
        user_id = int(mention.group(1))
        member = ctx.guild.get_member(user_id)
        if member is not None:
            nickname = return_nickname(member, ctx.guild.id)
        else:
            user = bot.get_user(user_id)
            if user is None:
                nickname = "unknown user"
            else:
                nickname = return_nickname(bot.get_user(user_id), ctx.guild.id)
        message_content = message_content.replace(mention.group(0), nickname, 1)

    # Replace channels with channel names
    channels = re.finditer(r'<#(\d{18,19})>', message_content)
    for channel_id in channels:
        channel = bot.get_channel(int(channel_id.group(1)))
        if channel is not None:
            channel_name = channel.name
        else:
            channel_name = "unknown"
        message_content = message_content.replace(channel_id.group(0), channel_name, 1)

    # Replace role mentions with role names
    roles = re.finditer(r'<@&(\d{18,19})>', message_content)
    for role_id in roles:
        role = ctx.guild.get_role(int(role_id.group(1)))
        if role is not None:
            role_name = role.name
        else:
            role_name = "unknown role"
        message_content = message_content.replace(role_id.group(0), role_name, 1)

    # replace server guide
    message_content = message_content.replace("<id:guide>", "Server Guide")

    # replace channels and roles
    message_content = message_content.replace("<id:customize>", "Channels and Roles")

    # replace browse channels
    message_content = message_content.replace("<id:browse>", "Browse Channels")

    # Remove long numbers (e.g., numbers longer than 8 digits)
    # Replaces it with an empty string
    message_content = re.sub(r'\d{8,}', "", message_content)
    
    if message_content == "" or re.match(r'^[\s\t\n]+$', message_content, re.MULTILINE) != None:
        print(f"{ctx.guild.name}: Message contains no text, skipping.")
        return

    if isinstance(ctx, discord.Message):
        message = ctx
    elif isinstance(ctx, commands.Context):
        message = ctx.message

    if voice_channel:
        # Add the filtered message content to the queue
        await bot.queue[ctx.guild.id]["queue"].put((message, message_content, ctx.author, voice_channel, accent, tld))
        print(f"{ctx.guild.name}: Added message to queue for {ctx.author.display_name}: {message_content}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.id in bot.members_to_read and message.author.voice.channel is message.channel:
        await process_message(message, message.content)
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Event triggered when a user's voice state changes.
    Checks if a user has joined a voice channel and sends a DM to users who opted in for notifications.
    """
    # Check if the user joined a voice channel (wasn't in one before, but now is)
    if before.channel is not after.channel:
        user_id = member.id
        user_id_str = str(user_id)
        if after.channel is not None:
            # guild_id = after.channel.guild.id
            guild_id_str = str(after.channel.guild.id)
            if user_id_str in members_settings and "autoread" in members_settings[user_id_str]:
                add = members_settings[user_id_str]["autoread"]
            elif guild_id_str in servers_settings and "autoread" in servers_settings[guild_id_str]:
                add = servers_settings[guild_id_str]["autoread"]
            else:
                add = bot.default_settings["autoread"]

            if add:
                if user_id not in bot.members_to_read:
                    bot.members_to_read.append(user_id)
            else:
                if user_id in bot.members_to_read:
                    bot.members_to_read.remove(user_id)
        elif after.channel is None:
            if user_id in bot.members_to_read:
                bot.members_to_read.remove(user_id)
        

# endregion

# endregion

# region Leave empty channel
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

    guild_id_str = str(guild.id)

    try:
        if guild_id_str in servers_settings and "timeout" in servers_settings[guild_id_str]:
            timeout = servers_settings[guild_id_str]["timeout"]
        else:
            timeout = bot.default_settings["timeout"]
        
        print(f'Timeout set for {guild.name}.')
        await asyncio.sleep(timeout)
        if guild.voice_client:
            await guild.voice_client.disconnect()
            print(f'Disconnected from {guild.name} due to timeout.')
    except asyncio.CancelledError:
        print(f'Timeout cancelled for {guild.name}')

# endregion

# region Commands

# region Converters
def to_lower(argument: str):
    if argument:
        argument = argument.strip()
    if not argument or argument == "":
        return None
    return argument.lower()

def return_int(argument: str):
    if argument:
        argument = argument.strip()
    try:
        return int(argument)
    except:
        return argument.lower()

def return_stripped(argument: str):
    return argument.strip()

# endregion

accent_desc = "The IETF language tag of the accent I will speak your messages with. Type 'reset' to set to default."
accent_list_desc = "Type `/list accents` to list the supported language tags."
tld_desc = "A localized top-level domain of the region from which I will speak. Type 'reset' to set to default."
tld_list_desc = "Type `/list regions` for a list of supported top-level domains."
    
class ResponseType(Enum):
    user = "user"
    server = "server"

# def is_in_guild(interaction: discord.Interaction | commands.Context) -> bool:
#     return interaction.guild is not None

async def send_dm_error(ctx: commands.Context):
    if ctx.invoked_subcommand is not None:
        subcommand = f" {ctx.invoked_subcommand}"
    else:
        subcommand = ""

    await ctx.send(f"`/{ctx.command}{subcommand}` cannot be used in dm's! Please use this command in the text channel of a server.", reference=ctx.message, ephemeral=True)

# region Accents setup

def get_accent_response(accent: str, typeof: ResponseType, reset: bool, guild: discord.Guild = None):
    # langs = lang.tts_langs()
    if not reset:
        if typeof == ResponseType.user:
            return f"Your accent has been set to **{accent}**."
        elif typeof == ResponseType.server and guild is not None:
            return f"{guild.name}'s server accent has been set to **{accent}**."
    else:
        if typeof == ResponseType.user:
            if guild is not None:
                return f"Your accent has been **reset** to the server default: `{accent}`"
            else:
                return "Your accent has been **reset** to the server default."
        elif typeof == ResponseType.server and guild is not None:
            return f"{guild.name}'s server accent has been **reset** to default: `{accent}`"


class AccentsView(discord.ui.View):
    def __init__(self, typeof):
        super().__init__()
        self.type = typeof

    langs = lang.tts_langs()
    keys = list(langs.keys())
    
    options: List[List[discord.SelectOption]] = []
    
    select_count = math.ceil(len(langs) / 25)

    for x in range(select_count):
        options.append([])

        new_keys = keys[(x * 25):min((x * 25) + 25, len(keys))]

        for y in range(len(new_keys)):
            key = new_keys[y]
            options[x].append(discord.SelectOption(label=key, value=key, description=langs[key]))

    
    async def select_accent(self, interaction: discord.Interaction, select: discord.ui.Select):
        langs = lang.tts_langs()
        # user_id = interaction.user.id
        if self.type == "user":
            user_id_str = str(interaction.user.id)
            if user_id_str not in members_settings:
                members_settings[user_id_str] = {}
            members_settings[user_id_str]["accent"] = select.values[0]
            
            save_members_settings()
            
            return await interaction.response.send_message(get_accent_response(langs[select.values[0]], ResponseType.user, False), ephemeral=True)
        elif self.type == "server":
            guild = interaction.guild
            guild_id_str = str(guild.id)
            if guild_id_str not in servers_settings:
                servers_settings[guild_id_str] = {}
            servers_settings[guild_id_str]["accent"] = select.values[0]
            
            save_servers_settings()
            return await interaction.response.send_message(get_accent_response(langs[select.values[0]], ResponseType.server, False, guild), ephemeral=True)
        else:
            print(f"{interaction.guild.name}: Failed to set server accent:\n\t{self.type} is not a valid ResponseType!")
            return await interaction.response.send_message(f"There was an error setting the server accent. Please create an [issue](https://github.com/Erallie/voicely-text/issues) and include the following error:\n\n```\n{self.type} is not a valid ResponseType!\n```")


    @discord.ui.select(placeholder="Language tags af through id", options=options[0])
    async def select_accent_1(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_accent(interaction, select)
    
    @discord.ui.select(placeholder="Language tags is through si", options=options[1])
    async def select_accent_2(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_accent(interaction, select)
    
    @discord.ui.select(placeholder="Language tags sk through zh", options=options[2])
    async def select_accent_3(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.select_accent(interaction, select)

# endregion

# region Regions setup

def region_embed(typeof: ResponseType, guild: discord.Guild = None):
    if typeof == ResponseType.user:
        return discord.Embed(title="Set your preferred region", description='Choose one **top-level domain** from the series of dropdowns below.\n\nI will read your messages as though I am from a region that uses that domain.\n\nDomains are sorted **alphabetically**.')
    elif typeof == ResponseType.server and guild is not None:
        return discord.Embed(title=f"Set {guild.name}'s region", description='Choose one **top-level domain** from the series of dropdowns below to set the server default.\n\nI will read messages in your server as though I am from a region that uses that domain.\n\nDomains are sorted **alphabetically**.')
    else:
        print("Error getting region_embed")

def get_region_response(tld: str, typeof: ResponseType, reset: bool, guild: discord.Guild = None):
    if tld and tld != "":
        display_tld = f"`{tld}` - *{get_country(tld)}*"
    
    if not reset:
        if typeof == ResponseType.user:
            return f"Your region's **top-level domain** has been set to {display_tld}."
        elif typeof == ResponseType.server and guild is not None:
            return f"The **top-level domain** for {guild.name}'s region has been set to {display_tld}."
    else:
        if typeof == ResponseType.user:
            if guild is not None:
                return f"Your region's **top-level domain** has been reset to the server default: {display_tld}"
            else:
                return "Your region's **top-level domain** has been reset to the server default."
        elif typeof == ResponseType.server and guild is not None:
            return f"The **top-level domain** for {guild.name}'s region has been reset to default: {display_tld}"


async def select_region(self, interaction: discord.Interaction, select: discord.ui.Select, typeof: ResponseType):
    if typeof == ResponseType.user:
        user_id_str = str(interaction.user.id)
        if user_id_str not in members_settings:
            members_settings[user_id_str] = {}
        members_settings[user_id_str]["region"] = select.values[0]

        save_members_settings()

        return await interaction.response.send_message(get_region_response(select.values[0], ResponseType.user, False), ephemeral=True)
    elif typeof == ResponseType.server:
        guild = interaction.guild
        guild_id_str = str(guild.id)
        if guild_id_str not in servers_settings:
            servers_settings[guild_id_str] = {}
        servers_settings[guild_id_str]["region"] = select.values[0]
        
        save_servers_settings()
        
        return await interaction.response.send_message(get_region_response(select.values[0], ResponseType.server, False, guild), ephemeral=True)
    else:
        print(f"{interaction.guild.name}: Failed to set server region:\n\t{typeof} is not a valid type!")
        return await interaction.response.send_message(f"There was an error setting the server region. Please create an [issue](https://github.com/Erallie/voicely-text/issues) and include the following error:\n\n```\n{typeof} is not a valid ResponseType!\n```")

# region tld mappings
def tld_get_countries():
    url = "https://en.wikipedia.org/wiki/Country_code_top-level_domain"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    ccTLD_list = []
    for table in soup.find_all("table", class_="wikitable"):
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            ccTLD_list.append((cols[0].text, cols[1].text))

    ccTLD_dict = {}
    for ccTLD, country in ccTLD_list:
        ccTLD_dict[ccTLD] = country

    return ccTLD_dict

tld_countries = tld_get_countries()


def get_country(tld: str):
    start = tld.rfind('.')
    if start != -1:
        tld = tld[start:]
    else:
        tld = "." + tld
    country = str(tld_countries.get(tld))
    country = re.sub(r"\[\d+]", "", country)
    return country.strip()

# endregion

# region tld_list
def get_tld_list():
    response = requests.get("https://www.google.com/supported_domains")

    if response.status_code == 200:
        string = response.text.strip('.google.')
        tld_list = string.split('\n.google.')
        if "us" not in tld_list:
            tld_list.append("us")
        tld_list.sort()

        return tld_list
    else:
        print("\nError: You should restart the bot because I was unable to fetch https://www.google.com/supported_domains for regions!")
        return []

tld_list_raw = get_tld_list()

def get_tlds():
    options: List[List[discord.SelectOption]] = []
    
    select_count = math.ceil(len(tld_list_raw) / 25)

    for x in range(select_count):
        options.append([])

        new_list = tld_list_raw[(x * 25):min((x * 25) + 25, len(tld_list_raw))]

        for y in range(len(new_list)):
            options[x].append(discord.SelectOption(label=new_list[y], value=new_list[y], description=get_country(new_list[y])))
    return options

tld_list = get_tlds()
# tld_list = []
# endregion

# region views
class RegionsView1(discord.ui.View):
    def __init__(self, typeof: ResponseType):
        super().__init__()
        self.type = typeof
        
    if len(tld_list) > 3:
        @discord.ui.select(placeholder="Domains .ad through .cm", options=tld_list[0])
        async def select_region_1(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .cn through .co.zw", options=tld_list[1])
        async def select_region_2(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .com through .com.kh", options=tld_list[2])
        async def select_region_3(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .com.kw through .com.sv", options=tld_list[3])
        async def select_region_4(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        if len(tld_list) > 4:
            @discord.ui.button(label="Next page")
            async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_message(embed=region_embed(self.type, interaction.guild), view=RegionsView2(self.type), ephemeral=True)

class RegionsView2(discord.ui.View):
    def __init__(self, typeof: ResponseType):
        super().__init__()
        self.type = typeof
    
    if len(tld_list) > 7:
        @discord.ui.select(placeholder="Domains .com.tj through .gr", options=tld_list[4])
        async def select_region_5(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .gy through .mk", options=tld_list[5])
        async def select_region_6(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .ml through .sn", options=tld_list[6])
        async def select_region_7(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.select(placeholder="Domains .so through .ws", options=tld_list[7])
        async def select_region_8(self, interaction: discord.Interaction, select: discord.ui.Select):
            await select_region(self, interaction, select, self.type)

        @discord.ui.button(label="Previous page")
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(embed=region_embed(self.type, interaction.guild), view=RegionsView1(self.type), ephemeral=True)
# endregion

# endregion

# region information
# Create a hybrid group
@bot.hybrid_group()
async def list(ctx: commands.Context):
    """List different options."""
    if ctx.invoked_subcommand is None:
        await ctx.send(f"{ctx.invoked_subcommand} is not a valid subcommand.", reference=ctx.message, ephemeral=True)

@list.command()
async def accents(ctx: commands.Context):
    """List the IETF language tags of all the accents available to use."""

    langs = lang.tts_langs()
    keys = builtins.list(langs.keys())

    text = f"## Supported IETF language tags:"
    for key in keys:
        text += f"\n- `{key}` - *{langs[key]}*"

    embed = discord.Embed(description=text)

    # print(len(text))

    await ctx.send(embed=embed, reference=ctx.message, ephemeral=True)
    

@list.command()
async def regions(ctx: commands.Context):
    """List the top-level domains of all the regions available to use."""

    embed_text: List[str] = []

    this_list = [f"## Supported top-level domains:"]

    for tld in tld_list_raw:
        tld = tld.strip()
        text = f"- `{tld}` - *{get_country(tld)}*"
        test_join = "\n".join(this_list)
        # this_list.append(text)
        if len(test_join) + len(text) + 1 > 2048:
            embed_text.append(test_join)
            this_list: List[str] = []
        this_list.append(text)

    if len(this_list) != 0:
        full_text = "\n".join(this_list)
        embed_text.append(full_text)

    embeds: List[discord.Embed] = []
    for this_text in embed_text:
        embed = discord.Embed(description=this_text)
        embeds.append(embed)

    # for x in range(len(tld_list_raw)):
    #     if x < len(tld_list_raw) - 1:
    #         text += f"`{tld_list_raw[x].strip()}`, "
    #     else:
    #         text += f"and `{tld_list_raw[x]}`"

    # print(len(text))

    # embed = discord.Embed(title="Supported **top-level domains**", description=text)s
    await ctx.send(embeds=embeds, reference=ctx.message, ephemeral=True)
# endregion

# region TTS
@bot.hybrid_group()
async def tts(ctx: commands.Context):
    """Toggle or trigger text-to-speech"""
    if ctx.invoked_subcommand is None:
        await ctx.send(f"{ctx.invoked_subcommand} is not a valid subcommand.", reference=ctx.message, ephemeral=True)

# region start
@tts.command()
async def start(ctx: commands.Context):
    """Make me start reading your text."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    if ctx.author.voice.channel is None:
        await ctx.send('You must be in a voice channel to use this command.', reference=ctx.message, ephemeral=True)
        return
    elif ctx.author.voice.channel is not ctx.channel:
        await ctx.send('You can only use this command in the text chat of the voice channel you are currently in.', reference=ctx.message, ephemeral=True)
        return
    
    user_id = ctx.author.id

    if user_id not in bot.members_to_read:
        bot.members_to_read.append(user_id)
        await ctx.send('I will now read all your messages in this channel until you run `/tts stop` or leave the voice channel.', reference=ctx.message, ephemeral=True)
    else:
        await ctx.send('I am already reading your messages.', reference=ctx.message, ephemeral=True)

# endregion

#region stop
    
@tts.command()
async def stop(ctx: commands.Context):
    """Make me stop reading your text."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    if ctx.author.voice.channel is None:
        await ctx.send('You are not in a voice channel, so I am not reading your messages.', reference=ctx.message, ephemeral=True)
        return
    elif ctx.author.voice.channel is not ctx.channel:
        await ctx.send('You can only use this command in the text chat of the voice channel you are currently in.', reference=ctx.message, ephemeral=True)
        return
    
    user_id = ctx.author.id

    if user_id in bot.members_to_read:
        bot.members_to_read.remove(user_id)
        await ctx.send('I am no longer reading your messages. Type `/tts start` to have me read your messages again, or type `/tts speak [your message]` to have me read a single message with optional accent and region overrides.', reference=ctx.message, ephemeral=True)
    else:
        await ctx.send('I already not reading your messages.', reference=ctx.message, ephemeral=True)

# endregion

# region speak

@tts.command()
@app_commands.describe(text="The text you want me to speak.", accent=accent_desc, tld=tld_desc)
async def speak(ctx: commands.Context, text: str, accent: str = None, tld: to_lower = None):
    """Speak a single message with optional accent and region overrides."""
    
    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    text_channel_name = ctx.channel.name
    voice_channel = discord.utils.get(ctx.guild.voice_channels, name=text_channel_name)
    if voice_channel is None:
        await ctx.send("You can only use this command in a voice channel's text chat.", reference=ctx.message, ephemeral=True)
        return
    
    errors: List[str] = []

    if accent:
        langs = lang.tts_langs()
        
        if accent not in langs:
            errors.append(f"`{accent}` is not a valid IETF language tag! {accent_list_desc}")
            
            accent = None
        
    if tld:
        try:
            requests.get(f"https://translate.google.{tld}")
        except requests.ConnectionError:
            errors.append(f"I cannot retrieve your desired region because `https://translate.google.`**`{tld}`** is currently down or does not exist. Please specify another **top-level domain** or try again later. Type `/list regions` for a list of supported top-level domains. Otherwise, leave `tld` blank to use your default region.")
            tld = None
            
    if len(errors) != 0:
        final_error = "\n\n".join(errors)

        if len(errors) == 1:
            plural = ""
        else:
            plural = "s"

        final_error = f"I cannot read your message because of the following error{plural}:\n\n" + final_error

        await ctx.send(final_error, reference=ctx.message, ephemeral=True)
    else:
        await process_message(ctx, text, accent, tld)
        if ctx.interaction is not None:
            await ctx.send(f"**{ctx.author.display_name}:** {text}")

# endregion

# region skip

@tts.command()
@app_commands.describe(count="The number of upcoming messages I should skip. Type 'cancel' to read all upcoming messages.")
async def skip(ctx: commands.Context, count: return_int = 1):
    """Skip your next message(s) in this channel. This includes currently playing or sent messages."""
    
    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    invalid_count = '`count` must be a positive whole number! Alternatively, enter `cancel` to read all upcoming messages.'

    text_channel_name = ctx.channel.name
    voice_channel = discord.utils.get(ctx.guild.voice_channels, name=text_channel_name)
    if voice_channel is None:
        await ctx.send("You can only use this command in a voice channel's text chat.", reference=ctx.message, ephemeral=True)
        return
    
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id
    user_id = ctx.author.id
    if count == "cancel":
        if guild_id in bot.to_skip and channel_id in bot.to_skip[guild_id] and user_id in bot.to_skip[guild_id][channel_id]:
            del bot.to_skip[guild_id][channel_id][user_id]
            if len(bot.to_skip[guild_id][channel_id]) == 0:
                del bot.to_skip[guild_id][channel_id]
            if len(bot.to_skip[guild_id]) == 0:
                del bot.to_skip[guild_id]

        await ctx.send("All your upcoming messages will be read.", reference=ctx.message, ephemeral=True)
    elif isinstance(count, int):
        if count <= 0:
            await ctx.send(invalid_count, reference=ctx.message, ephemeral=True)
            return
        
        if guild_id not in bot.to_skip:
            bot.to_skip[guild_id] = {channel_id: {user_id: count}}
        elif channel_id not in bot.to_skip[guild_id]:
            bot.to_skip[guild_id][channel_id] = {user_id: count}
        else:
            bot.to_skip[guild_id][channel_id][user_id] = count

        if count > 1:
            plural = "s"
        else:
            plural = ""

        await ctx.send(f"Your next **{count} message{plural}** will not be read.\n\nIf one of your messages are currently being read, it will be skipped.\n\nType `/tts skip cancel` to speak all your upcoming messages.", reference=ctx.message, ephemeral=True)
    else:
        await ctx.send(invalid_count, reference=ctx.message, ephemeral=True)

# endregion

# endregion

# region User settings

# Create a hybrid group for 'settings' commands
@bot.hybrid_group()
async def set(ctx: commands.Context):
    """Settings for the bot."""
    if ctx.invoked_subcommand is None:
        await ctx.send(f"{ctx.invoked_subcommand} is not a valid subcommand.", reference=ctx.message, ephemeral=True)

# region autoread
@set.command()
@app_commands.describe(enabled="Type 'true' or 'false'. Or type 'reset' to reset to default.")
async def autoread(ctx: commands.Context, enabled: to_lower):
    """Set whether your messages are automatically read when you join a voice channel."""

    user_id_str = str(ctx.author.id)
    if ctx.guild is not None:
        guild_id_str = str(ctx.guild.id)
    else:
        guild_id_str = None

    match enabled:
        case "true":
            enabled_bool = True
            confirm_message = f"Autoread has been **enabled**.\n\nI will automatically read all of your messages when you join a voice channel without having to use `/tts start`.\n\nThis will be disabled when you leave the voice channel or type `/tts stop`."
        case "false":
            enabled_bool = False
            confirm_message = f"Autoread has been **disabled**.\n\nYou will need to type `/tts start` for me to start reading your messages.\n\nAlternatively, you can type `/tts speak [your message]` for me to read a single message."
        case "reset":
            if user_id_str in members_settings and "autoread" in members_settings[user_id_str]:
                del members_settings[user_id_str]["autoread"]
                if len(members_settings[user_id_str]) == 0:
                    del members_settings[user_id_str]
            
            save_members_settings()
            
            if guild_id_str is not None:
                if guild_id_str in servers_settings and "autoread" in servers_settings[guild_id_str]:
                    default = f': `{servers_settings[guild_id_str]["autoread"]}`'
                else:
                    default = f': `{bot.default_settings["autoread"]}`'
            else:
                default = "."

            await ctx.send(f"Autoread has been **reset** to the server default{default}", reference=ctx.message, ephemeral=True)
            return
        case _:
            await ctx.send(f"`enabled` must be set to either `True` or `False`. Alternatively, enter `reset` to set to default.", reference=ctx.message, ephemeral=True)
            return

    if user_id_str not in members_settings:
        members_settings[user_id_str] = {}
    members_settings[user_id_str]["autoread"] = enabled_bool
    
    save_members_settings()
    await ctx.send(confirm_message, reference=ctx.message, ephemeral=True)

# endregion

# region Accents

@set.command()
@app_commands.describe(tag=accent_desc)
async def accent(ctx: commands.Context, tag: str = None):
    """Set the accent you want me to read your messages in."""

    if tag:
        langs = lang.tts_langs()

        if tag == 'reset':
            user_id_str = str(ctx.author.id)
            if user_id_str in members_settings and "accent" in members_settings[user_id_str]:
                del members_settings[user_id_str]["accent"]
                if len(members_settings[user_id_str]) == 0:
                    del members_settings[user_id_str]
            
            save_members_settings()

            guild = ctx.guild
            print(str(guild))
            if guild is not None:
                guild_id_str = str(guild.id)
                if guild_id_str in servers_settings and "accent" in servers_settings[guild_id_str]:
                    default = servers_settings[guild_id_str]['accent']
                else:
                    default = bot.default_settings['accent']

                this_lang = langs[default]
            else:
                this_lang = ""
            
            await ctx.send(get_accent_response(this_lang, ResponseType.user, True, guild), reference=ctx.message, ephemeral=True)
            return


        if tag in langs:
            user_id_str = str(ctx.author.id)
            if user_id_str not in members_settings:
                members_settings[user_id_str] = {}
            members_settings[user_id_str]["accent"] = tag

            save_members_settings()
            
            await ctx.send(get_accent_response(langs[tag], ResponseType.user, False), reference=ctx.message, ephemeral=True)
        else:
            accent_error = f"`{tag}` is not a valid IETF language tag! {accent_list_desc}\n\n Alternatively, rerun `/set accent` without arguments to generate dropdowns to choose from."
            
            await ctx.send(accent_error, reference=ctx.message, ephemeral=True)
    else:
        embed = discord.Embed(title="Set your preferred accent", description='Choose from the dropdown below to have me read your messages in that accent.\n\nAccents are sorted **alphabetically** by **IETF language tag**.\n\nIf your region\'s accent is not listed below, you may need to run `/set region` to set your region instead.')

        await ctx.send(embed=embed, view=AccentsView("user"), reference=ctx.message, ephemeral=True)

# endregion

# region Regions

@set.command()
@app_commands.describe(tld=tld_desc)
async def region(ctx: commands.Context, tld: to_lower = None):
    """Set the region you want me to read your messages in."""

    if tld:
        if tld == 'reset':
            user_id_str = str(ctx.author.id)
            if user_id_str in members_settings and "region" in members_settings[user_id_str]:
                del members_settings[user_id_str]["region"]
                if len(members_settings[user_id_str]) == 0:
                    del members_settings[user_id_str]
            
            save_members_settings()

            guild = ctx.guild
            if guild is not None:
                guild_id_str = str(ctx.guild.id)
                if guild_id_str in servers_settings and "region" in servers_settings[guild_id_str]:
                    default = servers_settings[guild_id_str]["region"]
                else:
                    default = bot.default_settings["region"]
            else:
                default = ""
            
            await ctx.send(get_region_response(default, ResponseType.user, True, guild), reference=ctx.message, ephemeral=True)
            return
        
        if tld not in tld_list_raw:
            await ctx.send(f"`{tld}` is not a valid top-level domain!\n\n{tld_list_desc}\n\nAlternatively, rerun `/set region` without arguments to generate dropdowns to choose from.", ephemeral=True, reference=ctx.message, suppress_embeds=True)
            return

        user_id_str = str(ctx.author.id)
        if user_id_str not in members_settings:
            members_settings[user_id_str] = {}
        members_settings[user_id_str]["region"] = tld
        
        save_members_settings()
        await ctx.send(get_region_response(tld, ResponseType.user, False), reference=ctx.message, ephemeral=True)
    elif len(tld_list) != 0:
        await ctx.send(embed=region_embed(ResponseType.user), view=RegionsView1(ResponseType.user), reference=ctx.message, ephemeral=True)
    else:
        await ctx.send(f"Cannot fetch list of domains because https://www.google.com/supported_domains was unavailable when I logged in.\n\nPlease specify a `tld` parameter or tell <@339841608134557696> to restart the bot.\n\nHere is an incomplete [**list of top-level domains**](https://gtts.readthedocs.io/en/latest/module.html#localized-accents) you can use.", reference=ctx.message, ephemeral=True)
            
# endregion

# region Nickname
@set.command()
@app_commands.describe(nickname="A nickname for me to call you. Type 'reset' to remove your nickname.", server="The ID of the server you'd like to use this nickname for. Leave blank to apply as default to all.")
async def nickname(ctx: commands.Context, nickname: return_stripped, server: return_int = None):
    """Set a nickname for me to call you. Useful to specify pronunciations or avoid special characters."""

    user_id_str = str(ctx.author.id)

    invalid_server = f"I cannot set your nickname in the specified server because I am not in the server with the ID `{server}`, or it does not exist.\n\nPlease enter another `server` or leave it **blank** to set your **default nickname** for all servers.\n\nTo get the ID of a server, follow [these instructions](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID)."

    server_messages = []
    if server is None or server == "":
        server = "default"
        server_messages.append("by default in **all servers**")
        server_messages.append("display name")
        server_messages.append("")
    elif isinstance(server, int):
        server_obj = bot.get_guild(server)
        server = str(server)
        if server_obj is not None:
            server_messages.append(f"for the server **{server_obj.name}**")
            server_messages.append("default nickname")
            server_messages.append(f" in the server **{server_obj.name}**")
        else:
            await ctx.send(invalid_server, reference=ctx.message, ephemeral=True)
            return
    else:
        await ctx.send(invalid_server, reference=ctx.message, ephemeral=True)
        return

    if nickname is None or nickname == "":
        await ctx.send(f"The nickname you entered is not valid. Please enter text that is not just whitespaces.", reference=ctx.message, ephemeral=True)
    elif nickname.lower() == "reset":
        if user_id_str in members_settings and "nickname" in members_settings[user_id_str] and server in members_settings[user_id_str]["nickname"]:
            del members_settings[user_id_str]["nickname"][server]
            
            if len(members_settings[user_id_str]["nickname"]) == 0:
                del members_settings[user_id_str]["nickname"]
            if len(members_settings[user_id_str]) == 0:
                del members_settings[user_id_str]
        
        save_members_settings()
        
        await ctx.send(f"Your nickname has been **removed** {server_messages[0]}.\n\nI will refer to you as your **{server_messages[1]}** when **reading mentions** and when **announcing your messages**{server_messages[2]}.", reference=ctx.message, ephemeral=True)
    else:
        if user_id_str not in members_settings:
            members_settings[user_id_str] = {}
        if "nickname" not in members_settings[user_id_str]:
            members_settings[user_id_str]["nickname"] = {}
        
        members_settings[user_id_str]["nickname"][server] = nickname

        save_members_settings()
        await ctx.send(f"Your nickname has been set to **{nickname}** {server_messages[0]}.\n\nI will say this whenever I refer to you{server_messages[2]}, both when **reading mentions** and when **announcing your messages**.", reference=ctx.message, ephemeral=True)

# endregion

# endregion

# region Server settings

# Create a hybrid group for 'settings' commands
@set.group()
async def server(ctx: commands.Context):
    """Settings that apply to the entire server. Can be overridden by user settings."""
    if ctx.invoked_subcommand is None:
        await ctx.send(f"{ctx.invoked_subcommand} is not a valid subcommand.", reference=ctx.message, ephemeral=True)

# region Botprefix
# @server.command()
# @commands.has_permissions(administrator=True)
# @app_commands.describe(prefix="One or more characters to be used as a prefix. Type 'reset' to set to default.")
# async def botprefix(ctx: commands.Context, prefix: return_stripped):
#     """Set the prefix used to run bot commands."""

#     guild = ctx.guild
#     guild_id_str = str(guild.id)

#     if prefix == 'reset':
#         if guild_id_str in servers_settings and "prefix" in servers_settings[guild_id_str]:
#             del servers_settings[guild_id_str]["prefix"]
        
#         default = bot.default_settings["prefix"]

#         bot.command_prefix = default
        
#         save_servers_settings()

#         await ctx.send(f"{guild.name}'s bot prefex has been **reset** to default: `{default}`", reference=ctx.message, ephemeral=True)
#         return
#     elif prefix is not "":
#         if guild_id_str in servers_settings:
#             servers_settings[guild_id_str]["prefix"] = prefix
#         else:
#             servers_settings[guild_id_str] = {"prefix": prefix}

#         bot.command_prefix = 
#         save_servers_settings()
        
#         await ctx.send(f"{guild.name}'s server accent has been set to **{langs[tag]}**.", reference=ctx.message, ephemeral=True)
#     else:
#         accent_error = f"`{tag}` is not a valid IETF language tag! {accent_list_desc}\n\n Alternatively, rerun `/set server accent` without arguments to generate dropdowns to choose from."
        
#         await ctx.send(accent_error, reference=ctx.message, ephemeral=True)
# endregion

# region Timeout
@server.command()
@commands.has_permissions(administrator=True)
@app_commands.describe(seconds="Timeout duration in seconds. Type 'reset' to reset to default.")
async def timeout(ctx: commands.Context, seconds: return_int):
    """Set the number of seconds of inactivity after which the bot will leave the voice channel."""
    
    if ctx.guild is None:
        await send_dm_error(ctx)
        return
        
    error_message = f"Please enter a **positive whole number** to set the **timeout duration** in **seconds**.\n\nAlternatively, type `reset` to **reset the timeout** to the default value *({bot.default_settings['timeout']} seconds)*."

    guild_id_str = str(ctx.guild.id)

    if seconds == "reset":
        if guild_id_str in servers_settings and "timeout" in servers_settings[guild_id_str]:
            del servers_settings[guild_id_str]["timeout"]
            if len(servers_settings[guild_id_str]) == 0:
                del servers_settings[guild_id_str]
        save_servers_settings()
        await ctx.send(f"Timeout reset to **{bot.default_settings['timeout']} seconds**.", reference=ctx.message, ephemeral=True)
    elif isinstance(seconds, int):
        if seconds <= 0:
            await ctx.send(error_message, reference=ctx.message, ephemeral=True)
            return
        
        if seconds > 1:
            unit = "seconds"
        else:
            unit = "second"

        if guild_id_str not in servers_settings:
            servers_settings[guild_id_str] = {}
        servers_settings[guild_id_str]["timeout"] = seconds

        save_servers_settings()
        await ctx.send(f"Timeout set to **{seconds} {unit}**.", reference=ctx.message, ephemeral=True)
    else:
        await ctx.send(error_message, reference=ctx.message, ephemeral=True)

# endregion

# region Accents

@server.command()
@commands.has_permissions(administrator=True)
@app_commands.describe(tag=accent_desc)
async def accent(ctx: commands.Context, tag = None):
    """Set the default accent for the server. This can be overridden on a per-user basis."""
    
    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    guild = ctx.guild

    if tag:
        guild_id_str = str(guild.id)
        langs = lang.tts_langs()
        if tag == 'reset':
            if guild_id_str in servers_settings and "accent" in servers_settings[guild_id_str]:
                del servers_settings[guild_id_str]["accent"]
                if len(servers_settings[guild_id_str]) == 0:
                    del servers_settings[guild_id_str]
            
            default = bot.default_settings["accent"]
            
            save_servers_settings()

            await ctx.send(get_accent_response(langs[default], ResponseType.server, True, guild), reference=ctx.message, ephemeral=True)
            return

        if tag in langs:
            if guild_id_str not in servers_settings:
                servers_settings[guild_id_str] = {}
            servers_settings[guild_id_str]["accent"] = tag

            save_servers_settings()
            
            await ctx.send(get_accent_response(langs[tag], ResponseType.server, False, guild), reference=ctx.message, ephemeral=True)
        else:
            accent_error = f"`{tag}` is not a valid IETF language tag! {accent_list_desc}\n\n Alternatively, rerun `/set server accent` without arguments to generate dropdowns to choose from."
            
            await ctx.send(accent_error, reference=ctx.message, ephemeral=True)
    else:
        embed = discord.Embed(title=f"Set {guild.name}'s accent", description='Choose from the dropdown below to set the server default to that accent.\n\nAccents are sorted **alphabetically** by **IETF language tag**.\n\nIf your region\'s accent is not listed below, you may need to run `/set server region` to set the server region instead.')

        await ctx.send(embed=embed, view=AccentsView("server"), reference=ctx.message, ephemeral=True)

# endregion

# region Regions

@server.command()
@commands.has_permissions(administrator=True)
@app_commands.describe(tld=tld_desc)
async def region(ctx: commands.Context, tld: to_lower = None):
    """Set the default region for the server. This can be overridden on a per-user basis."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    guild = ctx.guild

    if tld:
        guild_id_str = str(guild.id)
        if tld == 'reset':
            if guild_id_str in servers_settings and "region" in servers_settings[guild_id_str]:
                del servers_settings[guild_id_str]["region"]
                if len(servers_settings[guild_id_str]) == 0:
                    del servers_settings[guild_id_str]
            
            default = bot.default_settings["region"]
            
            save_servers_settings()
            
            await ctx.send(get_region_response(default, ResponseType.server, True, guild), reference=ctx.message, ephemeral=True)
            return
        
        if tld not in tld_list_raw:
            await ctx.send(f"`{tld}` is not a valid top-level domain!\n\n{tld_list_desc}\n\nAlternatively, rerun `/set server region` without arguments to generate dropdowns to choose from.", ephemeral=True, reference=ctx.message, suppress_embeds=True)
            return

        if guild_id_str not in servers_settings:
            servers_settings[guild_id_str] = {}
        servers_settings[guild_id_str]["region"] = tld
        
        save_servers_settings()
        await ctx.send(get_region_response(tld, ResponseType.server, False, guild), reference=ctx.message, ephemeral=True)
    elif len(tld_list) != 0:
        await ctx.send(embed=region_embed(ResponseType.server, guild), view=RegionsView1(ResponseType.server), reference=ctx.message, ephemeral=True)
    else:
        await ctx.send(f"Cannot fetch list of domains because https://www.google.com/supported_domains was unavailable when I logged in.\n\nPlease specify a `tld` parameter or tell <@339841608134557696> to restart the bot.\n\nHere is an incomplete [**list of top-level domains**](https://gtts.readthedocs.io/en/latest/module.html#localized-accents) you can use.", reference=ctx.message, ephemeral=True)
            
# endregion

# region autoread
@server.command()
@commands.has_permissions(administrator=True)
@app_commands.describe(enabled="Type 'true' or 'false'. Or type 'reset' to reset to default.")
async def autoread(ctx: commands.Context, enabled: to_lower):
    """Set the autoread default for the server."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    # user_id_str = str(ctx.author.id)
    guild = ctx.guild
    guild_id_str = str(guild.id)

    match enabled:
        case "true":
            enabled_bool = True
            confirm_message = f"Autoread has been **enabled** by default for {guild.name}.\n\nI will automatically read all messages sent when someone joins a voice channel without having to use `/tts start`.\n\nThis will be disabled when they leave the voice channel or type `/tts stop`."
        case "false":
            enabled_bool = False
            confirm_message = f"Autoread has been **disabled** by default for {guild.name}.\n\nMembers will need to type `/tts start` for me to start reading their messages.\n\nAlternatively, they can type `/tts speak [message]` for me to read a single message."
        case "reset":
            if guild_id_str in servers_settings and "autoread" in servers_settings[guild_id_str]:
                del servers_settings[guild_id_str]["autoread"]
                if len(servers_settings[guild_id_str]) == 0:
                    del servers_settings[guild_id_str]
            
            default = bot.default_settings["autoread"]
            save_servers_settings()
            await ctx.send(f"Autoread for {guild.name} has been **reset** to default: `{default}`", reference=ctx.message, ephemeral=True)
            return
        case _:
            await ctx.send(f"`enabled` must be set to either `True` or `False`. Alternatively, enter `reset` to set to default.", reference=ctx.message, ephemeral=True)
            return

    if guild_id_str not in servers_settings:
        servers_settings[guild_id_str] = {}
    servers_settings[guild_id_str]["autoread"] = enabled_bool
    
    save_servers_settings()
    await ctx.send(confirm_message, reference=ctx.message, ephemeral=True)

# endregion

# endregion

# region Admin commands

# Create a hybrid group for 'settings' commands
@bot.hybrid_group()
async def admin(ctx: commands.Context):
    """Admin commands"""
    if ctx.invoked_subcommand is None:
        await ctx.send(f"{ctx.invoked_subcommand} is not a valid subcommand.", reference=ctx.message, ephemeral=True)

# region Leave
@admin.command()
@commands.has_permissions(administrator=True)
async def leave(ctx: commands.Context):
    """Make the bot leave the voice channel."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.", reference=ctx.message)
    else:
        await ctx.send("I'm not in a voice channel.", reference=ctx.message, ephemeral=True)

# endregion

# region skip

@admin.command()
@commands.has_permissions(administrator=True)
@app_commands.describe(count="The number of upcoming messages I should skip. Type 'cancel' to read all upcoming messages.")
async def skip(ctx: commands.Context, count: return_int = 1):
    """Skip the next message(s) in this channel. This includes currently playing or sent messages."""

    if ctx.guild is None:
        await send_dm_error(ctx)
        return

    invalid_count = '`count` must be a positive whole number! Alternatively, enter `cancel` to read all upcoming messages.'

    text_channel_name = ctx.channel.name
    voice_channel = discord.utils.get(ctx.guild.voice_channels, name=text_channel_name)
    if voice_channel is None:
        await ctx.send("You can only use this command in a voice channel's text chat.", reference=ctx.message, ephemeral=True)
        return
    
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id
    # user_id = ctx.author.id
    if count == "cancel":
        if guild_id in bot.to_skip and channel_id in bot.to_skip[guild_id] and "admin" in bot.to_skip[guild_id][channel_id]:
            del bot.to_skip[guild_id][channel_id]["admin"]
            if len(bot.to_skip[guild_id][channel_id]) == 0:
                del bot.to_skip[guild_id][channel_id]
            if len(bot.to_skip[guild_id]) == 0:
                del bot.to_skip[guild_id]

        await ctx.send("All upcoming messages in this channel will be read.", reference=ctx.message, ephemeral=True)
    elif isinstance(count, int):
        if count <= 0:
            await ctx.send(invalid_count, reference=ctx.message, ephemeral=True)
            return
        
        if guild_id not in bot.to_skip:
            bot.to_skip[guild_id] = {channel_id: {"admin": count}}
        elif channel_id not in bot.to_skip[guild_id]:
            bot.to_skip[guild_id][channel_id] = {"admin": count}
        else:
            bot.to_skip[guild_id][channel_id]["admin"] = count

        if count > 1:
            plural = "s"
        else:
            plural = ""

        await ctx.send(f"The next **{count} message{plural}** in this channel will not be read.\n\nIf a message is currently being read, it will be skipped.\n\nType `/admin skip cancel` to speak all upcoming messages.", reference=ctx.message, ephemeral=True)
    else:
        await ctx.send(invalid_count, reference=ctx.message, ephemeral=True)

# endregion

# region Sync
@bot.command()
@commands.is_owner()
@app_commands.describe(guild="The server ID of the server you want to sync commands to.")
async def sync(ctx: commands.Context, guild: discord.Guild = None):
    """Sync slash commands either globally or for a specific guild."""

    if guild:
        synced_commands = await bot.tree.sync(guild=guild)
        command_list = ""
        for command in synced_commands:
            command_list += f"\n- `/{command.name}`"
        await ctx.send(f"Commands synced to the guild: {guild.name}{command_list}\nPlease note it may take up to an hour to propagate globally.", reference=ctx.message, ephemeral=True)
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
        await ctx.send(f"Commands synced globally:{command_list}\nPlease note it may take up to an hour to propagate globally.", reference=ctx.message, ephemeral=True)

# endregion

# endregion

# endregion

# region shutdown
# shutdown function for graceful exit

async def shutdown():
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

    # def run_shutdown():
    #     loop.run_until_complete(shutdown())
    # atexit.register(shutdown, loop)
    # signal.signal(signal.SIGINT, run_shutdown)
    # signal.signal(signal.SIGTERM, run_shutdown)

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
