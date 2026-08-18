from flask import Flask, render_template_string, request, jsonify, send_file, Response
from openai import OpenAI

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_READY = True
except ImportError:
    PYAUTOGUI_READY = False

try:
    import pygetwindow as gw
    PYGETWINDOW_READY = True
except ImportError:
    PYGETWINDOW_READY = False

try:
    import pyperclip
    PYPERCLIP_READY = True
except ImportError:
    PYPERCLIP_READY = False

try:
    import lameenc
    LAMEENC_READY = True
except ImportError:
    LAMEENC_READY = False

try:
    from pydub import AudioSegment
    PYDUB_READY = True
except ImportError:
    PYDUB_READY = False

import os
import json
import io
import time
import threading
import datetime
import webbrowser
import asyncio
import re
import base64
import shutil
import edge_tts
import urllib.parse
import subprocess
import sys
import ctypes
import psutil
import requests

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY missing!")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "eu-north-1")
AWS_READY = AWS_AVAILABLE and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

GROQ_MODEL = "openai/gpt-oss-120b"
groq_client = None
if GROQ_API_KEY:
    groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

EDGE_TTS_VOICE = "ta-IN-PallaviNeural"
EDGE_TTS_RATE = "+5%"
EDGE_TTS_PITCH = "+2Hz"
EDGE_TTS_VOLUME = "+10%"

VOICE_PROFILES = {
    "pallavi": {"voice": "ta-IN-PallaviNeural", "rate": "+5%", "pitch": "+2Hz", "label": "Pallavi"},
    "cute": {"voice": "ta-IN-PallaviNeural", "rate": "+12%", "pitch": "+10Hz", "label": "Cute"},
    "saranya": {"voice": "ta-LK-SaranyaNeural", "rate": "+5%", "pitch": "+2Hz", "label": "Saranya"},
}

LAST_BRAIN = "⚡ Groq"
def set_brain(b):
    global LAST_BRAIN
    LAST_BRAIN = b

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "screenshots")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

if PYDUB_READY:
    FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
    if os.path.exists(FFMPEG_PATH):
        AudioSegment.converter = FFMPEG_PATH
        AudioSegment.ffprobe = FFMPEG_PATH

