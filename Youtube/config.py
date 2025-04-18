import os
from dotenv import load_dotenv

load_dotenv()

class Config(object):
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API_ID = int(os.environ.get("API_ID", 0)) 
    API_HASH = os.environ.get("API_HASH", "")
    CHANNEL = os.environ.get("CHANNEL", "")
    HTTP_PROXY = os.environ.get("HTTP_PROXY", "")  # Fixed typo from HTTP_PROXY to HTTP_PROXY?
