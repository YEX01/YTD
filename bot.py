from pyrogram import Client, filters
from Youtube.config import Config

app = Client(
    "my_bot",
    api_id=Config.API_ID, 
    api_hash=Config.API_HASH, 
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="Youtube")
)


print("🎊 I'M ALIVE 🎊")
app.run()
