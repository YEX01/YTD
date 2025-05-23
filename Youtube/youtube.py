import os
import logging
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from Youtube.config import Config
from Youtube.forcesub import handle_force_subscribe
from pathlib import Path
import tempfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
youtube_dl_username = None  
youtube_dl_password = None
DOWNLOAD_FOLDER = "yt_downloads"
COOKIES_FILE = "cookies.txt"

# Ensure download folder exists
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)

def get_cookies_config():
    """Return cookies configuration if cookies file exists"""
    if os.path.exists(COOKIES_FILE):
        logger.info("Using cookies file for authentication")
        return {'cookiefile': COOKIES_FILE}
    return {}

@Client.on_message(filters.regex(r'^(http(s)?:\/\/)?((w){3}.)?youtu(be|.be)?(\.com)?\/.+'))
async def process_youtube_link(client, message):
    if Config.CHANNEL:
        fsub = await handle_force_subscribe(client, message)
        if fsub == 400:
            return
    
    youtube_link = message.text
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎥 Best Quality", callback_data=f"download|best|{youtube_link}"),
            InlineKeyboardButton("🎵 Audio Only", callback_data=f"download|audio|{youtube_link}")
        ],
        [
            InlineKeyboardButton("🖥 1080p", callback_data=f"download|1080p|{youtube_link}"),
            InlineKeyboardButton("📺 2K", callback_data=f"download|2k|{youtube_link}")
        ],
        [
            InlineKeyboardButton("📽 4K", callback_data=f"download|4k|{youtube_link}"),
            InlineKeyboardButton("🖼 Medium", callback_data=f"download|medium|{youtube_link}")
        ],
        [
            InlineKeyboardButton("📱 Low Quality", callback_data=f"download|low|{youtube_link}"),
            InlineKeyboardButton("ℹ️ Info", callback_data=f"info|{youtube_link}")
        ]
    ])
    
    await message.reply_text(
        "**🎬 Select Download Format**\n\nChoose the quality you want to download:",
        reply_markup=keyboard
    )

