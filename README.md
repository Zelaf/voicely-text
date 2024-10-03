# Voicely Text
Voicely Text is another text-to-speech bot for Discord, but instead of linking text channels to voice channels, it speaks text from a voice channel's associated chat channel into said voice channel, without the need for commands beforehand.

# Features
- Reads text messages from a voice channel's associated chat channel.
    - No need to be in a voice channel for the bot to read the text: it will read it in the associated voice channel.
- The ability to trigger TTS without using a command beforehand.
    - `/start` and `/stop` speaking text with slash commands.
    - Members can enable text to speech for all their messages when they join a voice channel by default.
- A `/tts` slash command to read just a single message if without needing to use the `/start` command.
- Individual members can set their preferred language.