HISTORY_FILE = os.path.join(DATA_DIR, "conversation_history.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
MEMORY_FILE = os.path.join(DATA_DIR, "long_term_memory.json")
MOOD_FILE = os.path.join(DATA_DIR, "current_mood.json")
conversation_history = []
MAX_HISTORY_MESSAGES = 20

CURRENT_MOOD = {"mood": "neutral", "intensity": 5, "timestamp": 0}

def load_mood():
    global CURRENT_MOOD
    try:
        if os.path.exists(MOOD_FILE):
            with open(MOOD_FILE, "r") as f: CURRENT_MOOD = json.load(f)
    except: pass

def save_mood():
    try:
        CURRENT_MOOD["timestamp"] = time.time()
        with open(MOOD_FILE, "w") as f: json.dump(CURRENT_MOOD, f)
    except: pass

def detect_emotion(text):
    global CURRENT_MOOD
    try:
        prompt = f"""Analyze the emotion in this message. Return ONLY JSON like: {{"mood":"happy","intensity":8}}
Moods: happy, sad, excited, tired, angry, neutral, curious
Intensity: 1-10
Message: {text}"""
        messages = [{"role": "system", "content": "You detect emotion. Return ONLY JSON."}, {"role": "user", "content": prompt}]
        reply = _groq_complete(messages)
        if not reply: return
        m = re.search(r'\{[^}]+\}', reply)
        if m:
            emo = json.loads(m.group(0))
            if "mood" in emo and emo["mood"] in ["happy","sad","excited","tired","angry","neutral","curious"]:
                CURRENT_MOOD = {"mood": emo["mood"], "intensity": emo.get("intensity",5), "timestamp": time.time()}
                save_mood()
                print(f"😺 Mood detected: {emo['mood']} ({emo.get('intensity',5)}/10)")
    except Exception as e:
        print(f"Emotion error: {e}")

def get_mood_context():
    if not CURRENT_MOOD.get("mood"): return ""
    age = time.time() - CURRENT_MOOD.get("timestamp", 0)
    if age > 300: return ""
    mood = CURRENT_MOOD["mood"]; intensity = CURRENT_MOOD["intensity"]
    tone_map = {
        "happy":"Be cheerful and match their good mood! 🎉","sad":"Be warm, comforting, supportive. 💙",
        "excited":"Match their excitement! Be energetic! 🔥","tired":"Be gentle, brief, relaxing. 😴",
        "angry":"Be calm, understanding. 🕊️","neutral":"Normal friendly tone.","curious":"Be detailed, engaging! 🤓"
    }
    return f"\n\nUSER'S CURRENT MOOD: {mood} (intensity {intensity}/10)\nTONE: {tone_map.get(mood,'Normal')}\n"

LAST_USER_ACTIVITY = time.time()
LAST_PROACTIVE_SPEAK = 0
MORNING_GREETED_TODAY = None
EVENING_GREETED_TODAY = None
WEATHER_ALERTED_TODAY = None

_THINK_TAG = '<' + '/' + 'think>'
THINK_PATTERN = re.compile(r'<' + 'think>.*?' + _THINK_TAG, flags=re.DOTALL)
def clean_think(text):
    return THINK_PATTERN.sub('', text).strip()

SYSTEM_PROMPT = """
You are Vasanth AI, a friendly personal AI assistant for Vasanth with FULL PC CONTROL. You are like JARVIS.
LANGUAGE & TONE RULES:
- Speak in natural Tanglish (Tamil + English mix), like a real Chennai friend.
- Call Vasanth "macha". BE HUMAN with fillers like "Hmm...", "Aama macha...", "Sari...".
- Use **bold** for important words.
SPECIAL ACTION RULES:
- AI IMAGE GEN: [IMAGE: detailed english description]
- YOUTUBE SUMMARY: [YT: video url]
- WEATHER: [WEATHER]
- PLAY media: [PLAY: query]
- SEARCH web: [SEARCH: query]
- OPEN web apps: [OPEN: app name]
- OPEN INSTALLED APPS: [APP: app name]
- RUN COMMAND: [CMD: shell command]
- FILE OPS: [FILE: delete|copy|move|rename|create_folder|list|source|destination]
- WINDOW: [WINDOW: close|minimize|maximize|activate|minimize_all|close_all|title]
- PROCESS: [PROCESS: list|kill|name]
- CLIPBOARD: [CLIP: copy|paste|text]
- POWER: [POWER: lock|sleep|shutdown|restart]
- VOLUME/BRIGHTNESS: [ACTION: volume_up/volume_down/mute/brightness_up/brightness_down]
- MEDIA: [ACTION: media_play_pause/media_next/media_prev]
- SYSTEM: [SYSTEM: battery/cpu/ram]
- FOLDERS: [FOLDER: downloads/documents/desktop/pictures/videos]
- MATH/CODE: [CODE]print(1+1)[/CODE]
- REMINDER: [REMINDER: minutes|message]
- CRICKET: [CRICKET: query]
- SCREENSHOT: [SCREENSHOT]
- CLICK: [CLICK: x,y] or [CLICK: center]
- TYPE: [TYPE: text]
- SCROLL: [SCROLL: up/down/amount]
When using these special actions, DO NOT write any other text, just the bracketed command.
"""

PWA_ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs>
<linearGradient id="sun" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#f5d0fe"/><stop offset=".5" stop-color="#e879f9"/><stop offset="1" stop-color="#ec4899"/>
</linearGradient>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#1e1b4b"/><stop offset="1" stop-color="#0f0a1e"/>
</linearGradient>
</defs>
<rect width="512" height="512" rx="112" fill="url(#bg)"/>
<circle cx="256" cy="220" r="130" fill="url(#sun)"/>
<rect x="126" y="220" width="260" height="12" fill="#1e1b4b"/>
<rect x="126" y="252" width="260" height="16" fill="#1e1b4b"/>
<rect x="126" y="290" width="260" height="20" fill="#1e1b4b"/>
<g stroke="#e879f9" stroke-width="6" fill="none" opacity=".7">
<path d="M86 370 h340 M86 410 h340 M86 450 h340"/>
<path d="M176 370 l-50 100 M256 370 v100 M336 370 l50 100"/>
</g>
<rect x="186" y="140" width="140" height="100" rx="26" fill="#0f0a1e" stroke="#f5d0fe" stroke-width="8"/>
<circle cx="222" cy="190" r="15" fill="#f5d0fe"/>
<circle cx="290" cy="190" r="15" fill="#f5d0fe"/>
<rect x="246" y="96" width="20" height="44" rx="10" fill="#f5d0fe"/>
<circle cx="256" cy="88" r="14" fill="#e879f9"/>
</svg>'''

PWA_SERVICE_WORKER = '''
const CACHE = 'vasanth-ai-v14';
const CORE = ['/', '/manifest.json', '/logo.png'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (['/command','/tts','/vision','/history','/clear','/change-voice','/mood','/screenshot','/gesture/on','/gesture/off','/gesture/status'].includes(url.pathname)) return;
  e.respondWith(fetch(e.request).then((res) => { if (res.ok) { const clone = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, clone)); } return res; }).catch(() => caches.match(e.request).then((m) => m || caches.match('/'))));
});
'''

def load_history():
    global conversation_history
    try:
        if not os.path.exists(HISTORY_FILE):
            conversation_history = []; return
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        conversation_history = data[-MAX_HISTORY_MESSAGES:] if isinstance(data, list) else []
    except Exception as error:
        print("History load error:", error); conversation_history = []

def save_history():
    try:
        temp_file = HISTORY_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(conversation_history[-MAX_HISTORY_MESSAGES:], file, ensure_ascii=False, indent=2)
        os.replace(temp_file, HISTORY_FILE)
    except Exception as error:
        print("History save error:", error)

def clear_memory():
    global conversation_history
    conversation_history = []
    try:
        if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
    except Exception as error:
        print("History delete error:", error)

def add_to_memory(role, text):
    global conversation_history, LAST_USER_ACTIVITY
    LAST_USER_ACTIVITY = time.time()
    conversation_history.append({"role": role, "text": text})
    if len(conversation_history) > MAX_HISTORY_MESSAGES:
        conversation_history = conversation_history[-MAX_HISTORY_MESSAGES:]
    save_history()

def get_openai_history():
    messages = []
    for message in conversation_history:
        role = message.get("role", "user"); text = message.get("text", "")
        if not text: continue
        if role == "user": messages.append({"role": "user", "content": text})
        elif role == "model": messages.append({"role": "assistant", "content": text})
    return messages

def load_reminders():
    if not os.path.exists(REMINDERS_FILE): return []
    try:
        with open(REMINDERS_FILE, "r") as f: return json.load(f)
    except: return []

def save_reminders(data):
    try:
        with open(REMINDERS_FILE, "w") as f: json.dump(data, f, indent=2)
    except: pass

def play_mp3_native(path):
    """Play MP3/WAV silently using Windows MCI (NO popup dialog!)"""
    try:
        winmm = ctypes.windll.winmm
        winmm.mciSendStringW('close vasanth_audio', None, 0, 0)
        winmm.mciSendStringW(f'open "{path}" alias vasanth_audio', None, 0, 0)
        winmm.mciSendStringW('play vasanth_audio', None, 0, 0)
        print(f"🔊 Native play: {os.path.basename(path)}")
    except Exception as e:
        print(f"Native play error: {e}")
        os.system(f'start "" "{path}"')

def save_audio_file(audio_buffer, mime, base_name):
    """Save audio buffer with correct extension, return path"""
    ext = "wav" if mime == "audio/wav" else "mp3"
    path = os.path.join(DATA_DIR, f"{base_name}.{ext}")
    with open(path, "wb") as f:
        f.write(audio_buffer.read())
    return path

def reminder_checker_thread():
    while True:
        time.sleep(10)
        reminders = load_reminders()
        now = time.time(); updated = False
        for r in reminders:
            if not r.get("done") and r["trigger_time"] <= now:
                print(f"⏰ TRIGGERING REMINDER: {r['message']}")
                r["done"] = True; updated = True
                try:
                    alert_text = f"Macha! Un reminder time aayiduchu: {r['message']}"
                    audio_buffer, error, mime = generate_tts(alert_text)
                    if audio_buffer:
                        alert_path = save_audio_file(audio_buffer, mime, "reminder_alert")
                        play_mp3_native(alert_path)
                except Exception as e:
                    print("Alert audio error:", e)
        if updated: save_reminders(reminders)

def load_long_memory():
    if not os.path.exists(MEMORY_FILE): return {"facts": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"facts": []}

def save_long_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e: print("Memory save error:", e)

def get_memory_context():
    mem = load_long_memory()
    if not mem["facts"]: return ""
    return ("\nLONG-TERM MEMORY (things you REMEMBER about Vasanth):\n- " + "\n- ".join(mem["facts"][-50:]) + "\nUse these naturally when relevant.\n")

def build_system():
    return SYSTEM_PROMPT + get_memory_context() + get_mood_context()

def extract_and_store_memories(user_text):
    try:
        prompt = (f"Extract personal facts about the user. Return ONLY a valid JSON array of short fact strings. If none, return [].\nMessage: {user_text}")
        messages = [{"role":"system","content":"You extract personal facts. Return ONLY a valid JSON array."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        if not reply: return
        m = re.search(r'\[.*\]', reply, re.DOTALL)
        if not m: return
        facts = json.loads(m.group(0))
        if not isinstance(facts, list) or not facts: return
        mem = load_long_memory(); added = 0
        for f in facts:
            if isinstance(f, str) and f.strip() and f not in mem["facts"]:
                mem["facts"].append(f.strip()); added += 1
        mem["facts"] = mem["facts"][-100:]
        save_long_memory(mem)
        if added: print(f"🧠 Stored {added} new memories!")
    except Exception as e:
        print(f"Memory extract error: {e}")

def generate_image(prompt):
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=640&height=640&nologo=true"
        print(f"🎨 Image generating: {prompt[:50]}...")
        return url
    except Exception as e:
        print(f"Image error: {e}")
        return None

def summarize_youtube(url):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        m = re.search(r'(?:v=|youtu\.be/)([\w-]{11})', url)
        if not m: return "YouTube link sari illa macha 🔗"
        vid = m.group(1)
        try:
            data = YouTubeTranscriptApi.get_transcript(vid)
        except Exception:
            data = YouTubeTranscriptApi().fetch(vid)
        full = " ".join([t["text"] for t in data])[:6000]
        if not full.strip(): return "Transcript kidaikkala macha"
        prompt = f"Summarize this YouTube video transcript in spoken Tamil (Tanglish). Give 4-6 bullet points. Call user 'macha'.\n\nTranscript: {full}"
        messages = [{"role":"system","content":"You are Vasanth AI. Summarize in natural Tamil."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Summary edukka mudiyala macha"
    except Exception as e:
        print(f"YT error: {e}")
        return f"YouTube summary edukka mudiyala: {e}"

def get_weather_now():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=13.0827&longitude=80.2707&current=temperature_2m,weather_code,precipitation&hourly=precipitation_probability&forecast_days=1", timeout=10)
        d = r.json()
        cur = d.get("current", {})
        temp = cur.get("temperature_2m")
        hourly = d.get("hourly", {}).get("precipitation_probability", [])
        max_rain = max(hourly) if hourly else 0
        return temp, max_rain
    except Exception as e:
        print(f"Weather error: {e}")
        return None, 0

def weather_report():
    temp, rain = get_weather_now()
    if temp is None: return smart_web_search("Chennai weather today temperature")
    rain_note = "— umbrella venum macha! 🌂" if rain >= 50 else "— problem illa! ☀️"
    return f"Macha! Chennai ippo **{temp}°C** iruku. Mazhai chance **{rain}%** {rain_note}"

def take_screenshot():
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"ss_{timestamp}.png")
        try:
            if not PYAUTOGUI_READY: raise Exception("pyautogui not ready")
            pyautogui.screenshot().save(path)
        except Exception as e1:
            print(f"pyautogui failed ({e1}), trying mss...")
            import mss
            with mss.mss() as sct: sct.shot(output=path)
        with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        print(f"📸 Screenshot saved: {path}")
        return f"data:image/png;base64,{b64}", path
    except Exception as e:
        print(f"Screenshot error: {e}")
        return None, str(e)

def run_shell_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip() or result.stderr.strip() or "Command executed"
        return f"Command run panniten macha 💻\n{output[:500]}"
    except subprocess.TimeoutExpired:
        return "Command timeout aachu macha ⏰"
    except Exception as e:
        return f"Command error: {e}"

def file_operation(action, src, dst=None):
    try:
        if src: src = os.path.expanduser(src)
        if dst: dst = os.path.expanduser(dst)
        if action == "delete":
            if os.path.isdir(src): shutil.rmtree(src)
            else: os.remove(src)
            return f"Delete panniten: {src} 🗑️"
        elif action == "copy":
            if os.path.isdir(src): shutil.copytree(src, dst)
            else: shutil.copy(src, dst)
            return f"Copy panniten: {src} → {dst} 📄"
        elif action == "move":
            shutil.move(src, dst); return f"Move panniten: {src} → {dst} 📦"
        elif action == "rename":
            os.rename(src, dst); return f"Rename panniten: {src} → {dst} ✏️"
        elif action == "create_folder":
            os.makedirs(src, exist_ok=True); return f"Folder create panniten: {src} 📁"
        elif action == "list":
            target = src if os.path.isdir(src) else os.path.dirname(src) or "."
            items = os.listdir(target); return f"Files ({len(items)}): {', '.join(items[:20])} 📂"
    except Exception as e:
        return f"File error: {e}"

def window_control(action, title=None):
    try:
        if not PYGETWINDOW_READY: return "pygetwindow not installed"
        if action == "minimize_all":
            pyautogui.hotkey('win','d'); return "Ellam windows minimize panniten 🗔"
        if action == "close_all":
            count=0
            for w in gw.getAllWindows():
                if w.title.strip():
                    try: w.close(); count+=1
                    except: pass
            return f"{count} windows close panniten ❌"
        windows = gw.getWindowsWithTitle(title) if title else gw.getAllWindows()
        if not windows: return f"Window '{title}' kaanala macha"
        w = windows[0]
        if action=="close": w.close()
        elif action=="minimize": w.minimize()
        elif action=="maximize": w.maximize()
        elif action=="activate": w.activate()
        return f"Window '{title}' {action} panniten 🗔"
    except Exception as e:
        return f"Window error: {e}"

def process_control(action, name=None):
    try:
        if action == "list":
            procs = [p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']][:30]
            return f"Running processes: {', '.join(procs)} ⚙️"
        elif action == "kill":
            killed=0
            for p in psutil.process_iter(['name']):
                if name and name.lower() in (p.info['name'] or '').lower():
                    p.kill(); killed+=1
            return f"{killed} process kill panniten ☠️" if killed else f"'{name}' process kaanala"
    except Exception as e:
        return f"Process error: {e}"

def clipboard_control(action, text=None):
    try:
        if not PYPERCLIP_READY: return "pyperclip not installed"
        if action == "copy":
            pyperclip.copy(text); return f"Clipboard-ல copy panniten 📋: {text[:50]}"
        elif action == "paste":
            return f"Clipboard content: {pyperclip.paste()[:200]} 📋"
    except Exception as e:
        return f"Clipboard error: {e}"

def power_control(action):
    if action == "lock":
        ctypes.windll.user32.LockWorkStation(); return "PC lock panniten 🔒"
    elif action == "sleep":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"); return "Sleep mode-ku anuppen 💤"
    elif action == "shutdown":
        os.system("shutdown /s /t 10"); return "10 sec-ல் shutdown 🔌"
    elif action == "restart":
        os.system("shutdown /r /t 10"); return "10 sec-ல் restart 🔄"
    return "Power command puriyala"

def click_at(x, y):
    try:
        if not PYAUTOGUI_READY: return "pyautogui not installed"
        if x == "center" or x is None:
            s = pyautogui.size(); x, y = s[0]//2, s[1]//2
        else: x, y = int(x), int(y)
        pyautogui.moveTo(x, y, duration=0.3); pyautogui.click()
        return f"Click panniten macha at ({x}, {y}) 🖱️"
    except Exception as e: return f"Click error: {e}"

def type_text(text):
    try:
        if not PYAUTOGUI_READY: return "pyautogui not installed"
        time.sleep(0.3); pyautogui.write(text, interval=0.03)
        return f"Type panniten macha: {text[:30]}... ⌨️"
    except Exception as e: return f"Type error: {e}"

def scroll_screen(direction, amount=3):
    try:
        if not PYAUTOGUI_READY: return "pyautogui not installed"
        pyautogui.scroll(int(amount) if direction=="up" else -int(amount))
        return f"Scroll {direction} panniten macha 📜"
    except Exception as e: return f"Scroll error: {e}"

def mouse_position():
    try:
        if not PYAUTOGUI_READY: return "pyautogui not installed"
        x, y = pyautogui.position(); return f"Mouse position: ({x}, {y}) 🖱️"
    except Exception as e: return f"Position error: {e}"

GESTURE_ENABLED = False
LAST_GESTURE = {"gesture": "none", "timestamp": 0}

def set_gesture(g):
    global LAST_GESTURE
    LAST_GESTURE = {"gesture": g, "timestamp": time.time()}
    print(f"✋ Gesture detected: {g}")

def _count_fingers(lm):
    tips=[8,12,16,20]; pips=[6,10,14,18]; n=0
    for t,p in zip(tips,pips):
        if lm[t].y < lm[p].y: n+=1
    return n

def _thumb_up(lm): return lm[4].y < lm[2].y and lm[4].y < lm[17].y
def _thumb_down(lm): return lm[4].y > lm[2].y and lm[4].y > lm[5].y

def _do_gesture(g):
    if g=="thumbs_up": control_volume("volume_up")
    elif g=="thumbs_down": control_volume("volume_down")
    elif g=="open_palm": control_media("media_play_pause")
    elif g=="fist": control_volume("mute")
    elif g=="peace": control_media("media_next")

def gesture_loop():
    global GESTURE_ENABLED
    import cv2
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.6)
    mp_draw = mp.solutions.drawing_utils
    cap = cv2.VideoCapture(0)
    last_action = 0
    while GESTURE_ENABLED:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)
        gesture = "none"
        if res.multi_hand_landmarks:
            for hl in res.multi_hand_landmarks:
                lm = hl.landmark
                mp_draw.draw_landmarks(frame, hl, mp_hands.HAND_CONNECTIONS)
                f = _count_fingers(lm)
                if _thumb_up(lm) and f<=1: gesture="thumbs_up"
                elif _thumb_down(lm) and f<=1: gesture="thumbs_down"
                elif f==5: gesture="open_palm"
                elif f==0: gesture="fist"
                elif f==2: gesture="peace"
        if gesture!="none" and (time.time()-last_action)>1.5:
            last_action = time.time()
            set_gesture(gesture)
            _do_gesture(gesture)
        cv2.imshow("Vasanth Gesture (Q to quit)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            GESTURE_ENABLED=False; break
    cap.release()
    cv2.destroyAllWindows()

def launch_app(app_name):
    apps = {"chrome":"chrome","google chrome":"chrome","firefox":"firefox","vscode":"code","vs code":"code","code":"code","notepad":"notepad","paint":"mspaint","calculator":"calc","spotify":"spotify","telegram":"telegram","whatsapp":"whatsapp","vlc":"vlc","word":"winword","excel":"excel","powerpoint":"powerpnt","edge":"msedge"}
    cmd = apps.get(app_name, app_name)
    try:
        os.system(f'start {cmd}')
        return f"{app_name.capitalize()} open panniten macha 🚀"
    except Exception:
        return f"{app_name} open panna mudiyala macha."

def get_cricket_score(query=""):
    try:
        print(f"\n🏏 CRICKET QUERY: {query}")
        try:
            response = requests.get("https://api.cricapi.com/v1/currentMatches?apikey=free", timeout=10)
            if response.status_code == 200:
                matches = response.json().get("data", [])
                if not matches: return smart_web_search(query + " cricket score")
                live_match=None; recent_match=None
                for match in matches:
                    status = match.get("status","").lower()
                    if "live" in status or "in progress" in status: live_match=match; break
                    elif "completed" in status or "result" in status:
                        if not recent_match: recent_match=match
                target = live_match or recent_match
                if target:
                    teams=target.get("teams",[]); score=target.get("score",[])
                    status=target.get("status","Match in progress"); venue=target.get("venue","")
                    rt=f"🏏 {status}\n\n"
                    if len(teams)>=2: rt+=f"**{teams[0]}** vs **{teams[1]}**\n\n"
                    for i,s in enumerate(score[:2]):
                        rt+=f"📊 {s.get('inning',f'Innings {i+1}')}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} overs)\n"
                    if venue: rt+=f"\n📍 {venue}"
                    return f"Macha! {rt}"
        except Exception as e: print(f"Cricket API error: {e}")
        return smart_web_search(query if query else "India cricket live score today")
    except Exception as e:
        print(f"Cricket error: {e}")
        return "Macha, cricket score edukka mudiyala. Try again later!"

def _groq_complete(messages):
    if groq_client is None:
        return None
    models_to_try = [GROQ_MODEL, "qwen/qwen3.6-27b", "openai/gpt-oss-20b", "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant", "gemma2-9b-it", "llama3-8b-8192"]
    for model in models_to_try:
        try:
            response = groq_client.chat.completions.create(model=model, messages=messages)
            reply = clean_think(response.choices[0].message.content.strip())
            set_brain("⚡ Groq"); return reply
        except Exception as e:
            err_str = str(e)
            if any(k in err_str for k in ["429","rate_limit","404","decommission","connect","network","unreachable","refused","timeout"]): continue
            raise e
    if AWS_READY:
        r = ask_bedrock(messages)
        if r: return r
    if OLLAMA_READY:
        r = ask_ollama(messages)
        if r: return r
    return None

def ask_bedrock(messages):
    if not AWS_READY: return None
    try:
        client = boto3.client("bedrock-runtime", region_name=AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        system = [{"text": m["content"]} for m in messages if m["role"]=="system"]
        conv_msgs = [{"role": m["role"], "content":[{"text": m["content"]}]} for m in messages if m["role"] in ("user","assistant")]
        for mid in ["amazon.nova-lite-v1:0","amazon.nova-micro-v1:0","meta.llama3-1-8b-instruct-v1:0","anthropic.claude-3-haiku-20240307-v1:0"]:
            try:
                kwargs = {"modelId": mid, "messages": conv_msgs, "inferenceConfig": {"maxTokens": 1024}}
                if system: kwargs["system"] = system
                resp = client.converse(**kwargs)
                reply = clean_think(resp["output"]["message"]["content"][0]["text"].strip())
                set_brain("☁️ AWS"); print(f"🧠 BEDROCK ({mid}) replied!")
                return reply
            except Exception as e: print(f"Bedrock {mid} error: {e}"); continue
        return None
    except Exception as e:
        print(f"BEDROCK ERROR: {e}"); return None

OLLAMA_MODEL = "llama3.1"
ollama_client = None
OLLAMA_READY = False
try:
    ollama_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    ollama_client.models.list(); OLLAMA_READY = True
except Exception:
    OLLAMA_READY = False

def ask_ollama(messages):
    if not OLLAMA_READY: return None
    for model in [OLLAMA_MODEL, "llama3.2:3b", "qwen2.5:3b"]:
        try:
            response = ollama_client.chat.completions.create(model=model, messages=messages)
            reply = clean_think(response.choices[0].message.content.strip())
            set_brain("🖥️ Ollama"); print(f"🖥️ OLLAMA ({model}) replied (OFFLINE)!")
            return reply
        except Exception as e: print(f"Ollama {model} error: {e}"); continue
    return None

def smart_web_search(query):
    try:
        print(f"\n🔍 Smart Web Search: {query}")
        results = []
        for search_q in [query, f"{query} latest", f"{query} 2026"]:
            try:
                with DDGS() as ddgs:
                    sr = list(ddgs.text(search_q, max_results=5))
                    if sr:
                        for r in sr[:3]: results.append(f"Title: {r.get('title','')}\nInfo: {r.get('body','')}")
                        break
            except: continue
        if not results:
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
            return f"Macha, Google-la '{query}' open panniruken. 🌐"
        context = "\n\n".join(results[:3])
        summary_prompt = f"Summarize this in 3 sentences in spoken Tamil (Tanglish ok). Call user 'macha'.\n\nResults: {context}\nQuestion: {query}"
        messages = [{"role":"system","content":"You are Vasanth AI. Summarize search results in natural spoken Tamil."},{"role":"user","content":summary_prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Macha, AI daily limit mudinjiduchu."
    except Exception as error:
        print(f"Search Error: {error}")
        return f"Macha, search-la problem."

def generate_morning_briefing():
    try:
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %d %B %Y"); time_str = now.strftime("%I:%M %p")
        weather = weather_report()
        news = smart_web_search("latest Tamil news headlines today")
        prompt = f"Give a friendly morning briefing in spoken Tamil. Include date ({date_str}), time ({time_str}), weather ({weather}), and 2 news headlines ({news}). Keep it under 8 sentences."
        messages = [{"role":"system","content":build_system()},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else f"Good morning macha! ☀️ Ippo time {time_str}."
    except Exception as e:
        print(f"Briefing error: {e}")
        return f"Good morning macha! ☀️ Briefing-ku internet problem."

def control_volume(action):
    try:
        keys = {"volume_up":0xAF,"volume_down":0xAE,"mute":0xAD}
        key = keys.get(action)
        if key:
            for _ in range(5 if action != "mute" else 1):
                ctypes.windll.user32.keybd_event(key,0,0,0); ctypes.windll.user32.keybd_event(key,0,2,0)
                if action != "mute": time.sleep(0.05)
            names = {"volume_up":"Volume increase","volume_down":"Volume decrease","mute":"Mute"}
            return f"{names[action]} panniten macha 🔊"
    except: pass
    return "Volume control-la problem macha."

def control_media(action):
    try:
        keys = {"media_play_pause":0xB3,"media_next":0xB0,"media_prev":0xB1}
        key = keys.get(action)
        if key:
            ctypes.windll.user32.keybd_event(key,0,0,0); ctypes.windll.user32.keybd_event(key,0,2,0)
            names = {"media_play_pause":"Play/Pause","media_next":"Next","media_prev":"Previous"}
            return f"{names[action]} button press panniten macha 🎵"
    except: pass
    return "Media control work aagala macha."

def control_brightness(action):
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()[0]
        new_val = min(100, current+20) if action=="brightness_up" else max(10, current-20)
        sbc.set_brightness(new_val)
        return f"Brightness {new_val}% ku set panniten macha ☀️"
    except:
        return "Brightness control-la problem macha."

def get_system_stats(stat):
    try:
        if stat=="battery":
            battery = psutil.sensors_battery()
            if battery: return f"Battery ippo {battery.percent}% iruku macha. {'Charging aagudhu' if battery.power_plugged else 'Discharge aagudhu'} 🔋"
            return "Battery sensor kidaikkala macha (Desktop-a irukalam)."
        elif stat=="cpu": return f"CPU usage ippo {psutil.cpu_percent(interval=1)}% iruku macha ⚙️"
        elif stat=="ram":
            ram = psutil.virtual_memory()
            return f"RAM-la {ram.used/(1024**3):.1f} GB use aagudhu, total {ram.total/(1024**3):.1f} GB iruku macha 💾"
    except: pass
    return "Stats edukka mudiyala macha."

def open_folder(folder_name):
    paths = {"downloads":os.path.expanduser("~/Downloads"),"documents":os.path.expanduser("~/Documents"),"desktop":os.path.expanduser("~/Desktop"),"pictures":os.path.expanduser("~/Pictures"),"videos":os.path.expanduser("~/Videos")}
    path = paths.get(folder_name)
    if path and os.path.exists(path):
        os.startfile(path); return f"{folder_name.capitalize()} folder open panniten macha 📂"
    return "Folder kidaikkala macha."

def set_reminder(minutes, message):
    try:
        minutes = int(minutes); trigger_time = time.time() + (minutes*60)
        reminders = load_reminders()
        reminders.append({"message":message,"trigger_time":trigger_time,"done":False})
        save_reminders(reminders)
        return f"Reminder set panniten macha! {minutes} minutes la voice alert varum. ⏰"
    except:
        return "Reminder set panna mudiyala macha."

def run_python_safely(code_string):
    try:
        result = subprocess.run([sys.executable,"-c",code_string.strip()],capture_output=True,text=True,timeout=5,encoding='utf-8')
        if result.returncode==0: return result.stdout.strip() or "Code ran but printed nothing."
        else: return f"Error: {result.stderr.strip().split(chr(10))[-1]}"
    except subprocess.TimeoutExpired: return "Error: Code took too long."
    except Exception as e: return f"Error: {str(e)}"

def ask_groq(user_text):
    if groq_client is None and not AWS_READY and not OLLAMA_READY:
        return "மச்சா 😅 AI API keys கிடைக்கவில்லை."
    models_to_try = [GROQ_MODEL,"qwen/qwen3.6-27b","openai/gpt-oss-20b","meta-llama/llama-4-scout-17b-16e-instruct","llama-3.1-8b-instant","gemma2-9b-it","llama3-8b-8192"]
    if groq_client:
        for model in models_to_try:
            try:
                print(f"\n========== GROQ TEXT ({model}) ==========\nUser: {user_text}\n===============================")
                messages = [{"role":"system","content":build_system()}]
                messages.extend(get_openai_history())
                messages.append({"role":"user","content":user_text})
                response = groq_client.chat.completions.create(model=model, messages=messages)
                content = response.choices[0].message.content
                reply = clean_think(content.strip() if content else "")
                set_brain("⚡ Groq")
                add_to_memory("user", user_text); add_to_memory("model", reply)
                return reply
            except Exception as error:
                error_str = str(error)
                print(f"GROQ ERROR ({model}): {error_str}")
                if any(k in error_str.lower() for k in ["429","rate_limit","404","decommission","connect","network","unreachable","refused","timeout","dns","resolve"]): continue
                return "மச்சா 😅 Groq AI-ல ஒரு பிரச்சனை வந்திருக்கு."
    if AWS_READY:
        print("\n⚠️ All Groq models failed. Switching to AWS Bedrock...")
        messages = [{"role":"system","content":build_system()}]
        messages.extend(get_openai_history()); messages.append({"role":"user","content":user_text})
        bedrock_reply = ask_bedrock(messages)
        if bedrock_reply:
            add_to_memory("user", user_text); add_to_memory("model", bedrock_reply)
            return bedrock_reply
    if OLLAMA_READY:
        print("\n🖥️ Switching to LOCAL Ollama (OFFLINE MODE)...")
        messages = [{"role":"system","content":build_system()}]
        messages.extend(get_openai_history()); messages.append({"role":"user","content":user_text})
        ollama_reply = ask_ollama(messages)
        if ollama_reply:
            add_to_memory("user", user_text); add_to_memory("model", ollama_reply)
            return ollama_reply
    return "மச்சா 😅 Groq + AWS + Local ellam down. 5 mins la try pannunga."

# ============================================================
# 🥇 TTS ENGINE (Gemini MP3 -> Google -> Edge) - NO FFMPEG NEEDED
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def pcm_to_wav(pcm_bytes, rate=24000):
    import wave
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()

def pcm_to_mp3(pcm_bytes, rate=24000):
    """Convert PCM to MP3 using lameenc (pure Python, NO ffmpeg/DLL needed!)"""
    if LAMEENC_READY:
        try:
            enc = lameenc.Encoder()
            enc.set_bit_rate(128)
            enc.set_in_sample_rate(rate)
            enc.set_channels(1)
            enc.set_quality(2)
            mp3_data = enc.encode(pcm_bytes) + enc.flush()
            buf = io.BytesIO(mp3_data)
            buf.seek(0)
            print(f"🎵 LAME MP3 encoded ({len(mp3_data)} bytes) - NO FFMPEG!")
            return buf
        except Exception as e:
            print(f"⚠️ lameenc failed: {e}")
    if PYDUB_READY:
        try:
            wav_bytes = pcm_to_wav(pcm_bytes, rate)
            audio = AudioSegment.from_wav(io.BytesIO(wav_bytes))
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format="mp3", bitrate="128k")
            mp3_io.seek(0)
            print(f"🎵 Pydub MP3 ({mp3_io.getbuffer().nbytes} bytes)")
            return mp3_io
        except Exception as e:
            print(f"⚠️ Pydub failed: {e}")
    return None

def gemini_tts(text):
    """Gemini TTS (most natural). Returns (buffer, mime) or None."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Leda")
                    )
                )
            )
        )
        part = resp.candidates[0].content.parts[0]
        pcm = part.inline_data.data
        rate = 24000
        mime = getattr(part.inline_data, "mime_type", "") or ""
        if "rate=" in mime:
            try: rate = int(mime.split("rate=")[1].split(";")[0])
            except: rate = 24000
        
        # MP3 first (browser-friendly)
        mp3_buf = pcm_to_mp3(pcm, rate)
        if mp3_buf:
            print(f"🥇 Gemini TTS success (MP3, {mp3_buf.getbuffer().nbytes} bytes) - NATURAL!")
            return mp3_buf, "audio/mpeg"
        
        # WAV fallback
        wav_bytes = pcm_to_wav(pcm, rate)
        buf = io.BytesIO(wav_bytes); buf.seek(0)
        print(f"🥇 Gemini TTS success (WAV, {len(wav_bytes)} bytes)")
        return buf, "audio/wav"
    except Exception as e:
        print(f"⚠️ Gemini TTS failed: {e}")
        return None

def google_tts(text):
    """Google Translate TTS (unlimited, native MP3)"""
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=text, lang='ta', slow=False).write_to_fp(buf)
        buf.seek(0)
        if buf.getbuffer().nbytes > 0:
            print("✅ Google TTS success (MP3, unlimited)")
            return buf
    except Exception as e:
        print(f"⚠️ Google TTS failed: {e}")
    return None

EMOJI_PATTERN = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E6-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+", flags=re.UNICODE)

def clean_text_for_tts(text):
    text = EMOJI_PATTERN.sub(" ", str(text))
    text = re.sub(r"[*_#`>\[\]]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000] if len(text) > 5000 else text

async def _generate_edge_tts_async(text):
    global EDGE_TTS_VOICE
    try:
        voice_to_use = EDGE_TTS_VOICE
        print(f"🎙️ Trying voice: {voice_to_use} (rate={EDGE_TTS_RATE}, pitch={EDGE_TTS_PITCH})")
        try:
            communicate = edge_tts.Communicate(text, voice_to_use, rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH, volume=EDGE_TTS_VOLUME)
            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk.get("type")=="audio": audio_buffer.write(chunk.get("data", b""))
            audio_buffer.seek(0)
            if audio_buffer.getbuffer().nbytes == 0: raise Exception("Empty audio buffer")
            print(f"✅ Voice {voice_to_use} success ({audio_buffer.getbuffer().nbytes} bytes)")
            return audio_buffer
        except Exception as first_error:
            print(f"⚠️ Voice {voice_to_use} failed: {first_error}")
            if voice_to_use != "ta-IN-PallaviNeural":
                print("🔄 Falling back to Pallavi...")
                EDGE_TTS_VOICE = "ta-IN-PallaviNeural"
                communicate = edge_tts.Communicate(text, "ta-IN-PallaviNeural", rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH, volume=EDGE_TTS_VOLUME)
                audio_buffer = io.BytesIO()
                async for chunk in communicate.stream():
                    if chunk.get("type")=="audio": audio_buffer.write(chunk.get("data", b""))
                audio_buffer.seek(0)
                print("✅ Fallback to Pallavi success")
                return audio_buffer
            else: raise first_error
    except Exception as e:
        print(f"❌ Edge TTS error: {e}"); raise

def generate_tts(text):
    """Cascade: Gemini (BEST MP3) -> Google (MP3) -> Edge (MP3). Returns (buffer, error, mime)."""
    try:
        cleaned_text = clean_text_for_tts(text)
        if not cleaned_text:
            return None, "No speakable text", "audio/mpeg"
        
        # 1) GEMINI (best natural voice, MP3 via lameenc)
        result = gemini_tts(cleaned_text)
        if result:
            buf, mime = result
            return buf, None, mime
        
        # 2) GOOGLE (unlimited, native MP3)
        buf = google_tts(cleaned_text)
        if buf:
            return buf, None, "audio/mpeg"
        
        # 3) EDGE (unlimited, native MP3)
        buf = asyncio.run(_generate_edge_tts_async(cleaned_text))
        if buf and buf.getbuffer().nbytes > 0:
            return buf, None, "audio/mpeg"
        
        return None, "All TTS failed", "audio/mpeg"
    except Exception as error:
        print(f"❌ TTS ERROR: {error}")
        return None, f"TTS error: {error}", "audio/mpeg"

def proactive_speak(text):
    global LAST_PROACTIVE_SPEAK
    try:
        print(f"🔮 PROACTIVE: {text[:60]}...")
        LAST_PROACTIVE_SPEAK = time.time()
        add_to_memory("model", f"[proactive] {text}")
        audio_buffer, error, mime = generate_tts(text)
        if audio_buffer is None:
            print(f"Proactive TTS failed: {error}")
            return False
        path = save_audio_file(audio_buffer, mime, "proactive")
        play_mp3_native(path)
        return True
    except Exception as e:
        print(f"Proactive speak error: {e}")
        return False

def proactive_thread():
    global MORNING_GREETED_TODAY, EVENING_GREETED_TODAY, LAST_PROACTIVE_SPEAK, WEATHER_ALERTED_TODAY
    time.sleep(15)
    while True:
        try:
            time.sleep(30)
            now = datetime.datetime.now()
            current_hour = now.hour
            today = now.strftime("%Y-%m-%d")
            idle_time = time.time() - LAST_USER_ACTIVITY
            since_last = time.time() - LAST_PROACTIVE_SPEAK
            if idle_time < 60: continue
            if since_last < 300: continue
            temp, rain = get_weather_now()
            if rain >= 60 and WEATHER_ALERTED_TODAY != today:
                WEATHER_ALERTED_TODAY = today
                proactive_speak(f"Macha! Innaiku {rain}% chance mazhai varum! Umbrella edunga! 🌂")
                continue
            if 7 <= current_hour <= 11 and MORNING_GREETED_TODAY != today:
                MORNING_GREETED_TODAY = today
                proactive_speak(f"Good morning macha! ☀️ Ippo time {now.strftime('%I:%M %p')}. {weather_report()}")
                continue
            if 19 <= current_hour <= 21 and EVENING_GREETED_TODAY != today:
                EVENING_GREETED_TODAY = today
                proactive_speak(f"Good evening macha! 🌙 Ippo time {now.strftime('%I:%M %p')}. Long day ah? Coffee sapdringala?")
                continue
            if 1800 <= idle_time <= 3600:
                import random
                proactive_speak(random.choice([
                    "Macha, 30 minutes aachu... oru break eduthu thanni kudiyunga! 💧",
                    "Hey macha, romba neram aachu! Eyes rest pannunga... 🌿",
                    "Macha, stretch pannunga! Back health mukkiyam! 🧘",
                ]))
                continue
            reminders = load_reminders(); now_ts = time.time()
            for r in reminders:
                if not r.get("done") and 0 < (r["trigger_time"] - now_ts) <= 120:
                    proactive_speak(f"Macha! Oru reminder varuthu 2 minutes-ல: {r['message']}")
                    break
        except Exception as e:
            print(f"Proactive error: {e}")
            time.sleep(30)

def strip_img_token(text):
    """FIXED: None-safe"""
    if not text:
        return "", None
    text = str(text)
    m = re.search(r'\[\[IMG:(.*?)\]\]', text)
    if m: return text.replace(m.group(0), "").strip(), m.group(1)
    return text, None

def process_command(original_text):
    global LAST_USER_ACTIVITY
    text = original_text.lower()
    LAST_USER_ACTIVITY = time.time()
    if not original_text: return "மச்சா 😅 ஏதாவது type பண்ணு."
    threading.Thread(target=extract_and_store_memories, args=(original_text,), daemon=True).start()
    threading.Thread(target=detect_emotion, args=(original_text,), daemon=True).start()

    if text in ["good morning","morning","briefing","kaalai vanakkam"]:
        reply = generate_morning_briefing(); add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["youtube","open youtube"]:
        webbrowser.open("https://www.youtube.com"); reply = "YouTube open பண்ணிட்டேன் மச்சா 🎵"; add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["google","open google"]:
        webbrowser.open("https://www.google.com"); reply = "Google open பண்ணிட்டேன் மச்சா 🌐"; add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["calculator","open calculator"]:
        os.system("start calc.exe"); reply = "Calculator open பண்ணிட்டேன் மச்சா 🧮"; add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["time","what is the time","current time","time sollu"]:
        reply = f"இப்போ நேரம் {datetime.datetime.now().strftime('%I:%M %p')} மச்சா ⏰"; add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["weather","weather enna","mazhiya","weather update"]:
        reply = weather_report(); add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["screenshot","take screenshot","screen capture","screen eduppu"]:
        data_url, info = take_screenshot()
        reply = f"Screenshot eduthuten macha! 📸 File: {info}" if data_url else f"Screenshot edukka mudiyala: {info}"
        add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if text in ["mouse position","where is mouse","mouse eng"]:
        reply = mouse_position(); add_to_memory("user", original_text); add_to_memory("model", reply); return reply

    yt_link = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s]+)', original_text)
    if yt_link:
        reply = summarize_youtube(yt_link.group(1)); add_to_memory("user", original_text); add_to_memory("model", reply); return reply

    ai_reply = ask_groq(original_text)
    # FIXED: None-safety
    if not ai_reply:
        ai_reply = "மச்சா 😅 AI-க்கு ஒரு chinna issue. Thirumba try pannunga."
    final_reply = ai_reply

    code_match = re.search(r'\[CODE\](.*?)\[/CODE\]', ai_reply, re.DOTALL | re.IGNORECASE)
    if code_match:
        execution_result = run_python_safely(code_match.group(1).strip())
        final_reply = ai_reply.replace(code_match.group(0), f"\n\n**Answer:** `{execution_result}`")
        add_to_memory("user", original_text); add_to_memory("model", final_reply); return final_reply

    image_match = re.search(r'\[IMAGE:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    yt_match = re.search(r'\[YT:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    weather_match = re.search(r'\[WEATHER\]', ai_reply, re.IGNORECASE)
    play_match = re.search(r'\[PLAY:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    search_match = re.search(r'\[SEARCH:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    open_match = re.search(r'\[OPEN:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    action_match = re.search(r'\[ACTION:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    reminder_match = re.search(r'\[REMINDER:\s*(.*?)\|(.*?)\]', ai_reply, re.IGNORECASE)
    system_match = re.search(r'\[SYSTEM:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    folder_match = re.search(r'\[FOLDER:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    app_match = re.search(r'\[APP:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    cricket_match = re.search(r'\[CRICKET:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    screenshot_match = re.search(r'\[SCREENSHOT\]', ai_reply, re.IGNORECASE)
    click_match = re.search(r'\[CLICK:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    type_match = re.search(r'\[TYPE:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    scroll_match = re.search(r'\[SCROLL:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    cmd_match = re.search(r'\[CMD:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    file_match = re.search(r'\[FILE:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    window_match = re.search(r'\[WINDOW:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    process_match = re.search(r'\[PROCESS:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    clip_match = re.search(r'\[CLIP:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    power_match = re.search(r'\[POWER:\s*(.*?)\]', ai_reply, re.IGNORECASE)

    if image_match:
        img_url = generate_image(image_match.group(1).strip())
        final_reply = f"Image create panniten macha! 🎨 (loading...)\n[[IMG:{img_url}]]" if img_url else "Image generate panna mudiyala macha 😅"
        conversation_history[-1]["text"] = final_reply; save_history()
    elif yt_match:
        final_reply = summarize_youtube(yt_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif weather_match:
        final_reply = weather_report(); conversation_history[-1]["text"] = final_reply; save_history()
    elif screenshot_match:
        data_url, info = take_screenshot()
        final_reply = f"Screenshot eduthuten macha! 📸 File: {info}" if data_url else f"Screenshot edukka mudiyala: {info}"
        conversation_history[-1]["text"] = final_reply; save_history()
    elif click_match:
        coords = click_match.group(1).strip()
        final_reply = click_at(*coords.split(",")) if "," in coords else click_at(coords, None)
        conversation_history[-1]["text"] = final_reply; save_history()
    elif type_match:
        final_reply = type_text(type_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif scroll_match:
        args = scroll_match.group(1).strip().split()
        final_reply = scroll_screen(args[0] if args else "down", args[1] if len(args)>1 else "3")
        conversation_history[-1]["text"] = final_reply; save_history()
    elif cmd_match:
        final_reply = run_shell_command(cmd_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif file_match:
        parts = [p.strip() for p in file_match.group(1).split("|")]
        final_reply = file_operation(parts[0] if parts else "list", parts[1] if len(parts)>1 else None, parts[2] if len(parts)>2 else None)
        conversation_history[-1]["text"] = final_reply; save_history()
    elif window_match:
        parts = [p.strip() for p in window_match.group(1).split("|")]
        final_reply = window_control(parts[0] if parts else "minimize_all", parts[1] if len(parts)>1 else None)
        conversation_history[-1]["text"] = final_reply; save_history()
    elif process_match:
        parts = [p.strip() for p in process_match.group(1).split("|")]
        final_reply = process_control(parts[0] if parts else "list", parts[1] if len(parts)>1 else None)
        conversation_history[-1]["text"] = final_reply; save_history()
    elif clip_match:
        parts = [p.strip() for p in clip_match.group(1).split("|")]
        final_reply = clipboard_control(parts[0] if parts else "paste", parts[1] if len(parts)>1 else None)
        conversation_history[-1]["text"] = final_reply; save_history()
    elif power_match:
        final_reply = power_control(power_match.group(1).strip().lower()); conversation_history[-1]["text"] = final_reply; save_history()
    elif play_match:
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(play_match.group(1).strip()))
        final_reply = f"YouTube-la '{play_match.group(1).strip()}' play pannuren macha 🎵"
        conversation_history[-1]["text"] = final_reply; save_history()
    elif search_match:
        final_reply = smart_web_search(search_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif open_match:
        urls = {"whatsapp":"https://web.whatsapp.com/","instagram":"https://www.instagram.com/","spotify":"https://open.spotify.com/","netflix":"https://www.netflix.com/","youtube":"https://www.youtube.com/","google":"https://www.google.com/"}
        app_name = open_match.group(1).strip().lower()
        if app_name in urls:
            webbrowser.open(urls[app_name]); final_reply = f"{app_name.capitalize()} open pannuren macha 🚀"
        else: final_reply = f"{app_name} open panna mudiyala macha."
        conversation_history[-1]["text"] = final_reply; save_history()
    elif action_match:
        action = action_match.group(1).strip().lower()
        if action in ["volume_up","volume_down","mute"]: final_reply = control_volume(action)
        elif action in ["media_play_pause","media_next","media_prev"]: final_reply = control_media(action)
        elif action in ["brightness_up","brightness_down"]: final_reply = control_brightness(action)
        elif action == "shutdown": final_reply = power_control("shutdown")
        elif action == "restart": final_reply = power_control("restart")
        else: final_reply = f"{action} action work aagala macha."
        conversation_history[-1]["text"] = final_reply; save_history()
    elif system_match:
        final_reply = get_system_stats(system_match.group(1).strip().lower()); conversation_history[-1]["text"] = final_reply; save_history()
    elif folder_match:
        final_reply = open_folder(folder_match.group(1).strip().lower()); conversation_history[-1]["text"] = final_reply; save_history()
    elif app_match:
        final_reply = launch_app(app_match.group(1).strip().lower()); conversation_history[-1]["text"] = final_reply; save_history()
    elif cricket_match:
        final_reply = get_cricket_score(cricket_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif reminder_match:
        final_reply = set_reminder(reminder_match.group(1).strip(), reminder_match.group(2).strip()); conversation_history[-1]["text"] = final_reply; save_history()

    return final_reply

def telegram_bot_thread():
    if not TELEGRAM_AVAILABLE:
        print("⚠️ Telegram: python-telegram-bot not installed"); return
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ Telegram: TELEGRAM_BOT_TOKEN not set (optional)"); return
    try:
        async def start_cmd(update, context):
            await update.message.reply_text("🤖 Vasanth AI online macha! FULL PC CONTROL + IMAGE + YT + WEATHER ready!")
        async def handle_message(update, context):
            user_text = update.message.text
            print(f"\n📱 TELEGRAM: {user_text}")
            reply = await asyncio.to_thread(process_command, user_text)
            reply, _ = strip_img_token(reply)
            await update.message.reply_text(reply[:4096])
        def run():
            application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            application.add_handler(CommandHandler("start", start_cmd))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            print("📱 Telegram Bot Started!")
            application.run_polling()
        run()
    except Exception as e:
        print(f"Telegram Bot Error: {e}")

HTML = r"""
<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vasanth AI - MEGA Edition</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#e879f9">
<link rel="icon" href="/logo.png" type="image/png">
<link rel="apple-touch-icon" href="/logo.png">
<style>
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; background: #0a0614; color: #fff; font-family: 'Segoe UI', Arial, "Noto Sans Tamil", sans-serif; display: flex; justify-content: center; align-items: center; padding: 18px; overflow-x: hidden; }
.aurora { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
.aurora i { position: absolute; width: 45vw; height: 45vw; border-radius: 50%; filter: blur(100px); opacity: .25; animation: float 14s ease-in-out infinite; }
.aurora i:nth-child(1){ background:#e879f9; top:-12%; left:-12%; }
.aurora i:nth-child(2){ background:#ec4899; bottom:-12%; right:-12%; animation-delay:-5s; }
.aurora i:nth-child(3){ background:#d946ef; top:40%; left:55%; animation-delay:-9s; }
@keyframes float { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(50px,-40px) scale(1.15);} }
#particles { position: fixed; inset: 0; z-index: 0; pointer-events: none; }
.app { position: relative; z-index: 1; width: min(1100px,100%); height: min(900px,94vh); min-height:600px; background: rgba(20,10,35,.85); border: 1px solid rgba(232,121,249,.2); border-radius: 28px; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 0 80px rgba(232,121,249,.15), 0 30px 80px rgba(0,0,0,.7); backdrop-filter: blur(24px); }
.header { padding: 18px 24px; background: rgba(30,15,50,.9); border-bottom: 1px solid rgba(232,121,249,.15); display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
.logo-img { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(232,121,249,.6); box-shadow: 0 0 20px rgba(232,121,249,.5); flex: 0 0 auto; transition: all .3s; animation: logoPulse 3s ease-in-out infinite; }
body.speaking .logo-img { box-shadow: 0 0 40px rgba(232,121,249,.9); transform: scale(1.08); animation: logoGlow .8s ease-in-out infinite; }
@keyframes logoPulse { 0%,100%{ box-shadow:0 0 20px rgba(232,121,249,.5);} 50%{ box-shadow:0 0 30px rgba(236,72,153,.7);} }
@keyframes logoGlow { 0%,100%{ box-shadow:0 0 30px rgba(232,121,249,.8); transform:scale(1.08);} 50%{ box-shadow:0 0 50px rgba(236,72,153,1); transform:scale(1.12);} }
.title { font-size: 24px; font-weight: 800; background: linear-gradient(90deg,#e879f9,#f0abfc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.subtitle { margin-top: 3px; color: #f5d0fe; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; }
.online { display: inline-flex; align-items: center; gap: 7px; margin-top: 5px; color: #4ade80; font-size: 12px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 12px #22c55e; animation: pulse 1.8s infinite; }
@keyframes pulse { 50% { opacity:.4; transform: scale(.8);} }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; align-items: center; }
.small-btn { border:1px solid rgba(232,121,249,.25); background:rgba(30,15,50,.9); color:#f5d0fe; padding:9px 12px; border-radius:10px; cursor:pointer; font-size:12px; transition:all .2s; }
.small-btn:hover { background:rgba(232,121,249,.12); border-color:rgba(232,121,249,.5); transform:translateY(-1px); }
.small-btn.active { background:rgba(232,121,249,.2); border-color:#e879f9; }
.small-btn.live-on { background:rgba(236,72,153,.3); border-color:#ec4899; color:#f0abfc; animation: livePulse 1.5s ease-in-out infinite; }
@keyframes livePulse { 0%,100%{ box-shadow:0 0 10px rgba(236,72,153,.3);} 50%{ box-shadow:0 0 20px rgba(236,72,153,.8);} }
.voice-select { border:1px solid rgba(232,121,249,.25); background:rgba(30,15,50,.9); color:#f5d0fe; padding:9px 12px; border-radius:10px; cursor:pointer; font-size:12px; outline:none; }
.voice-select option { background:#1e1b4b; }
.mood-badge { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; background: rgba(232,121,249,.15); border: 1px solid rgba(232,121,249,.35); border-radius: 12px; font-size: 11px; color: #f0abfc; margin-left: 8px; }
#chat { flex: 1; padding: 25px; overflow-y: auto; scroll-behavior: smooth; }
.message-row { display: flex; margin: 16px 0; gap: 10px; align-items: flex-start; animation: messageIn .35s cubic-bezier(.2,.9,.3,1.2); }
.message-row.user-row { justify-content: flex-end; }
.message-row.proactive-row { justify-content: center; }
.message-row.proactive-row .message { background: rgba(236,72,153,.15); border: 1px dashed rgba(236,72,153,.4); font-style: italic; max-width: 70%; }
@keyframes messageIn { from{opacity:0; transform:translateY(14px) scale(.96);} to{opacity:1; transform:translateY(0) scale(1);} }
.avatar { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; font-size: 17px; flex: 0 0 auto; margin-top: 2px; overflow: hidden; }
.avatar.ai { background: linear-gradient(135deg,#e879f9,#ec4899); box-shadow: 0 0 14px rgba(232,121,249,.5); }
.avatar.user { background: linear-gradient(135deg,#be185d,#ec4899); }
.avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.message { max-width: min(75%,740px); padding: 14px 17px; border-radius: 18px; line-height: 1.65; word-wrap: break-word; }
.message .msg-text { white-space: pre-wrap; }
.message .msg-text b { color: #f5d0fe; }
.message .msg-text code { background: rgba(232,121,249,.12); border: 1px solid rgba(232,121,249,.3); padding: 1px 6px; border-radius: 6px; font-family: Consolas, monospace; font-size: .9em; color: #f0abfc; }
.message img.msg-img { max-width: 260px; border-radius: 12px; margin-top: 8px; display: block; border: 1px solid rgba(232,121,249,.3); }
.ai { background: rgba(40,20,65,.9); border: 1px solid rgba(232,121,249,.15); border-top-left-radius: 6px; }
.user { background: linear-gradient(135deg,#be185d,#ec4899); border-top-right-radius: 6px; }
.meta { font-size: 11px; opacity: .55; margin-top: 7px; display: flex; align-items: center; gap: 6px; }
.brain-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; background: rgba(232,121,249,.15); border: 1px solid rgba(232,121,249,.35); font-size: 10px; color: #f0abfc; }
.copy-btn { cursor: pointer; opacity: .6; margin-left: auto; }
.copy-btn:hover { opacity: 1; }
.thinking { display: flex; align-items: center; gap: 7px; color: #f5d0fe; font-style: italic; }
.thinking span { width: 7px; height: 7px; border-radius: 50%; background: #e879f9; animation: bounce 1.1s infinite; }
.thinking span:nth-child(2){animation-delay:.15s;} .thinking span:nth-child(3){animation-delay:.3s;}
@keyframes bounce { 0%,60%,100%{transform:translateY(0);opacity:.4;} 30%{transform:translateY(-6px);opacity:1;} }
.bottom { padding: 16px; background: rgba(25,12,45,.95); border-top: 1px solid rgba(232,121,249,.15); }
.status-row { display: flex; align-items: center; gap: 12px; margin: 0 4px 9px; flex-wrap: wrap; }
.voice-status { min-height: 18px; color: #4ade80; font-size: 12px; flex: 1; min-width: 200px; }
#waveform { display: none; align-items: center; gap: 3px; height: 20px; }
body.speaking #waveform { display: flex; }
#waveform span { width: 4px; height: 18px; background: linear-gradient(180deg,#e879f9,#ec4899); border-radius: 2px; animation: wv .9s infinite ease-in-out; }
#waveform span:nth-child(1){animation-delay:0s;} #waveform span:nth-child(2){animation-delay:.15s;} #waveform span:nth-child(3){animation-delay:.3s;} #waveform span:nth-child(4){animation-delay:.45s;} #waveform span:nth-child(5){animation-delay:.6s;}
@keyframes wv { 0%,100%{transform:scaleY(.25);} 50%{transform:scaleY(1);} }
.composer { display: flex; gap: 10px; }
input { flex: 1; min-width: 0; padding: 15px 17px; border: 1px solid rgba(232,121,249,.2); border-radius: 15px; outline: none; background: rgba(15,8,28,.9); color: #fff; font-size: 15px; transition: all .3s; }
input:focus { border-color: rgba(232,121,249,.6); box-shadow: 0 0 20px rgba(232,121,249,.2); }
input::placeholder { color: #6b5b8a; }
.action-btn { width: 52px; border: none; border-radius: 14px; cursor: pointer; font-size: 20px; color: white; transition: all .2s; }
.action-btn:hover { transform: translateY(-2px) scale(1.05); filter: brightness(1.15); }
.mic { background: linear-gradient(135deg,#16a34a,#059669); }
.cam { background: linear-gradient(135deg,#f59e0b,#d97706); }
.scr { background: linear-gradient(135deg,#8b5cf6,#6d28d9); }
.send { background: linear-gradient(135deg,#d946ef,#a21caf); }
.quick-actions { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.quick-btn { padding: 6px 12px; border-radius: 20px; border: 1px solid rgba(232,121,249,.2); background: rgba(30,15,50,.8); color: #f5d0fe; font-size: 11px; cursor: pointer; transition: all .2s; }
.quick-btn:hover { background: rgba(232,121,249,.15); transform: translateY(-1px); }
.footer-note { margin-top: 8px; text-align: center; color: #6b5b8a; font-size: 10px; letter-spacing: .5px; }
.wake-word-indicator { position: fixed; top: 20px; right: 20px; display: flex; align-items: center; gap: 10px; padding: 12px 20px; background: rgba(232,121,249,.15); border: 1px solid rgba(232,121,249,.35); border-radius: 30px; backdrop-filter: blur(10px); opacity: 0; transform: translateY(-20px); transition: all .3s ease; z-index: 1000; }
.wake-word-indicator.active { opacity: 1; transform: translateY(0); }
.wake-word-indicator.listening { background: rgba(34,197,94,.2); border-color: rgba(34,197,94,.5); }
.wake-word-indicator.speaking { background: rgba(236,72,153,.25); border-color: rgba(236,72,153,.55); }
.wake-word-orb { width: 16px; height: 16px; border-radius: 50%; background: #e879f9; animation: orbPulse 1.5s ease-in-out infinite; }
.wake-word-indicator.listening .wake-word-orb { background:#22c55e; }
.wake-word-indicator.speaking .wake-word-orb { background:#f0abfc; }
@keyframes orbPulse { 0%,100%{transform:scale(1);} 50%{transform:scale(1.3);} }
.wake-word-text { color: #fff; font-size: 13px; font-weight: 600; }
@media (max-width:700px){ body{padding:0;} .app{width:100%;height:100vh;min-height:0;border-radius:0;} .header{padding:12px 15px;} .logo-img{width:44px;height:44px;} .title{font-size:18px;} #chat{padding:15px 12px;} .message{max-width:85%;} .bottom{padding:10px;} .action-btn{width:46px;} input{font-size:14px;padding:13px;} .avatar{width:30px;height:30px;font-size:14px;} }
</style>
</head>
<body>
<div class="aurora"><i></i><i></i><i></i></div>
<canvas id="particles"></canvas>
<div id="wakeIndicator" class="wake-word-indicator">
    <div class="wake-word-orb"></div>
    <span class="wake-word-text">Listening for "Macha"...</span>
</div>
<div class="app">
    <div class="header">
        <div class="brand">
            <img src="/logo.png" alt="Vasanth AI" class="logo-img">
            <div>
                <div class="title">VASANTH AI <span class="mood-badge" id="moodBadge">😊 Neutral</span></div>
                <div class="subtitle">🎨 Image • 🎬 YT • ️ Weather • ️ PC Control</div>
                <div class="online"><span class="dot"></span><span id="onlineText">Online — MEGA Edition Ready</span></div>
            </div>
        </div>
        <div class="header-actions">
            <select id="voiceSelect" onchange="changeVoice()" class="voice-select" title="Select Voice">
                <option value="pallavi">👩 Pallavi</option>
                <option value="cute">🎀 Cute</option>
                <option value="saranya">🌏 Saranya</option>
            </select>
            <button class="small-btn" onclick="toggleLive()" id="liveBtn">🎙️ Live: OFF</button>
            <button class="small-btn" onclick="toggleGesture()" id="gestureBtn">✋ Gesture: OFF</button>
            <button class="small-btn" onclick="installApp()" id="installBtn" style="display:none">📲 Install</button>
            <button class="small-btn active" onclick="toggleWakeWord()" id="wakeBtn">🎙️ Wake: ON</button>
            <button class="small-btn" onclick="clearChat()">🗑️ Clear</button>
        </div>
    </div>
    <div id="chat"></div>
    <div class="bottom">
        <div class="status-row">
            <div id="voiceStatus" class="voice-status">🔊 Jarvis Systems Online — MEGA EDITION</div>
            <div id="waveform"><span></span><span></span><span></span><span></span><span></span></div>
        </div>
        <div class="quick-actions">
            <button class="quick-btn" onclick="quickSend('Draw a cute robot in neon style')">🎨 Draw</button>
            <button class="quick-btn" onclick="quickSend('Weather enna?')">🌦️ Weather</button>
            <button class="quick-btn" onclick="quickSend('Good morning')">🌅 Morning</button>
            <button class="quick-btn" onclick="quickSend('India cricket score enna?')">🏏 Cricket</button>
            <button class="quick-btn" onclick="quickSend('Take screenshot')">📸 Screenshot</button>
            <button class="quick-btn" onclick="quickSend('Minimize all windows')">🗔 Minimize</button>
            <button class="quick-btn" onclick="quickSend('Battery status enna?')">🔋 Battery</button>
        </div>
        <div class="composer">
            <input id="message" type="text" placeholder="Say 'Macha' or type... (Image/YT/Weather/PC)" autocomplete="off">
            <button class="action-btn scr" onclick="quickSend('Take screenshot')" title="Screenshot">📸</button>
            <button class="action-btn cam" onclick="pickImage()" title="Photo">📷</button>
            <button class="action-btn mic" onclick="startVoice()" title="Voice">🎤</button>
            <button class="action-btn send" onclick="sendMessage()" title="Send">➤</button>
        </div>
        <input type="file" id="imageInput" accept="image/*" style="display:none" onchange="onImagePicked(event)">
        <div class="footer-note">VASANTH AI • MEGA EDITION 🎨️🖥️ • TRIPLE BRAIN 🖥️</div>
    </div>
</div>
<script>
const LOGO_HTML = '<img src="/logo.png" alt="AI">';
const wakeBeep = new Audio("data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdH2LkZaXmZaKi4uLioqJiIeGhYSDgoGAfn18e3p5eHd3d3Z1dXRzc29ubWxqaWhnZmVkY2NiYGBfXl1cW1taWVlZWVhYV1dWVlVVVFRUU1NSUlJRUFBQT09OTk1NTUxMTEw/Pz8+Pj49PT08PDw8Ozs7Ojo6OTo5OTk5ODg4ODc3Nzc2NjY1NTU1NDQ0NDMzMzMyMjIxMTExMDAwLy8vLi4uLS0tLCwsKysrKioqKSkoKCgnJycmJiYlJSUlJCQkIyMjIiIiISEhICAgICAgIB8fHx4eHh0dHRwcHBsbGxoaGhkZGRgYGBcXFxYWFhUUFBQTExMSEhIREREQEBAQEBAQEA8PDw4ODg0NDQwMDAsLCwoKCgkJCQgICAcHBwYGBgUFBQQEBAMDAwICAgEBAQAAAAD//wAA//8AAP//AAD//wAA");
function playWakeBeep(){ try{ wakeBeep.currentTime=0; wakeBeep.play().catch(e=>{}); }catch(e){} }
const MOOD_EMOJI = { happy:"😊 Happy", sad:"😢 Sad", excited:"🤩 Excited", tired:"😴 Tired", angry:"😠 Angry", neutral:"😐 Neutral", curious:"🤓 Curious" };

// AUDIO UNLOCK: First click/keypress allows autoplay (fixes browser block)
function unlockAudio(){
  try{
    const a = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==");
    a.play().catch(()=>{});
  }catch(e){}
  document.removeEventListener("click", unlockAudio);
  document.removeEventListener("keydown", unlockAudio);
}
document.addEventListener("click", unlockAudio);
document.addEventListener("keydown", unlockAudio);

let gestureOn=false;
function toggleGesture(){
  gestureOn=!gestureOn;
  fetch(gestureOn?"/gesture/on":"/gesture/off",{method:"POST"});
  const b=document.getElementById("gestureBtn");
  b.textContent = gestureOn?"✋ Gesture: ON":"✋ Gesture: OFF";
  b.classList.toggle("active",gestureOn);
  setVoiceStatus(gestureOn?"✋ Gesture ON - camera watch pannudhu!":"🔊 Ready");
}
setInterval(async()=>{
  try{
    const r=await fetch("/gesture/status"); const d=await r.json();
    if(d.enabled && d.last && (Date.now()/1000 - d.last.timestamp)<2){
      setVoiceStatus("✋ Gesture: "+d.last.gesture);
    }
  }catch(e){}
},1000);

async function pollMood(){
  try{
    const r = await fetch("/mood"); const d = await r.json();
    if(d && d.mood){
      const badge = document.getElementById("moodBadge");
      badge.textContent = MOOD_EMOJI[d.mood] || "😐 Neutral";
      badge.title = "Intensity: " + (d.intensity || 5) + "/10";
    }
  }catch(e){}
  setTimeout(pollMood, 5000);
}
pollMood();
</script>
<script>
const cv=document.getElementById("particles"),cx=cv.getContext("2d");
let P=[];
function rsz(){cv.width=innerWidth;cv.height=innerHeight;}
rsz();addEventListener("resize",rsz);
for(let i=0;i<45;i++)P.push({x:Math.random()*innerWidth,y:Math.random()*innerHeight,vx:(Math.random()-.5)*.5,vy:(Math.random()-.5)*.5,r:Math.random()*1.8+.8});
function drawP(){cx.clearRect(0,0,cv.width,cv.height);
for(const p of P){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>cv.width)p.vx*=-1;if(p.y<0||p.y>cv.height)p.vy*=-1;cx.beginPath();cx.arc(p.x,p.y,p.r,0,7);cx.fillStyle="rgba(232,121,249,.3)";cx.fill();}
for(let i=0;i<P.length;i++)for(let j=i+1;j<P.length;j++){const dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d=dx*dx+dy*dy;if(d<13000){cx.strokeStyle="rgba(232,121,249,"+(0.12*(1-d/13000))+")";cx.beginPath();cx.moveTo(P[i].x,P[i].y);cx.lineTo(P[j].x,P[j].y);cx.stroke();}}
requestAnimationFrame(drawP);}
drawP();

const chat=document.getElementById("chat"),input=document.getElementById("message");
let wakeWordEnabled=true,wakeActive=false,busy=false,wakeRecognition=null,commandRecognition=null;
const WAKE_PATTERNS=[/mach/i,/much/i,/vasan/i,/மச்சா/,/வசந்த/];

let liveMode = false;
function toggleLive(){
  liveMode = !liveMode;
  const b = document.getElementById("liveBtn");
  if(liveMode){ b.textContent="🔴 Live: ON"; b.classList.add("live-on"); b.classList.add("active"); setVoiceStatus("🎙️ Live Chat ON - pesunga macha!"); startLiveListen(); }
  else { b.textContent="🎙️ Live: OFF"; b.classList.remove("live-on"); b.classList.remove("active"); setVoiceStatus("🔊 Ready"); showIndicator("",""); }
}
function startLiveListen(){
  if(!liveMode || busy) return;
  const SR = window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR) return;
  const r = new SR(); r.lang="ta-IN"; r.continuous=false; r.interimResults=false;
  let got=false;
  setVoiceStatus("🎧 Kekuren... pesunga!"); showIndicator("listening","Listening...");
  r.onresult=(e)=>{ got=true; input.value=e.results[0][0].transcript; sendMessage(); };
  r.onend=()=>{ if(!got && liveMode) setTimeout(startLiveListen,500); };
  r.onerror=()=>{ if(liveMode) setTimeout(startLiveListen,800); };
  try{ r.start(); }catch(e){}
}

function escapeTime(){return new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});}
function formatText(t){
  let s=t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  s=s.replace(/\*\*(.*?)\*\*/g,"<b>$1</b>");
  s=s.replace(/`(.*?)`/g,"<code>$1</code>");
  return s;
}
function typewriter(el,text,done){
  let i=0; const speed=text.length>400?4:14; el.textContent="";
  (function step(){
    if(i<text.length){ el.textContent+=text[i]; i++; chat.scrollTop=chat.scrollHeight; setTimeout(step,speed); }
    else if(done){ done(); }
  })();
}
function addMessage(t,type,time=null,imgSrc=null,animate=false,brain=""){
  const r=document.createElement("div");
  r.className="message-row "+(type==="user"?"user-row":type==="proactive"?"proactive-row":"ai-row");
  let av=null;
  if(type !== "proactive"){
    av=document.createElement("div");
    av.className="avatar "+(type==="user"?"user":"ai");
    if(type==="user"){ av.textContent="👤"; } else { av.innerHTML=LOGO_HTML; }
  }
  const b=document.createElement("div");
  b.className="message "+(type==="proactive"?"ai":type);
  if(imgSrc){const im=document.createElement("img");im.src=imgSrc;im.className="msg-img";b.appendChild(im);}
  const txt=document.createElement("div"); txt.className="msg-text"; b.appendChild(txt);
  const m=document.createElement("div");m.className="meta";
  let meta=type==="user"?"You":type==="proactive"?"🔮 Vasanth AI (Proactive)":"Vasanth AI";
  if(brain) meta+=` <span class="brain-badge">${brain}</span>`;
  meta+=" • "+(time||escapeTime());
  if(type==="ai") meta+=` <span class="copy-btn" title="Copy">⧉</span>`;
  m.innerHTML=meta; b.appendChild(m);
  if(type==="user"){ r.appendChild(b); if(av) r.appendChild(av); }
  else { if(av) r.appendChild(av); r.appendChild(b); }
  chat.appendChild(r); chat.scrollTop=chat.scrollHeight;
  const cp=m.querySelector(".copy-btn");
  if(cp){ cp.onclick=()=>{ navigator.clipboard.writeText(t); cp.textContent="✅"; setTimeout(()=>cp.textContent="⧉",1200); }; }
  if(animate && (type==="ai"||type==="proactive")){ typewriter(txt,t,()=>{ txt.innerHTML=formatText(t); }); }
  else { txt.innerHTML=formatText(t); }
}
function addThinking(){
  removeThinking();
  const r=document.createElement("div"); r.className="message-row";
  const av=document.createElement("div"); av.className="avatar ai"; av.innerHTML=LOGO_HTML;
  const b=document.createElement("div"); b.className="message ai thinking";
  b.innerHTML="<span></span><span></span><span></span><b style='margin-left:4px;font-weight:500'>Thinking...</b>";
  r.appendChild(av); r.appendChild(b); chat.appendChild(r); chat.scrollTop=chat.scrollHeight;
}
function removeThinking(){const o=document.querySelector(".thinking");if(o)o.parentElement.remove();}
function setVoiceStatus(t){const s=document.getElementById("voiceStatus");if(s)s.textContent=t;}
function showIndicator(state,text){const ind=document.getElementById("wakeIndicator");ind.className="wake-word-indicator "+state;if(text)ind.querySelector(".wake-word-text").textContent=text;}
function showWelcome(){chat.innerHTML="";addMessage("வணக்கம் Vasanth! 👋\n\n**MEGA EDITION (BUG-FREE)** ready! 🎨🎬️🖥️\n\n🥇 **Gemini Natural Voice** - MP3 via lameenc (no ffmpeg!)\n🎨 **AI Image Gen** - 'Draw a cute robot' nu sollu!\n🎬 **YouTube Summarizer** - link paste pannu!\n🌧️ **Weather Alerts** - mazhai auto-alert!\n🖥️ **PC Master Control** - full access!\n\n**Try:** 'Draw a neon cat' / 'Weather enna?'","ai");}
async function loadHistory(){try{const r=await fetch("/history");if(!r.ok)throw new Error();const d=await r.json();chat.innerHTML="";if(!d.history||d.history.length===0){showWelcome();return;}d.history.forEach(i=>{
  const isProactive = i.text && i.text.startsWith("[proactive]");
  const cleanText = isProactive ? i.text.substring(12) : i.text;
  addMessage(cleanText, isProactive ? "proactive" : (i.role==="user"?"user":"ai"));
});}catch(e){showWelcome();}}
async function clearChat(){if(!confirm("Clear history?"))return;try{await fetch("/clear",{method:"POST"});showWelcome();setVoiceStatus("🧠 Fresh ready");}catch(e){alert("Error");}}
function changeVoice(){
  const voice=document.getElementById("voiceSelect").value;
  setVoiceStatus("🎤 Voice switching...");
  fetch("/change-voice",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({voice:voice})})
    .then(r=>r.json()).then(d=>{ if(d.success){ setVoiceStatus("🎤 Voice: "+d.name); playTTS("Vanakkam macha! Naan "+d.name+" voice-la pesuren. Cute-a irukka?"); } })
    .catch(e=>setVoiceStatus("⚠️ Voice error"));
}
function playTTS(t){return new Promise(async (resolve)=>{setVoiceStatus("🔊 குரல் உருவாகிறது...");showIndicator("speaking","Speaking...");try{const r=await fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});if(!r.ok){if(!busy)finishCycle();resolve();return;}const b=await r.blob();if(!b.size){if(!busy)finishCycle();resolve();return;}const u=URL.createObjectURL(b),a=new Audio(u);a.onplay=()=>{setVoiceStatus("🔊 பேசுகிறது...");document.body.classList.add("speaking");showIndicator("speaking","Speaking...");};const done=()=>{document.body.classList.remove("speaking");setVoiceStatus("🔊 Ready");URL.revokeObjectURL(u);if(!busy)finishCycle();resolve();};a.onended=done;a.onerror=done;await a.play().catch(e=>{console.log("Play blocked:",e);done();});}catch(e){document.body.classList.remove("speaking");setVoiceStatus("⚠️ Error");if(!busy)finishCycle();resolve();}});}
function quickSend(t){input.value=t;sendMessage();}
function finishCycle(){busy=false;showIndicator("","");if(liveMode){setTimeout(startLiveListen,400);}else if(wakeWordEnabled){setTimeout(startWake,600);}}
async function sendMessage(){const t=input.value.trim();if(!t){finishCycle();return;}busy=true;stopWake();addMessage(t,"user");input.value="";addThinking();setVoiceStatus(" Thinking...");showIndicator("listening","Processing...");try{const r=await fetch("/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t})});if(!r.ok)throw new Error();const d=await r.json();removeThinking();addMessage(d.reply||"...", "ai",null,d.image||null,true,d.brain||"");await playTTS(d.reply||"");finishCycle();}catch(e){removeThinking();addMessage("Server error","ai");setVoiceStatus("🔴 Error");finishCycle();}}
function pickImage(){document.getElementById("imageInput").click();}
async function onImagePicked(e){const file=e.target.files[0];if(!file)return;const reader=new FileReader();reader.onload=async function(){const dataURL=reader.result;const q=input.value.trim()||"Idhula enna iruku?";busy=true;stopWake();addMessage("📷 "+q,"user",null,dataURL);input.value="";addThinking();try{const r=await fetch("/vision",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:dataURL,question:q})});const d=await r.json();removeThinking();addMessage(d.reply,"ai",null,null,true,d.brain||"");await playTTS(d.reply);finishCycle();}catch(err){removeThinking();addMessage("Vision error","ai");finishCycle();}};reader.readAsDataURL(file);e.target.value="";}
function detectWake(t){t=t.toLowerCase().trim();for(const p of WAKE_PATTERNS){const m=p.exec(t);if(m)return t.slice(m.index+m[0].length).trim();}return null;}
function stopWake(){if(wakeRecognition){try{wakeRecognition.onend=null;wakeRecognition.onerror=null;wakeRecognition.stop();}catch(e){}wakeRecognition=null;}wakeActive=false;}
function startWake(){if(!wakeWordEnabled||busy||wakeActive||liveMode)return;const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return;try{wakeRecognition=new SR();}catch(e){return;}wakeRecognition.lang="ta-IN";wakeRecognition.continuous=true;wakeRecognition.interimResults=true;wakeRecognition.onstart=()=>{wakeActive=true;showIndicator("active",'Listening "Macha"...');};wakeRecognition.onresult=(e)=>{if(busy)return;let t="";for(let i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript;if(!t)return;const a=detectWake(t);if(a!==null){playWakeBeep();stopWake();busy=true;if(a.length>=2){input.value=a;sendMessage();}else{startCommandRecognition();}}};wakeRecognition.onerror=()=>{};wakeRecognition.onend=()=>{wakeActive=false;if(wakeWordEnabled&&!busy&&!liveMode)setTimeout(startWake,500);};try{wakeRecognition.start();}catch(e){}}
function startCommandRecognition(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){finishCycle();return;}commandRecognition=new SR();commandRecognition.lang="ta-IN";commandRecognition.continuous=false;commandRecognition.interimResults=false;let got=false;commandRecognition.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};commandRecognition.onend=()=>{if(!got)finishCycle();};setTimeout(()=>{try{commandRecognition.start();}catch(e){finishCycle();}},400);}
function toggleWakeWord(){wakeWordEnabled=!wakeWordEnabled;const b=document.getElementById("wakeBtn");if(wakeWordEnabled){b.textContent="🎙️ Wake: ON";b.classList.add("active");startWake();}else{b.textContent="🎙️ Wake: OFF";b.classList.remove("active");stopWake();busy=false;showIndicator("","");}}
function startVoice(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){addMessage("Voice not supported","ai");return;}busy=true;stopWake();const r=new SR();r.lang="ta-IN";r.continuous=false;r.interimResults=false;let got=false;setVoiceStatus("🎤 பேசு...");r.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};r.onend=()=>{if(!got)finishCycle();};try{r.start();}catch(e){finishCycle();}}
let deferredPrompt=null;
window.addEventListener("beforeinstallprompt",(e)=>{e.preventDefault();deferredPrompt=e;const b=document.getElementById("installBtn");if(b)b.style.display="inline-block";});
function installApp(){if(!deferredPrompt)return;deferredPrompt.prompt();deferredPrompt.userChoice.then(r=>{if(r.outcome==="accepted")document.getElementById("installBtn").style.display="none";deferredPrompt=null;});}
if("serviceWorker" in navigator){window.addEventListener("load",()=>{navigator.serviceWorker.register("/sw.js").catch(e=>{});});}
input.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();sendMessage();}});
loadHistory();setTimeout(startWake,1000);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/history", methods=["GET"])
def history():
    return jsonify({"history": conversation_history[-MAX_HISTORY_MESSAGES:]})

@app.route("/clear", methods=["POST"])
def clear():
    clear_memory()
    return jsonify({"success": True})

@app.route("/mood", methods=["GET"])
def mood():
    return jsonify(CURRENT_MOOD)

@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"success": False}), 400
    audio_buffer, error, mime = generate_tts(text)
    if audio_buffer is None:
        return jsonify({"success": False, "error": error}), 503
    audio_buffer.seek(0)
    ext = "wav" if mime == "audio/wav" else "mp3"
    return send_file(audio_buffer, mimetype=mime, as_attachment=False, download_name=f"v.{ext}")

@app.route("/vision", methods=["POST"])
def vision():
    data = request.get_json(silent=True) or {}
    image_data = data.get("image", "")
    question = data.get("question", "") or "Describe what you see in this image in Tamil."
    if not image_data or groq_client is None:
        return jsonify({"reply": "மச்சா 😅 Photo upload pannunga / API key illa."})
    messages = [{"role":"system","content":build_system()},{"role":"user","content":[{"type":"text","text":question},{"type":"image_url","image_url":{"url":image_data}}]}]
    for model in ["qwen/qwen3.6-27b","meta-llama/llama-4-scout-17b-16e-instruct"]:
        try:
            response = groq_client.chat.completions.create(model=model, messages=messages, max_tokens=800)
            content = response.choices[0].message.content
            reply = clean_think(content.strip() if content else "")
            set_brain("⚡ Groq")
            add_to_memory("user", f"[Photo] {question}"); add_to_memory("model", reply)
            return jsonify({"reply": reply, "brain": LAST_BRAIN})
        except Exception as e:
            if any(k in str(e) for k in ["404","429","rate","decommission"]): continue
            return jsonify({"reply": f"மச்சா 😅 Vision error: {str(e)[:100]}"})
    return jsonify({"reply": "மச்சா 😅 Vision AI work aagala."})

@app.route("/command", methods=["POST"])
def command():
    data = request.get_json(silent=True) or {}
    original_text = str(data.get("command", "")).strip()
    result = process_command(original_text)
    reply, image = strip_img_token(result)
    return jsonify({"reply": reply, "brain": LAST_BRAIN, "image": image})

@app.route("/change-voice", methods=["POST"])
def change_voice():
    global EDGE_TTS_VOICE, EDGE_TTS_RATE, EDGE_TTS_PITCH
    data = request.get_json(silent=True) or {}
    key = data.get("voice", "pallavi")
    prof = VOICE_PROFILES.get(key, VOICE_PROFILES["pallavi"])
    EDGE_TTS_VOICE = prof["voice"]; EDGE_TTS_RATE = prof["rate"]; EDGE_TTS_PITCH = prof["pitch"]
    print(f"🎤 Voice profile: {prof['label']} (rate={EDGE_TTS_RATE}, pitch={EDGE_TTS_PITCH})")
    return jsonify({"success": True, "name": prof["label"]})

@app.route("/gesture/on", methods=["POST"])
def gesture_on():
    global GESTURE_ENABLED
    if GESTURE_ENABLED: return jsonify({"success": True, "msg": "already on"})
    GESTURE_ENABLED = True
    threading.Thread(target=gesture_loop, daemon=True).start()
    return jsonify({"success": True})

@app.route("/gesture/off", methods=["POST"])
def gesture_off():
    global GESTURE_ENABLED
    GESTURE_ENABLED = False
    return jsonify({"success": True})

@app.route("/gesture/status", methods=["GET"])
def gesture_status():
    return jsonify({"enabled": GESTURE_ENABLED, "last": LAST_GESTURE})

@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "Vasanth AI - MEGA Edition",
        "short_name": "Vasanth AI",
        "description": "AI with image gen, YT summary, weather, PC control",
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#0f0a1e", "theme_color": "#e879f9", "orientation": "portrait",
        "icons": [
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
        ]
    })

@app.route("/icon.svg")
def pwa_icon():
    return Response(PWA_ICON_SVG, mimetype="image/svg+xml")

@app.route("/logo.png")
def logo_png():
    try:
        return send_file(os.path.join(BASE_DIR, "logo.png"), mimetype="image/png")
    except Exception as e:
        print(f"Logo error: {e}")
        return Response(PWA_ICON_SVG, mimetype="image/svg+xml")

@app.route("/sw.js")
def pwa_sw():
    return Response(PWA_SERVICE_WORKER, mimetype="application/javascript")

def open_browser():
    time.sleep(2)
    try: webbrowser.open_new("http://127.0.0.1:5000")
    except: pass

if __name__ == "__main__":
    load_history()
    load_mood()
    threading.Thread(target=reminder_checker_thread, daemon=True).start()
    threading.Thread(target=telegram_bot_thread, daemon=True).start()
    threading.Thread(target=proactive_thread, daemon=True).start()
    print("\n" + "=" * 60)
    print("    VASANTH AI - MEGA EDITION (BUG-FREE) 🎨🎬🌧️️")
    print("=" * 60)
    print(f"Groq:     {'READY ✅' if GROQ_API_KEY else 'MISSING ❌'}")
    print(f"AWS:      {'READY ✅' if AWS_READY else 'Not configured'}")
    print(f"Ollama:   {'READY ✅ (OFFLINE!)' if OLLAMA_READY else 'Not running'}")
    print(f"Telegram: {'READY ✅' if (TELEGRAM_AVAILABLE and TELEGRAM_BOT_TOKEN) else 'Not configured'}")
    print(f"PyAutoGUI:{'READY ✅' if PYAUTOGUI_READY else 'MISSING ❌'}")
    print(f"Gemini:   {'🥇 NATURAL VOICE READY' if GEMINI_API_KEY else 'NOT SET (Google/Edge fallback)'}")
    print(f"Lameenc:  {'✅ MP3 encoder ready (NO FFMPEG!)' if LAMEENC_READY else '❌ pip install lameenc'}")
    print(f"Image:    🎨 Pollinations (FREE)")
    print(f"YouTube:  🎬 Transcript Summarizer")
    print(f"Weather:  🌧️ Open-Meteo (auto alerts)")
    print(f"Memory:   🧠 PERMANENT")
    print(f"Mood:     🎭 Emotion Detection ON")
    print(f"Proactive:🔮 Background speaker ON")
    print(f"PC Ctrl:  🖥️ FULL ACCESS")
    print(f"Gesture:  ✋ Hand control ready")
    print(f"Logo:     {'READY ✅' if os.path.exists(os.path.join(BASE_DIR,'logo.png')) else 'MISSING ❌'}")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 7860)), debug=False, use_reloader=False)