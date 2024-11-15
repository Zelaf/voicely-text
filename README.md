# Voicely Text
Voicely Text is another text-to-speech bot for Discord, but instead of linking text channels to voice channels, it speaks text from a voice channel's associated text chat into said voice channel, without the need for commands beforehand.

[Invite me](https://discord.com/oauth2/authorize?client_id=1290741552158609419)
[Discord App Directory](https://discord.com/application-directory/1290741552158609419)
# Getting started
## Enabling text-to-speech
If you are in a voice channel, and you want the bot to **read your messages**, type `/tts start` in the associated text chat. All of the messages you send in that channel will be read by Voicely Text until you either run `/tts stop` or leave the voice channel.
## Autoread
If you would like the bot to **automatically read your messages** whenever you join a voice channel without needing to run the `/tts start` command, type the command `/set autoread` and set `enabled` to `true`, and whenever you join a voice channel, it will automatically read your messages from the associated text chat.
## Set your accent and region
You can also set the **accent** and the **region** that the bot will read your messages in by typing `/set accent` and `/set region`. Typing either of these commands *without parameters* will display a collection of dropdowns for you to choose from.
- If you're from the UK, you can make the bot read your messages in a British accent by setting the `tag` to `en` *(English)* when running `/set accent` and setting the `tld` to `co.uk` when running `/set region`.
## Text-to-speech override
If you don't want the bot to read *all* of your messages, but just want it to **read a single message**, or if you already have your messages being read but want to **override the accent or region** for a single message, use the `/tts speak` command, and specify the text you want to be read under `text`.
- If you don't provide an `accent` or `tld` (for the region), your default accent and region will be used.
## Skipping messages
If you want to **skip speaking messages** you may have already sent or are about to send, type `/tts skip`, with an optional `count` being the number of messages you want to skip.
- If one of your messages is currently being read, the currently spoken message will be included in the `count`.
## Nicknames
You can set a **nickname** for Voicely Text to call you every time it refers to you. Both when it **announces your messages** and when it **reads mentions**. To do so, type `/set nickname` and set the `nickname` parameter to the name you want to be called.
- Setting the `nickname` parameter to `reset` will remove the nickname.
- This is useful for if you have **special characters** in your display name that you don’t want to be read, or if the bot **mispronounces** your display name by default. Or if your display name is just **super long** and you want to shorten it.

If you want to **override** your nickname for a **specific server**, you can set the `server` parameter to the [server ID](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID) of the server you want to use the nickname in. This nickname will only be applied to messages sent in that server.
# Support
If you have any problems with the bot or want to request a feature, please create an [issue](https://github.com/Erallie/voicely-text/issues), and I will address it to the best of my ability!