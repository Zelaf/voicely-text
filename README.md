# Voicely Text
Voicely Text is another text-to-speech bot for Discord, but instead of linking text channels to voice channels, it speaks text from a voice channel's associated chat channel into said voice channel, without the need for commands beforehand.

[Invite me](https://discord.com/oauth2/authorize?client_id=1290741552158609419)
# Getting started
## Enabling text-to-speech
If you are in a voice channel, and you want the bot to **read your messages**, type `/tts start` in the associated voice chat channel. All of the messages you send in that channel will be read by Voicely Text until you either run `/tts stop` or leave the voice channel.
## Autoread
If you would like the bot to **automatically read your messages** whenever you join a voice channel without needing to run the `/tts start` command, type the command `/settings autoread` and set `enabled` to `true`, and whenever you join a voice channel, it will automatically read your messages from the associated voice chat channel.
## Set your language and accent
You can also set the **language** and the **accent** that the bot will read your messages in by typing `/settings language` and `/settings accent`. Typing either of these commands *without parameters* will display a collection of dropdowns for you to choose from.
- It turns out, if you type in English, and your language is set to Spanish, it will read the English text in a Spanish accent.
- If you're from the UK, you can make the bot read your messages in a British accent by setting the `tld` to `co.uk` when running `/settings accent`.
## Text-to-speech override
If you don't want the bot to read *all* of your messages, but just want it to **read a single message**, or if you already have your messages being read but want to **override the language or accent** for a single message, use the `/tts speak` command, and specify the text you want to be read under `text`.
- If you don't provide a `language` or `tld` (for the accent), your default language and accent will be used.
# Early development
This bot is still in early development, and I still need to fix up some things and add server-side settings, but the bot is completely useable in this state! Feel free to invite it to any of your servers, and just remember that things may change in the future!

If any of you have an issue with the bot, please create an [issue](https://github.com/Erallie/voicely-text/issues), and I will address it to the best of my ability!