async def cleanup_file(file_path):
    """Safely remove downloaded files"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")

async def download_thumbnail(thumbnail_url):
    """Download thumbnail to temporary file"""
    if not thumbnail_url:
        return None
        
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(tempfile.gettempdir(), 'thumbnail_%(id)s.%(ext)s'),
            'skip_download': True,
            'writethumbnail': True,
            'format': 'best'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(thumbnail_url, download=False)
            if not info:
                return None
                
            ydl.download([thumbnail_url])
            thumb_path = os.path.join(
                tempfile.gettempdir(),
                f"thumbnail_{info['id']}.{info['thumbnail'].split('.')[-1]}"
            )
            return thumb_path if os.path.exists(thumb_path) else None
    except Exception as e:
        logger.error(f"Error downloading thumbnail: {e}")
        return None

async def get_video_info(ydl, url):
    """Get video information safely"""
    try:
        return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return None

async def get_actual_file_path(download_path, file_id, is_audio=False):
    """Find the actual downloaded file path"""
    try:
        # First try the expected path
        expected_ext = 'mp3' if is_audio else 'mp4'
        expected_path = os.path.join(
            DOWNLOAD_FOLDER,
            f"downloaded_{'audio_' if is_audio else ''}{file_id}.{expected_ext}"
        )
        
        if os.path.exists(expected_path):
            return expected_path
            
        # If not found, search for any file with the video ID
        pattern = f"*{file_id}*"
        possible_files = list(Path(DOWNLOAD_FOLDER).glob(pattern))
        
        if possible_files:
            return str(possible_files[0])
            
        # Also check temp directory
        temp_files = list(Path(tempfile.gettempdir()).glob(pattern))
        if temp_files:
            return str(temp_files[0])
            
        return None
    except Exception as e:
        logger.error(f"Error finding file path: {e}")
        return None

@Client.on_callback_query(filters.regex(r'^(download|info)\|'))
async def handle_callback_query(client, callback_query):
    action, *data = callback_query.data.split('|')
    youtube_link = data[-1]
    
    if action == 'info':
        await handle_info_request(client, callback_query, youtube_link)
        return
        
    quality = data[0]
    
    quality_formats = {
        'best': 'best',
        'audio': 'bestaudio/best',
        '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '2k': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]',
        '4k': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
        'medium': 'best[height<=480]',
        'low': 'best[height<=360]'
    }
    
    if quality not in quality_formats:
        await callback_query.answer("Invalid quality selected", show_alert=True)
        return

    try:
        await callback_query.answer("Processing your request...")
        downloading_msg = await callback_query.message.reply("⏳ Downloading...")
        
        ydl_opts = {
            'format': quality_formats[quality],
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'downloaded_%(id)s.%(ext)s'),
            'progress_hooks': [lambda d: logger.info(d.get('status', 'No status'))],
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            **get_cookies_config()
        }

        if quality == 'audio':
            ydl_opts.update({
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }],
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'downloaded_audio_%(id)s.%(ext)s'),
            })

        if Config.HTTP_PROXY:
            ydl_opts['proxy'] = Config.HTTP_PROXY
        if youtube_dl_username:
            ydl_opts['username'] = youtube_dl_username
        if youtube_dl_password:
            ydl_opts['password'] = youtube_dl_password

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = await get_video_info(ydl, youtube_link)
            if not info_dict:
                await callback_query.message.reply("❌ Error: Could not get video information")
                return

            title = info_dict.get('title', 'Untitled')
            file_id = info_dict['id']
            is_audio = quality == 'audio'
            
            # Clean up any existing files
            await cleanup_file(os.path.join(DOWNLOAD_FOLDER, f"downloaded_{file_id}*"))
            
            try:
                await asyncio.to_thread(ydl.download, [youtube_link])
                
                file_path = await get_actual_file_path(DOWNLOAD_FOLDER, file_id, is_audio)
                if not file_path:
                    raise FileNotFoundError("Downloaded file not found")

                await downloading_msg.edit("📤 Uploading...")
                
                # Handle thumbnail
                thumb_path = None
                thumbnail_url = info_dict.get('thumbnail')
                if thumbnail_url:
                    thumb_path = await download_thumbnail(thumbnail_url)
                
                upload_kwargs = {
                    'chat_id': callback_query.message.chat.id,
                    'caption': f"🎵 {title}" if is_audio else f"🎬 {title}",
                }
                
                if is_audio:
                    upload_kwargs.update({
                        'audio': file_path,
                        'title': title[:64],
                        'performer': info_dict.get('uploader', 'Unknown Artist')[:64],
                        'duration': info_dict.get('duration', 0),
                        'thumb': thumb_path
                    })
                    await client.send_audio(**upload_kwargs)
                else:
                    upload_kwargs.update({
                        'video': file_path,
                        'duration': info_dict.get('duration', 0),
                        'width': info_dict.get('width'),
                        'height': info_dict.get('height'),
                        'thumb': thumb_path
                    })
                    await client.send_video(**upload_kwargs)
                
                await downloading_msg.delete()
                await callback_query.message.reply("✅ Successfully uploaded!")
                
            except Exception as upload_error:
                logger.error(f"Upload error: {upload_error}")
                await callback_query.message.reply(f"❌ Upload failed: {str(upload_error)}")
            finally:
                await cleanup_file(file_path)
                if thumb_path:
                    await cleanup_file(thumb_path)

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download error: {e}")
        await callback_query.message.reply("❌ Download error: The video may be restricted or unavailable")
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        await callback_query.message.reply("❌ Error: Downloaded file not found. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await callback_query.message.reply(f"❌ An unexpected error occurred: {str(e)}")
    finally:
        if 'downloading_msg' in locals():
            try:
                await downloading_msg.delete()
            except:
                pass

async def handle_info_request(client, callback_query, youtube_link):
    try:
        await callback_query.answer("Fetching video info...")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'simulate': True,
            'extract_flat': False,
            **get_cookies_config()
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, youtube_link, download=False)
            
            if not info:
                await callback_query.message.reply("❌ Could not fetch video information")
                return
                
            message_text = (
                f"📌 **Title:** {info.get('title', 'Unknown')}\n"
                f"👤 **Channel:** {info.get('uploader', 'Unknown')}\n"
                f"⏱ **Duration:** {info.get('duration', 0) // 60}:{info.get('duration', 0) % 60:02d}\n"
                f"👀 **Views:** {info.get('view_count', 'N/A')}\n"
                f"👍 **Likes:** {info.get('like_count', 'N/A')}\n"
                f"📅 **Upload Date:** {info.get('upload_date', 'Unknown')}"
            )
            
            thumbnail_url = info.get('thumbnail')
            thumb_path = await download_thumbnail(thumbnail_url) if thumbnail_url else None
            
            if thumb_path:
                await callback_query.message.reply_photo(
                    photo=thumb_path,
                    caption=message_text
                )
                await cleanup_file(thumb_path)
            else:
                await callback_query.message.reply(message_text)
                
    except Exception as e:
        logger.error(f"Info error: {e}")
        await callback_query.message.reply("❌ Could not fetch video information")
