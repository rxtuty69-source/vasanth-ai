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
import os, json, io, time, threading, datetime, webbrowser, asyncio, re, base64, shutil, edge_tts, urllib.parse, subprocess, sys, ctypes, psutil, requests
from pathlib import Path

# ─── Whisper STT ──────────────────────────────────────────────
WHISPER_READY = False
whisper_model = None
try:
    import whisper as _whisper_mod
    whisper_model = _whisper_mod.load_model("base")
    WHISPER_READY = True
    print("🎙️ Whisper STT READY")
except: pass

# ─── Piper TTS ───────────────────────────────────────────────
PIPER_READY = False
piper_voice = None
try:
    from piper import PiperVoice
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _piper_model_path = os.path.join(BASE_DIR, 'data', 'ta_IN-shalini-medium.onnx')
    if os.path.exists(_piper_model_path):
        piper_voice = PiperVoice.load(_piper_model_path)
        PIPER_READY = True
        print("🔊 Piper TTS READY")
except: pass

app = Flask(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
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
VOICE_ENABLED = True
PERSONALITY = {"mode": "friend"}
PERSONALITY_PROMPTS = {
    "friend": "Speak in natural Tanglish like a Chennai friend. Call user 'macha'.",
    "teacher": "Speak like a patient teacher. Explain step-by-step clearly.",
    "professional": "Speak professionally and concisely in clear English.",
    "funny": "Speak with lots of humor and playful teasing in Tanglish."
}

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
MUSIC_FILE = os.path.join(DATA_DIR, "music_state.json")
conversation_history = []
MAX_HISTORY_MESSAGES = 20
CURRENT_MOOD = {"mood": "neutral", "intensity": 5, "timestamp": 0}
MUSIC_STATE = {"playing": False, "title": "Nothing playing"}

def load_music():
    global MUSIC_STATE
    try:
        if os.path.exists(MUSIC_FILE):
            with open(MUSIC_FILE, "r", encoding="utf-8") as f: MUSIC_STATE.update(json.load(f))
    except: pass

def save_music():
    try:
        with open(MUSIC_FILE, "w", encoding="utf-8") as f: json.dump(MUSIC_STATE, f, ensure_ascii=False)
    except: pass

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
        prompt = f"""Analyze the emotion. Return ONLY JSON: {{"mood":"happy","intensity":8}}
Moods: happy, sad, excited, tired, angry, neutral, curious. Intensity: 1-10
Message: {text}"""
        messages = [{"role": "system", "content": "Return ONLY JSON."}, {"role": "user", "content": prompt}]
        reply = _groq_complete(messages)
        if not reply: return
        m = re.search(r'\{[^}]+\}', reply)
        if m:
            emo = json.loads(m.group(0))
            if "mood" in emo and emo["mood"] in ["happy","sad","excited","tired","angry","neutral","curious"]:
                CURRENT_MOOD = {"mood": emo["mood"], "intensity": emo.get("intensity",5), "timestamp": time.time()}
                save_mood()
    except: pass

def get_mood_context():
    if not CURRENT_MOOD.get("mood"): return ""
    age = time.time() - CURRENT_MOOD.get("timestamp", 0)
    if age > 300: return ""
    mood = CURRENT_MOOD["mood"]; intensity = CURRENT_MOOD["intensity"]
    tone_map = {"happy":"Be cheerful! 🎉","sad":"Be warm and supportive. 💙","excited":"Match their excitement! 🔥","tired":"Be gentle and brief. 😴","angry":"Be calm and understanding. 🕊️","neutral":"Normal friendly tone.","curious":"Be detailed and engaging! "}
    return f"\nUSER'S MOOD: {mood} ({intensity}/10)\nTONE: {tone_map.get(mood,'Normal')}\n"

LAST_USER_ACTIVITY = time.time()
LAST_PROACTIVE_SPEAK = 0
MORNING_GREETED_TODAY = None
EVENING_GREETED_TODAY = None
WEATHER_ALERTED_TODAY = None

_THINK_TAG = '</think>'
THINK_PATTERN = re.compile(r'<think>.*?</think>', flags=re.DOTALL)
def clean_think(text):
    return THINK_PATTERN.sub('', text).strip()

SYSTEM_PROMPT = """You are Vasanth AI, a genius-level personal AI assistant for Vasanth. Like JARVIS with Chennai friend vibe.
LANGUAGE: Speak in natural Tanglish. Call Vasanth "macha". Use fillers like "Hmm...", "Aama macha...".
Use **bold** for important words. Keep voice responses concise (under 200 words).
⏰ Current year is 2026.
🧠 Think step-by-step inside <think> tags before answering.
SPECIAL ACTIONS: [IMAGE: desc], [YT: url], [WEATHER], [PLAY: query], [SEARCH: query], [OPEN: app], [APP: app], [CMD: cmd], [FILE: action|src|dst], [WINDOW: action|title], [PROCESS: action|name], [CLIP: action|text], [POWER: action], [ACTION: volume_up/down/mute/brightness_up/down], [SYSTEM: battery/cpu/ram], [FOLDER: name], [CODE]code[/CODE], [REMINDER: min|msg], [CRICKET: query], [SCREENSHOT], [CLICK: x,y], [TYPE: text], [SCROLL: dir], [CRYPTO: coin], [TRANSLATE: lang|text], [NEWS: cat]"""

PWA_ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="112" fill="#1e1b4b"/><circle cx="256" cy="220" r="130" fill="#e879f9"/></svg>'''

PWA_SERVICE_WORKER = '''const CACHE='vasanth-ai-v27';const CORE=['/','/manifest.json','/logo.png'];self.addEventListener('install',(e)=>{e.waitUntil(caches.open(CACHE).then((c)=>c.addAll(CORE)).then(()=>self.skipWaiting()));});self.addEventListener('activate',(e)=>{e.waitUntil(caches.keys().then((keys)=>Promise.all(keys.filter((k)=>k!==CACHE).map((k)=>caches.delete(k)))).then(()=>self.clients.claim()));});self.addEventListener('fetch',(e)=>{const url=new URL(e.request.url);if(e.request.method!=='GET'||url.origin!==location.origin)return;if(['/command','/tts','/vision','/history','/clear','/change-voice','/mood','/genimg','/screenshot'].includes(url.pathname))return;e.respondWith(fetch(e.request).then((res)=>{if(res.ok){const clone=res.clone();caches.open(CACHE).then((c)=>c.put(e.request,clone));}return res;}).catch(()=>caches.match(e.request).then((m)=>m||caches.match('/'))));});'''

def load_history():
    global conversation_history
    try:
        if not os.path.exists(HISTORY_FILE): conversation_history = []; return
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        conversation_history = data[-MAX_HISTORY_MESSAGES:] if isinstance(data, list) else []
    except: conversation_history = []

def save_history():
    try:
        temp_file = HISTORY_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(conversation_history[-MAX_HISTORY_MESSAGES:], file, ensure_ascii=False, indent=2)
        os.replace(temp_file, HISTORY_FILE)
    except: pass

def clear_memory():
    global conversation_history
    conversation_history = []
    try:
        if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
    except: pass

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
    try:
        if sys.platform == "win32":
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW('close vasanth_audio', None, 0, 0)
            winmm.mciSendStringW(f'open "{path}" alias vasanth_audio', None, 0, 0)
            winmm.mciSendStringW('play vasanth_audio', None, 0, 0)
        else:
            os.system(f'start "" "{path}"')
    except: pass

def save_audio_file(audio_buffer, mime, base_name):
    ext = "wav" if mime == "audio/wav" else "mp3"
    path = os.path.join(DATA_DIR, f"{base_name}.{ext}")
    with open(path, "wb") as f: f.write(audio_buffer.read())
    return path

AUTOMATION_FILE = os.path.join(DATA_DIR, "automation.json")
AUTOMATION = {"morning_routine": True, "work_mode": False, "night_routine": False, "battery_saver": False, "auto_backup": False}

def load_automation():
    global AUTOMATION
    try:
        if os.path.exists(AUTOMATION_FILE):
            with open(AUTOMATION_FILE, "r") as f: AUTOMATION.update(json.load(f))
    except: pass

def save_automation():
    try:
        with open(AUTOMATION_FILE, "w") as f: json.dump(AUTOMATION, f)
    except: pass

AUTOMATION_DONE = {"night": None, "backup": None, "battery": None}

def control_volume(action):
    try:
        keys = {"volume_up":0xAF,"volume_down":0xAE,"mute":0xAD}
        key = keys.get(action)
        if key:
            for _ in range(5 if action != "mute" else 1):
                ctypes.windll.user32.keybd_event(key,0,0,0); ctypes.windll.user32.keybd_event(key,0,2,0)
            return f"{action} panniten macha 🔊"
    except: pass
    return "Volume control-la problem."

def control_media(action):
    try:
        keys = {"media_play_pause":0xB3,"media_next":0xB0,"media_prev":0xB1}
        key = keys.get(action)
        if key:
            ctypes.windll.user32.keybd_event(key,0,0,0); ctypes.windll.user32.keybd_event(key,0,2,0)
            return f"{action} press panniten macha 🎵"
    except: pass
    return "Media control work aagala."

def control_brightness(action):
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()[0]
        new_val = min(100, current+20) if action=="brightness_up" else max(10, current-20)
        sbc.set_brightness(new_val)
        return f"Brightness {new_val}% ku set panniten macha ☀️"
    except: return "Brightness control-la problem."

def get_system_stats(stat):
    try:
        if stat=="battery":
            battery = psutil.sensors_battery()
            if battery: return f"Battery {battery.percent}% iruku macha. {'Charging' if battery.power_plugged else 'Discharging'} 🔋"
        elif stat=="cpu": return f"CPU usage {psutil.cpu_percent(interval=1)}% macha ️"
        elif stat=="ram":
            ram = psutil.virtual_memory()
            return f"RAM {ram.used/(1024**3):.1f}GB / {ram.total/(1024**3):.1f}GB macha 💾"
    except: pass
    return "Stats edukka mudiyala."

def open_folder(folder_name):
    paths = {"downloads":os.path.expanduser("~/Downloads"),"documents":os.path.expanduser("~/Documents"),"desktop":os.path.expanduser("~/Desktop"),"pictures":os.path.expanduser("~/Pictures"),"videos":os.path.expanduser("~/Videos")}
    path = paths.get(folder_name)
    if path and os.path.exists(path):
        os.startfile(path); return f"{folder_name} folder open panniten macha "
    return "Folder kidaikkala."

def set_reminder(minutes, message):
    try:
        minutes = int(minutes); trigger_time = time.time() + (minutes*60)
        reminders = load_reminders()
        reminders.append({"message":message,"trigger_time":trigger_time,"done":False})
        save_reminders(reminders)
        return f"Reminder set panniten macha! {minutes} mins la alert varum. "
    except: return "Reminder set panna mudiyala."

def run_python_safely(code_string):
    try:
        result = subprocess.run([sys.executable,"-c",code_string.strip()],capture_output=True,text=True,timeout=5,encoding='utf-8')
        if result.returncode==0: return result.stdout.strip() or "Code ran but printed nothing."
        else: return f"Error: {result.stderr.strip().split(chr(10))[-1]}"
    except subprocess.TimeoutExpired: return "Error: Code took too long."
    except Exception as e: return f"Error: {str(e)}"

def track_event(event_type):
    try: print(f"📊 Tracking: {event_type}")
    except: pass

def proactive_speak(text):
    global LAST_PROACTIVE_SPEAK
    if not VOICE_ENABLED: return False
    try:
        LAST_PROACTIVE_SPEAK = time.time()
        audio_buffer, error, mime = generate_tts(text)
        if audio_buffer:
            path = save_audio_file(audio_buffer, mime, "proactive")
            play_mp3_native(path)
            return True
    except: pass
    return False

def automation_thread():
    load_automation()
    time.sleep(20)
    while True:
        try:
            time.sleep(30)
            now = datetime.datetime.now(); today = now.strftime("%Y-%m-%d"); h = now.hour
            if AUTOMATION.get("night_routine") and 22 <= h <= 23 and AUTOMATION_DONE["night"] != today:
                AUTOMATION_DONE["night"] = today
                control_volume("volume_down")
                if VOICE_ENABLED: proactive_speak("Macha, night 10 aachu! Screen off panni thoonguunga. Good night!")
            if AUTOMATION.get("battery_saver") and AUTOMATION_DONE["battery"] != today:
                bat = psutil.sensors_battery()
                if bat and bat.percent < 20 and not bat.power_plugged:
                    AUTOMATION_DONE["battery"] = today
                    try:
                        import screen_brightness_control as sbc
                        sbc.set_brightness(40)
                    except: pass
                    if VOICE_ENABLED: proactive_speak("Macha, battery 20% ku keezha! Charger podunga!")
            if AUTOMATION.get("auto_backup") and h == 23 and AUTOMATION_DONE["backup"] != today:
                AUTOMATION_DONE["backup"] = today
                try:
                    bak = os.path.join(DATA_DIR, "backup"); os.makedirs(bak, exist_ok=True)
                    for f in ["conversation_history.json","long_term_memory.json","reminders.json","automation.json","music_state.json"]:
                        src = os.path.join(DATA_DIR, f)
                        if os.path.exists(src): shutil.copy(src, os.path.join(bak, f))
                    print("💾 Auto backup complete!")
                except: pass
        except: time.sleep(30)

def reminder_checker_thread():
    while True:
        time.sleep(10)
        reminders = load_reminders()
        now = time.time(); updated = False
        for r in reminders:
            if not r.get("done") and r["trigger_time"] <= now:
                r["done"] = True; updated = True
                try:
                    if VOICE_ENABLED:
                        alert_text = f"Macha! Reminder: {r['message']}"
                        audio_buffer, error, mime = generate_tts(alert_text)
                        if audio_buffer:
                            alert_path = save_audio_file(audio_buffer, mime, "reminder_alert")
                            play_mp3_native(alert_path)
                except: pass
        if updated: save_reminders(reminders)

def proactive_thread():
    global MORNING_GREETED_TODAY, EVENING_GREETED_TODAY, WEATHER_ALERTED_TODAY
    time.sleep(15)
    while True:
        try:
            time.sleep(30)
            now = datetime.datetime.now(); current_hour = now.hour; today = now.strftime("%Y-%m-%d")
            idle_time = time.time() - LAST_USER_ACTIVITY
            since_last = time.time() - LAST_PROACTIVE_SPEAK
            if idle_time < 60 or since_last < 300: continue
            temp, rain = get_weather_now()
            if rain >= 60 and WEATHER_ALERTED_TODAY != today:
                WEATHER_ALERTED_TODAY = today
                proactive_speak(f"Macha! {rain}% chance mazhai! Umbrella edunga! 🌂"); continue
            if AUTOMATION.get("morning_routine", True) and 7 <= current_hour <= 11 and MORNING_GREETED_TODAY != today:
                MORNING_GREETED_TODAY = today
                proactive_speak(f"Good morning macha! ☀️ Time {now.strftime('%I:%M %p')}. {weather_report()}"); continue
            if 19 <= current_hour <= 21 and EVENING_GREETED_TODAY != today:
                EVENING_GREETED_TODAY = today
                proactive_speak(f"Good evening macha! 🌙 Long day ah? Coffee sapdringala?"); continue
        except: time.sleep(30)

def take_screenshot():
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"ss_{timestamp}.png")
        if PYAUTOGUI_READY:
            pyautogui.screenshot().save(path)
        with open(path, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{b64}", path
    except: return None, None

def screen_vision(question=""):
    data_url, path = take_screenshot()
    if not data_url: return "Screenshot edukka mudiyala macha 😅"
    q = question or "Describe what is visible on the screen in Tanglish."
    if groq_client is None: return "AI key illa macha 😅"
    messages = [{"role":"user","content":[{"type":"text","text":q},{"type":"image_url","image_url":{"url":data_url}}]}]
    for model in ["meta-llama/llama-4-scout-17b-16e-instruct","qwen/qwen3.6-27b","openai/gpt-oss-120b"]:
        try:
            response = groq_client.chat.completions.create(model=model, messages=messages, max_tokens=600)
            reply = clean_think(response.choices[0].message.content.strip())
            set_brain("👁 Groq Vision")
            return reply
        except: continue
    return "Screen vision work aagala macha 😅"

def load_long_memory():
    if not os.path.exists(MEMORY_FILE): return {"facts": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"facts": []}

def save_long_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

def extract_and_store_memories(user_text):
    try:
        prompt = f"Extract personal facts about the user. Return ONLY a valid JSON array of short fact strings. If none, return []. Message: {user_text}"
        messages = [{"role":"system","content":"Return ONLY a valid JSON array."},{"role":"user","content":prompt}]
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
        if added: print(f" Stored {added} new memories!")
    except: pass

def get_memory_context(query=""):
    mem = load_long_memory()
    facts = mem["facts"]
    if not facts: return ""
    chosen = facts[-12:]
    if not chosen: return ""
    return "\nLONG-TERM MEMORY:\n- " + "\n- ".join(chosen) + "\nUse these naturally when relevant.\n"

def build_system(query=""):
    return SYSTEM_PROMPT + get_memory_context(query) + get_mood_context() + "\nPERSONALITY MODE (" + PERSONALITY["mode"] + "): " + PERSONALITY_PROMPTS.get(PERSONALITY["mode"], PERSONALITY_PROMPTS["friend"])

def generate_image(prompt, n=4):
    try:
        urls = []
        for i in range(n):
            seed = int(time.time() * 1000) % 1000000 + i
            encoded = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&seed={seed}&nologo=true"
            urls.append(url)
        return urls
    except: return None

def get_weather_now():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=13.0827&longitude=80.2707&current=temperature_2m,weather_code,precipitation&hourly=precipitation_probability&forecast_days=1", timeout=10)
        d = r.json()
        cur = d.get("current", {})
        temp = cur.get("temperature_2m")
        hourly = d.get("hourly", {}).get("precipitation_probability", [])
        max_rain = max(hourly) if hourly else 0
        return temp, max_rain
    except: return None, 0

def weather_report():
    temp, rain = get_weather_now()
    if temp is None: return "Weather edukka mudiyala macha 😅"
    rain_note = "— umbrella venum macha! 🌂" if rain >= 50 else "— problem illa! ☀️"
    return f"Macha! Chennai ippo **{temp}°C** iruku. Mazhai chance **{rain}%** {rain_note}"

COIN_IDS = {"bitcoin":"bitcoin","btc":"bitcoin","ethereum":"ethereum","eth":"ethereum","dogecoin":"dogecoin","doge":"dogecoin","solana":"solana","sol":"solana","ripple":"ripple","xrp":"ripple","cardano":"cardano","ada":"cardano"}

def get_crypto(coin="bitcoin"):
    try:
        coin_id = COIN_IDS.get(coin.lower(), coin.lower())
        r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr&include_24hr_change=true", timeout=10)
        d = r.json()
        if coin_id in d:
            usd = d[coin_id].get("usd", 0); inr = d[coin_id].get("inr", 0); change = d[coin_id].get("usd_24h_change", 0)
            trend = "📈" if change >= 0 else "📉"
            return f"{coin_id.capitalize()}: **${usd:,.2f}** (₹{inr:,.2f}) {trend} 24h: {change:+.2f}%"
    except: pass
    return f"{coin} price edukka mudiyala macha."

def translate_text(text, target="english"):
    try:
        prompt = f"Translate to {target}. Return ONLY the translation. Text: {text}"
        messages = [{"role":"system","content":"Return only the translation."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Translate panna mudiyala macha 😅"
    except: return "Translate panna mudiyala macha 😅"

def get_news(category="tamil"):
    try:
        queries = {"tamil":"latest Tamil news","sports":"sports news today","tech":"technology news","cinema":"Tamil cinema news","world":"world news today"}
        q = queries.get(category.lower(), f"{category} news")
        with DDGS() as ddgs:
            results = list(ddgs.news(q, max_results=5))
            headlines = [r.get("title","") for r in results if r.get("title")]
            if headlines:
                summary = "\n".join([f"• {h}" for h in headlines[:5]])
                prompt = f"Give a short friendly Tamil news briefing in 4-5 lines. Call user 'macha'.\n{summary}"
                messages = [{"role":"system","content":"Give news briefing in natural Tamil."},{"role":"user","content":prompt}]
                reply = _groq_complete(messages)
                return reply if reply else summary
    except: pass
    return "News edukka mudiyala macha."

def run_shell_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip() or result.stderr.strip() or "Command executed"
        return f"Command run panniten macha 💻\n{output[:500]}"
    except subprocess.TimeoutExpired: return "Command timeout aachu macha ⏰"
    except Exception as e: return f"Command error: {e}"

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
        elif action == "create_folder":
            os.makedirs(src, exist_ok=True); return f"Folder create panniten: {src} 📁"
        elif action == "list":
            target = src if os.path.isdir(src) else os.path.dirname(src) or "."
            items = os.listdir(target); return f"Files ({len(items)}): {', '.join(items[:20])} 📂"
    except Exception as e: return f"File error: {e}"

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
    except Exception as e: return f"Window error: {e}"

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
    except Exception as e: return f"Process error: {e}"

def clipboard_control(action, text=None):
    try:
        if not PYPERCLIP_READY: return "pyperclip not installed"
        if action == "copy":
            pyperclip.copy(text); return f"Clipboard-ku copy panniten 📋: {text[:50]}"
        elif action == "paste":
            return f"Clipboard content: {pyperclip.paste()[:200]} 📋"
    except Exception as e: return f"Clipboard error: {e}"

def power_control(action):
    if action == "lock":
        ctypes.windll.user32.LockWorkStation(); return "PC lock panniten 🔒"
    elif action == "sleep":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"); return "Sleep mode-ku anuppen 💤"
    elif action == "shutdown":
        os.system("shutdown /s /t 10"); return "10 sec-ıl shutdown 🔌"
    elif action == "restart":
        os.system("shutdown /r /t 10"); return "10 sec-ıl restart 🔄"
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

def launch_app(app_name):
    apps = {"chrome":"chrome","firefox":"firefox","vscode":"code","notepad":"notepad","calculator":"calc","spotify":"spotify","telegram":"telegram","whatsapp":"whatsapp","vlc":"vlc","edge":"msedge"}
    cmd = apps.get(app_name, app_name)
    try:
        os.system(f'start {cmd}')
        return f"{app_name.capitalize()} open panniten macha "
    except: return f"{app_name} open panna mudiyala macha."

def get_cricket_score(query=""):
    try:
        response = requests.get("https://api.cricapi.com/v1/currentMatches?apikey=free", timeout=10)
        if response.status_code == 200:
            matches = response.json().get("data", [])
            if not matches: return "Cricket score edukka mudiyala macha."
            live_match=None; recent_match=None
            for match in matches:
                status = match.get("status","").lower()
                if "live" in status or "in progress" in status: live_match=match; break
                elif "completed" in status or "result" in status:
                    if not recent_match: recent_match=match
            target = live_match or recent_match
            if target:
                teams=target.get("teams",[]); score=target.get("score",[]); status=target.get("status","")
                rt=f"🏏 {status}\n"
                if len(teams)>=2: rt+=f"**{teams[0]}** vs **{teams[1]}**\n"
                for i,s in enumerate(score[:2]):
                    rt+=f" {s.get('inning',f'Innings {i+1}')}: {s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} overs)\n"
                return f"Macha! {rt}"
    except: pass
    return "Cricket score edukka mudiyala macha."

def summarize_youtube(url):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        m = re.search(r'(?:v=|youtu\.be/)([\w-]{11})', url)
        if not m: return "YouTube link sari illa macha 🔗"
        vid = m.group(1)
        try: data = YouTubeTranscriptApi.get_transcript(vid)
        except: data = YouTubeTranscriptApi().fetch(vid)
        full = " ".join([t["text"] for t in data])[:6000]
        if not full.strip(): return "Transcript kidaikkala macha"
        prompt = f"Summarize this YouTube video in Tanglish. Give 4-6 bullet points. Call user 'macha'.\nTranscript: {full}"
        messages = [{"role":"system","content":"Summarize in natural Tamil."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Summary edukka mudiyala macha"
    except Exception as e: return f"YouTube summary edukka mudiyala: {e}"

def smart_web_search(query):
    try:
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
        context = "\n".join(results[:3])
        summary_prompt = f"Summarize this in 3 sentences in Tanglish. Call user 'macha'.\nResults: {context}\nQuestion: {query}"
        messages = [{"role":"system","content":"Summarize search results in natural spoken Tamil."},{"role":"user","content":summary_prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Macha, AI daily limit mudinjiduchu."
    except: return f"Macha, search-la problem."

def generate_morning_briefing():
    try:
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %d %B %Y"); time_str = now.strftime("%I:%M %p")
        weather = weather_report()
        prompt = f"Give a friendly morning briefing in spoken Tamil. Include date ({date_str}), time ({time_str}), weather ({weather}). Keep it under 8 sentences."
        messages = [{"role":"system","content":build_system()},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else f"Good morning macha! ☀️ Ippo time {time_str}."
    except: return f"Good morning macha! ☀️ Briefing-ku internet problem."

def _groq_complete(messages):
    if groq_client is None: return None
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
    return None

def ask_groq(user_text):
    if groq_client is None:
        return "மச்சா 😅 AI API keys கிடைக்கவில்லை."
    models_to_try = [GROQ_MODEL,"qwen/qwen3.6-27b","openai/gpt-oss-20b","meta-llama/llama-4-scout-17b-16e-instruct","llama-3.1-8b-instant","gemma2-9b-it","llama3-8b-8192"]
    if groq_client:
        for model in models_to_try:
            try:
                messages = [{"role":"system","content":build_system(user_text)}]
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
                if any(k in error_str.lower() for k in ["429","rate_limit","404","decommission","connect","network","unreachable","refused","timeout","dns","resolve"]): continue
                return "மச்சா 😅 Groq AI-ல ஒரு பிரச்சனை வந்திருக்கு."
    return "மச்சா 😅 AI down. 5 mins la try pannunga."

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TTS_BLOCKED_DAY = None

def pcm_to_wav(pcm_bytes, rate=24000):
    import wave
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm_bytes)
    return buf.getvalue()

def pcm_to_mp3(pcm_bytes, rate=24000):
    if LAMEENC_READY:
        try:
            enc = lameenc.Encoder()
            enc.set_bit_rate(128); enc.set_in_sample_rate(rate); enc.set_channels(1); enc.set_quality(2)
            mp3_data = enc.encode(pcm_bytes) + enc.flush()
            buf = io.BytesIO(mp3_data); buf.seek(0)
            return buf
        except: pass
    if PYDUB_READY:
        try:
            wav_bytes = pcm_to_wav(pcm_bytes, rate)
            audio = AudioSegment.from_wav(io.BytesIO(wav_bytes))
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format="mp3", bitrate="128k")
            mp3_io.seek(0)
            return mp3_io
        except: pass
    return None

def gemini_tts(text):
    global GEMINI_TTS_BLOCKED_DAY
    if not GEMINI_API_KEY: return None
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if GEMINI_TTS_BLOCKED_DAY == today: return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        clean = text.replace("**","").replace("*","").replace("`","")
        clean = re.sub(r'\[\[.*?\]\]','',clean)
        clean = re.sub(r'\[.*?\]','',clean)
        clean = re.sub(r'[*_#>]','',clean)
        clean = re.sub(r'\s+',' ',clean).strip()[:1000]
        if len(clean) < 3: return None
        resp = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=clean,
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
        mp3_buf = pcm_to_mp3(pcm, rate)
        if mp3_buf: return mp3_buf, "audio/mpeg"
        wav_bytes = pcm_to_wav(pcm, rate)
        buf = io.BytesIO(wav_bytes); buf.seek(0)
        return buf, "audio/wav"
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            GEMINI_TTS_BLOCKED_DAY = today
        return None

def google_tts(text):
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        clean = text.replace("**","").replace("*","").replace("`","")
        clean = re.sub(r'\[.*?\]','',clean)
        clean = re.sub(r'\s+',' ',clean).strip()[:1500]
        gTTS(text=clean, lang='ta', slow=False).write_to_fp(buf)
        buf.seek(0)
        if buf.getbuffer().nbytes > 0: return buf
    except: pass
    return None

EMOJI_PATTERN = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E6-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+", flags=re.UNICODE)

def clean_text_for_tts(text):
    text = EMOJI_PATTERN.sub(" ", str(text))
    text = re.sub(r"\[\[.*?\]\]", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"[*_#`>]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000] if len(text) > 2000 else text

async def _generate_edge_tts_async(text):
    global EDGE_TTS_VOICE
    try:
        voice_to_use = EDGE_TTS_VOICE
        communicate = edge_tts.Communicate(text, voice_to_use, rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH, volume=EDGE_TTS_VOLUME)
        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type")=="audio": audio_buffer.write(chunk.get("data", b""))
        audio_buffer.seek(0)
        if audio_buffer.getbuffer().nbytes == 0: raise Exception("Empty audio buffer")
        return audio_buffer
    except: raise

def piper_tts(text: str) -> io.BytesIO | None:
    if not PIPER_READY or piper_voice is None: return None
    try:
        import wave
        import tempfile
        cleaned = text.replace("**", "").replace("*", "")
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()[:2000]
        if len(cleaned) < 3: return None
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp_path, 'wb') as wav_file:
                piper_voice.synthesize(cleaned, wav_file)
            with open(tmp_path, 'rb') as f:
                buf = io.BytesIO(f.read())
            os.unlink(tmp_path)
            buf.seek(0)
            if buf.getbuffer().nbytes > 0: return buf
    except: pass
    return None

def generate_tts(text):
    try:
        cleaned_text = clean_text_for_tts(text)
        if not cleaned_text or len(cleaned_text) < 3:
            return None, "No speakable text", "audio/mpeg"
        if len(cleaned_text) < 300:
            buf = google_tts(cleaned_text)
            if buf: return buf, None, "audio/mpeg"
        result = gemini_tts(cleaned_text)
        if result:
            buf, mime = result
            return buf, None, mime
        buf = google_tts(cleaned_text)
        if buf: return buf, None, "audio/mpeg"
        piper_buf = piper_tts(cleaned_text)
        if piper_buf: return piper_buf, None, "audio/wav"
        try:
            buf = asyncio.run(_generate_edge_tts_async(cleaned_text))
            if buf and buf.getbuffer().nbytes > 0: return buf, None, "audio/mpeg"
        except: pass
        return None, "All TTS failed", "audio/mpeg"
    except Exception as error:
        return None, f"TTS error: {error}", "audio/mpeg"

def strip_img_token(text):
    if not text: return "", None
    text = str(text)
    m = re.search(r'\[\[GALLERY:(.*?)\]\]', text)
    if m:
        urls = [u for u in m.group(1).split("|") if u]
        return text.replace(m.group(0), "").strip(), {"type": "gallery", "urls": urls}
    m2 = re.search(r'\[\[IMG:(.*?)\]\]', text)
    if m2:
        return text.replace(m2.group(0), "").strip(), {"type": "single", "url": m2.group(1)}
    return text, None

SKILLS_FILE = os.path.join(DATA_DIR, "skills.json")
def load_skills():
    try:
        if os.path.exists(SKILLS_FILE):
            with open(SKILLS_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return []

def save_skills(s):
    try:
        with open(SKILLS_FILE, "w", encoding="utf-8") as f: json.dump(s, f, ensure_ascii=False, indent=2)
    except: pass

QUIZ_STATE = {"active": False, "questions": [], "index": 0, "score": 0, "topic": ""}

def start_quiz(topic):
    global QUIZ_STATE
    try:
        prompt = f"""Create a 5-question multiple choice quiz about: {topic}
Return ONLY valid JSON array like:
[{{"q":"question?","options":["opt1","opt2","opt3","opt4"],"answer":0}}]
answer = index of correct option (0-3)."""
        messages = [{"role":"system","content":"Return ONLY valid JSON array."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        m = re.search(r'\[.*\]', reply or "", re.DOTALL)
        qs = json.loads(m.group(0))
        if not isinstance(qs, list) or len(qs) < 1: raise Exception("bad quiz")
        QUIZ_STATE = {"active": True, "questions": qs[:5], "index": 0, "score": 0, "topic": topic}
        return quiz_question_text()
    except: return "Quiz generate panna mudiyala macha 😅"

def quiz_question_text():
    q = QUIZ_STATE["questions"][QUIZ_STATE["index"]]
    out = f"🧠 **QUIZ ({QUIZ_STATE['index']+1}/{len(QUIZ_STATE['questions'])})** — Topic: **{QUIZ_STATE['topic']}**\n**{q['q']}**\n"
    for i, o in enumerate(q.get("options", [])):
        out += f"\n**{i+1}** • {o}"
    out += "\n👉 Answer sollu macha! (1-4) • 'quit quiz' = exit"
    return out

def answer_quiz(ans_text):
    global QUIZ_STATE
    q = QUIZ_STATE["questions"][QUIZ_STATE["index"]]
    correct = int(q.get("answer", 0))
    t = ans_text.strip().lower()
    chosen = -1
    if t in ["1","2","3","4"]: chosen = int(t)-1
    elif t in ["a","b","c","d"]: chosen = ord(t)-97
    else:
        for i, o in enumerate([str(x).lower() for x in q.get("options", [])]):
            if t and (t in o or o in t): chosen = i; break
    right = chosen == correct
    if right: QUIZ_STATE["score"] += 1
    QUIZ_STATE["index"] += 1
    if QUIZ_STATE["index"] >= len(QUIZ_STATE["questions"]):
        s = QUIZ_STATE["score"]; tot = len(QUIZ_STATE["questions"]); tp = QUIZ_STATE["topic"]
        QUIZ_STATE = {"active": False, "questions": [], "index": 0, "score": 0, "topic": ""}
        msg = f"🎉 **QUIZ COMPLETE!** Score: **{s}/{tot}** "
        if s == tot: msg += "— FULL MARKS macha! 🏆 Genius!"
        elif s >= tot-1: msg += "— Super macha! 🔥"
        elif s >= tot//2: msg += "— Nalla iruku macha! "
        else: msg += "— Paravala, next time adichu dhu! 💪"
        return msg
    fb = "✅ Correct macha! 🎉" if right else f"❌ Thappu macha! Correct: **{q['options'][correct]}**"
    return fb + "\n" + quiz_question_text()

FOCUS_TIMER = {"active": False, "end_time": 0, "duration": 1500, "mode": "work"}

def timer_thread():
    global FOCUS_TIMER
    while True:
        time.sleep(1)
        if FOCUS_TIMER.get("active") and time.time() >= FOCUS_TIMER["end_time"]:
            mode = FOCUS_TIMER["mode"]
            FOCUS_TIMER["active"] = False
            if mode == "work":
                proactive_speak("Macha! 25 minutes mudinjiduchu. Oru 5 minutes break eduthukko.")
            else:
                proactive_speak("Macha! Break over. Thirumba focus time!")

NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
def load_notes():
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return {"notes": [], "todos": []}

def save_notes(d):
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
    except: pass

DAILY_LOG = os.path.join(DATA_DIR, "daily_log.json")
def track_event(kind):
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log = {}
        if os.path.exists(DAILY_LOG):
            with open(DAILY_LOG, "r", encoding="utf-8") as f: log = json.load(f)
        d = log.get(today, {"msgs":0,"quiz":0,"songs":0,"shots":0,"notes":0})
        d[kind] = d.get(kind,0) + 1
        log[today] = d
        with open(DAILY_LOG, "w", encoding="utf-8") as f: json.dump(log, f)
    except: pass

def get_today_stats():
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(DAILY_LOG):
            with open(DAILY_LOG, "r", encoding="utf-8") as f: log = json.load(f)
            return log.get(today, {"msgs":0,"quiz":0,"songs":0,"shots":0,"notes":0})
    except: pass
    return {"msgs":0,"quiz":0,"songs":0,"shots":0,"notes":0}

def fmt_uptime(s):
    h=s//3600; m=(s%3600)//60
    return f"{h}h {m}m" if h else f"{m}m"

SYSTEM_START = time.time()

def build_daily_report():
    s = get_today_stats()
    score = min(100, s.get("msgs",0)*4 + s.get("quiz",0)*10 + s.get("notes",0)*8 + s.get("songs",0)*2 + s.get("shots",0)*3)
    grade = "S" if score>=80 else "A" if score>=60 else "B" if score>=40 else "C"
    temp, rain = get_weather_now()
    now = datetime.datetime.now()
    lines = [
        f"📊 **DAILY REPORT** — {now.strftime('%A, %d %B %Y')}",
        f"💬 Messages: **{s.get('msgs',0)}** • 🧠 Quiz: **{s.get('quiz',0)}** •  Notes: **{s.get('notes',0)}**",
        f"🎵 Songs: **{s.get('songs',0)}** •  Screenshots: **{s.get('shots',0)}**",
        f"🏆 Productivity Score: **{score}% (Grade {grade})**",
    ]
    if temp is not None:
        lines.append(f"🌦 Chennai: **{temp}°C**, rain chance **{rain}%**")
    lines.append(f"🕐 Uptime: {fmt_uptime(int(time.time()-SYSTEM_START))}")
    return "\n".join(lines)

def process_command(original_text, _skill_depth=0):
    global LAST_USER_ACTIVITY
    text = original_text.lower()
    t = text
    LAST_USER_ACTIVITY = time.time()
    if not original_text: return "மச்சா 😅 ஏதாவது type பண்ணு."
    threading.Thread(target=extract_and_store_memories, args=(original_text,), daemon=True).start()
    threading.Thread(target=detect_emotion, args=(original_text,), daemon=True).start()
    track_event("msgs")
    if QUIZ_STATE.get("active"):
        if t in ["quit quiz","stop quiz","exit quiz"]:
            QUIZ_STATE["active"] = False
            return "🧠 Quiz quit panniten macha!"
        return answer_quiz(original_text)
    if t.startswith("quiz") or "quiz me" in t or "quiz:" in t:
        topic = re.sub(r'\b(quiz|me|on|about|please|sollu)\b|:', '', t).strip() or "general knowledge"
        return start_quiz(topic)
    teach_m = re.search(r'teach\s*(?:me)?\s*:?\s*(?:when i say\s+)?(.+?)\s+(?:do|then|→|\|)\s+(.+)', original_text, re.IGNORECASE)
    if teach_m:
        trig = teach_m.group(1).strip().lower(); act = teach_m.group(2).strip()
        if trig and act:
            skills = load_skills()
            skills = [s for s in skills if s["trigger"] != trig]
            skills.append({"trigger": trig, "do": act})
            save_skills(skills)
            return f"🎓 Skill kathukitten macha! Inimel '**{trig}**' sonna → '**{act}**' pannuven!"
    if t in ["show skills","my skills","skills"]:
        skills = load_skills()
        if not skills: return "Skills edhuvum illa macha 🎓\n**Try:** 'teach: when I say movie time do open youtube'"
        return "🎓 **Learned Skills:**\n" + "\n".join([f"• '{s['trigger']}' → {s['do']}" for s in skills])
    if t.startswith("forget skill"):
        trig = t.replace("forget skill","").strip()
        save_skills([s for s in load_skills() if s["trigger"] != trig])
        return f"️ Skill '{trig}' maranduten macha."
    if "focus" in text and ("start" in text or "on" in text or "begin" in text):
        FOCUS_TIMER = {"active": True, "end_time": time.time() + 1500, "duration": 1500, "mode": "work"}
        return "⏱️ **Focus Timer Started!** 25 minutes deep work macha."
    if "break" in text and ("start" in text or "on" in text):
        FOCUS_TIMER = {"active": True, "end_time": time.time() + 300, "duration": 300, "mode": "break"}
        return "☕ **Break Timer Started!** 5 minutes relax macha."
    if ("stop" in text or "cancel" in text) and "timer" in text:
        FOCUS_TIMER["active"] = False
        return "⏹️ Timer stop panniten macha!"
    if "timer" in text and ("status" in text or "time" in text or "left" in text):
        if FOCUS_TIMER["active"]:
            rem = int(FOCUS_TIMER["end_time"] - time.time())
            m, s = divmod(rem, 60)
            return f"⏱️ **{FOCUS_TIMER['mode'].capitalize()} Timer** running macha! {m} mins {s} secs remaining."
        return "Timer edhuvum run aagala macha."
    if text in ["daily report","report","daily report sollu","report sollu","daily summary"]:
        return build_daily_report()
    if text in ["good morning","morning","briefing","kaalai vanakkam"]:
        return generate_morning_briefing()
    if text in ["youtube","open youtube"]:
        webbrowser.open("https://www.youtube.com"); return "YouTube open பண்ணிட்டேன் மச்சா 🎵"
    if text in ["google","open google"]:
        webbrowser.open("https://www.google.com"); return "Google open பண்ணிட்டேன் மச்சா 🌐"
    if text in ["calculator","open calculator"]:
        os.system("start calc.exe"); return "Calculator open பண்ணிட்டேன் மச்சா 🧮"
    if text in ["time","what is the time","current time","time sollu"]:
        return f"இப்போ நேரம் {datetime.datetime.now().strftime('%I:%M %p')} மச்சா "
    if text in ["weather","weather enna","mazhiya","weather update"]:
        return weather_report()
    if text in ["screenshot","take screenshot","screen capture","screen eduppu"]:
        data_url, info = take_screenshot()
        return f"Screenshot eduthuten macha! 📸 File: {info}" if data_url else f"Screenshot edukka mudiyala: {info}"
    if text in ["mouse position","where is mouse","mouse eng"]:
        return mouse_position()
    if ("story" in text or "kathai" in text or "கதை" in text):
        topic = re.sub(r'(story|kathai|கதை|about|please|sollu|write|a|an|the)', '', original_text, flags=re.I).strip() or "a brave kid"
        return f"📖 Story about {topic} - coming soon macha!"
    if text.startswith("note:") or text.startswith("note "):
        t = original_text.split(":",1)[-1].strip() if ":" in original_text else original_text[5:].strip()
        d = load_notes(); d["notes"].append({"text": t, "time": time.time()}); save_notes(d)
        return f"📝 Note save panniten macha! '{t}'"
    if text.startswith("todo:") or text.startswith("todo "):
        t = original_text.split(":",1)[-1].strip() if ":" in original_text else original_text[5:].strip()
        d = load_notes(); d["todos"].append({"text": t, "done": False, "time": time.time()}); save_notes(d)
        return f"✅ To-Do add panniten macha! '{t}'"
    if text in ["show notes","my notes","notes","my todos"]:
        d = load_notes()
        if not d["notes"] and not d["todos"]: return "Notes edhuvum illa macha 📝\n**Try:** 'note: buy milk' / 'todo: gym at 6pm'"
        out = " **Notes:**\n" + ("\n".join([f"• {n['text']}" for n in d["notes"][-5:]]) or "—")
        out += "\n✅ **To-Do:**\n" + ("\n".join([f"{'☑' if t['done'] else '☐'} {t['text']}" for t in d["todos"][-6:]]) or "—")
        return out
    if _skill_depth < 2:
        for s in load_skills():
            if s.get("trigger") and s["trigger"] in t:
                return process_command(s["do"], _skill_depth+1)
    yt_link = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s]+)', original_text)
    if yt_link:
        return summarize_youtube(yt_link.group(1))
    if ("screen" in text and "shot" not in text):
        return screen_vision(original_text)
    ai_reply = ask_groq(original_text)
    if not ai_reply:
        ai_reply = "மச்சா 😅 AI-க்கு ஒரு chinna issue. Thirumba try pannunga."
    final_reply = ai_reply
    code_match = re.search(r'\[CODE\](.*?)\[/CODE\]', ai_reply, re.DOTALL | re.IGNORECASE)
    if code_match:
        execution_result = run_python_safely(code_match.group(1).strip())
        final_reply = ai_reply.replace(code_match.group(0), f"\n**Answer:** `{execution_result}`")
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
    crypto_match = re.search(r'\[CRYPTO:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    translate_match = re.search(r'\[TRANSLATE:\s*(.*?)\|(.*?)\]', ai_reply, re.IGNORECASE)
    news_match = re.search(r'\[NEWS:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    if image_match:
        img_urls = generate_image(image_match.group(1).strip(), n=4)
        if img_urls:
            final_reply = f"🎨 **4 HD images** generate panniten macha!\n[[GALLERY:{'|'.join(img_urls)}]]"
        else:
            final_reply = "Image generate panna mudiyala macha 😅"
    elif yt_match:
        final_reply = summarize_youtube(yt_match.group(1).strip())
    elif weather_match:
        final_reply = weather_report()
    elif screenshot_match:
        data_url, info = take_screenshot()
        final_reply = f"Screenshot eduthuten macha! 📸 File: {info}" if data_url else f"Screenshot edukka mudiyala: {info}"
    elif click_match:
        coords = click_match.group(1).strip()
        final_reply = click_at(*coords.split(",")) if "," in coords else click_at(coords, None)
    elif type_match:
        final_reply = type_text(type_match.group(1).strip())
    elif scroll_match:
        args = scroll_match.group(1).strip().split()
        final_reply = scroll_screen(args[0] if args else "down", args[1] if len(args)>1 else "3")
    elif cmd_match:
        final_reply = run_shell_command(cmd_match.group(1).strip())
    elif file_match:
        parts = [p.strip() for p in file_match.group(1).split("|")]
        final_reply = file_operation(parts[0] if parts else "list", parts[1] if len(parts)>1 else None, parts[2] if len(parts)>2 else None)
    elif window_match:
        parts = [p.strip() for p in window_match.group(1).split("|")]
        final_reply = window_control(parts[0] if parts else "minimize_all", parts[1] if len(parts)>1 else None)
    elif process_match:
        parts = [p.strip() for p in process_match.group(1).split("|")]
        final_reply = process_control(parts[0] if parts else "list", parts[1] if len(parts)>1 else None)
    elif clip_match:
        parts = [p.strip() for p in clip_match.group(1).split("|")]
        final_reply = clipboard_control(parts[0] if parts else "paste", parts[1] if len(parts)>1 else None)
    elif power_match:
        final_reply = power_control(power_match.group(1).strip().lower())
    elif play_match:
        q = play_match.group(1).strip()
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
        MUSIC_STATE["playing"] = True; MUSIC_STATE["title"] = q; save_music()
        final_reply = f"YouTube-la '{q}' play pannuren macha 🎵"
    elif search_match:
        final_reply = smart_web_search(search_match.group(1).strip())
    elif open_match:
        urls = {"whatsapp":"https://web.whatsapp.com/","instagram":"https://www.instagram.com/","spotify":"https://open.spotify.com/","netflix":"https://www.netflix.com/","youtube":"https://www.youtube.com/","google":"https://www.google.com/"}
        app_name = open_match.group(1).strip().lower()
        if app_name in urls:
            webbrowser.open(urls[app_name]); final_reply = f"{app_name.capitalize()} open pannuren macha 🚀"
        else: final_reply = f"{app_name} open panna mudiyala macha."
    elif action_match:
        action = action_match.group(1).strip().lower()
        if action in ["volume_up","volume_down","mute"]: final_reply = control_volume(action)
        elif action in ["media_play_pause","media_next","media_prev"]: final_reply = control_media(action)
        elif action in ["brightness_up","brightness_down"]: final_reply = control_brightness(action)
        elif action == "shutdown": final_reply = power_control("shutdown")
        elif action == "restart": final_reply = power_control("restart")
        else: final_reply = f"{action} action work aagala macha."
    elif system_match:
        final_reply = get_system_stats(system_match.group(1).strip().lower())
    elif folder_match:
        final_reply = open_folder(folder_match.group(1).strip().lower())
    elif app_match:
        final_reply = launch_app(app_match.group(1).strip().lower())
    elif cricket_match:
        final_reply = get_cricket_score(cricket_match.group(1).strip())
    elif reminder_match:
        final_reply = set_reminder(reminder_match.group(1).strip(), reminder_match.group(2).strip())
    elif crypto_match:
        final_reply = get_crypto(crypto_match.group(1).strip())
    elif translate_match:
        final_reply = translate_text(translate_match.group(2).strip(), translate_match.group(1).strip())
    elif news_match:
        final_reply = get_news(news_match.group(1).strip())
    add_to_memory("user", original_text); add_to_memory("model", final_reply)
    return final_reply

def telegram_bot_thread():
    if not TELEGRAM_AVAILABLE or not TELEGRAM_BOT_TOKEN: return
    try:
        async def start_cmd(update, context):
            await update.message.reply_text(" Vasanth AI online macha!")
        async def handle_message(update, context):
            user_text = update.message.text
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

HTML = r"""<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vasanth AI</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0d0721">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:linear-gradient(135deg,#0f0a1e 0%,#1e1b4b 100%);color:#fff;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;}
.app{width:min(900px,100%);height:min(900px,95vh);border-radius:24px;overflow:hidden;display:flex;flex-direction:column;border:2px solid rgba(0,255,200,.3);box-shadow:0 0 30px rgba(0,255,200,.15);background:rgba(6,8,22,.92);}
.header{padding:16px 24px;background:rgba(0,0,0,.5);border-bottom:2px solid rgba(0,255,200,.2);display:flex;align-items:center;justify-content:space-between;}
.title{font-size:22px;font-weight:900;letter-spacing:3px;background:linear-gradient(135deg,#00ffc8,#ff2d95);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.online{display:inline-flex;align-items:center;gap:6px;color:#00ffc8;font-size:11px;font-weight:700;}
.dot{width:9px;height:9px;border-radius:50%;background:#00ffc8;box-shadow:0 0 16px #00ffc8;animation:pulse 1.5s infinite;}
@keyframes pulse{50%{opacity:.3;transform:scale(.7)}}
#chat{flex:1;padding:20px;overflow-y:auto;}
.message{margin:12px 0;padding:14px 18px;border-radius:16px;max-width:80%;line-height:1.6;}
.message.user{background:linear-gradient(135deg,rgba(255,45,149,.85),rgba(0,180,255,.85));margin-left:auto;border-bottom-right-radius:4px;}
.message.ai{background:rgba(0,10,30,.7);border:1px solid rgba(0,255,200,.12);border-bottom-left-radius:4px;}
.message b{color:#00ffc8;}
.message code{background:rgba(0,255,200,.08);padding:2px 8px;border-radius:6px;font-family:monospace;}
.bottom{padding:16px 20px;background:rgba(0,0,0,.55);border-top:2px solid rgba(0,255,200,.15);}
.composer{display:flex;gap:10px;align-items:center;}
input{flex:1;padding:14px 20px;border:2px solid rgba(0,255,200,.2);border-radius:999px;outline:none;background:rgba(0,8,20,.7);color:#fff;font-size:15px;}
input:focus{border-color:rgba(0,255,200,.6);box-shadow:0 0 20px rgba(0,255,200,.15);}
input::placeholder{color:#6b8a9e;}
.action-btn{width:50px;height:50px;border:none;border-radius:16px;cursor:pointer;font-size:20px;color:white;transition:all .25s;}
.action-btn:hover{transform:translateY(-3px) scale(1.1);}
.mic{background:linear-gradient(135deg,#00c853,#00897b);}
.send{background:linear-gradient(135deg,#00ffc8,#00b4ff);}
.quick-actions{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.quick-btn{padding:8px 16px;border-radius:999px;border:1px solid rgba(0,255,200,.15);background:rgba(0,255,200,.03);color:#fff;font-size:12px;cursor:pointer;transition:all .25s;}
.quick-btn:hover{transform:translateY(-2px);border-color:rgba(0,255,200,.45);}
</style>
</head>
<body>
<div class="app">
<div class="header">
<div>
<div class="title">VASANTH AI <span style="font-size:10px;background:linear-gradient(135deg,#00ffc8,#ff2d95);padding:3px 10px;border-radius:8px;color:#020208;-webkit-text-fill-color:#020208;">ROYAL</span></div>
<div class="online"><span class="dot"></span>Online</div>
</div>
<button onclick="toggleSettings()" style="width:44px;height:44px;border-radius:14px;border:2px solid rgba(0,255,200,.3);background:rgba(0,255,200,.05);color:#fff;font-size:20px;cursor:pointer;">⚙️</button>
</div>
<div id="chat"></div>
<div class="bottom">
<div class="quick-actions">
<button class="quick-btn" onclick="quickSend('Draw a cute robot')">🎨 Draw</button>
<button class="quick-btn" onclick="quickSend('Weather enna?')">🌦️ Weather</button>
<button class="quick-btn" onclick="quickSend('Bitcoin price')">📈 Crypto</button>
<button class="quick-btn" onclick="quickSend('Today news sollu')">📰 News</button>
<button class="quick-btn" onclick="quickSend('India cricket score')">🏏 Cricket</button>
<button class="quick-btn" onclick="quickSend('Play AR Rahman songs')">🎵 Music</button>
<button class="quick-btn" onclick="quickSend('Take screenshot')">📸 Screen</button>
<button class="quick-btn" onclick="quickSend('Quiz me')">🧠 Quiz</button>
</div>
<div class="composer">
<input id="message" type="text" placeholder="Say 'Macha' or type..." onkeypress="if(event.key==='Enter')sendMessage()">
<button class="action-btn mic" onclick="startVoice()">🎤</button>
<button class="action-btn send" onclick="sendMessage()"></button>
</div>
</div>
</div>
<script>
const chat=document.getElementById("chat"),input=document.getElementById("message");
let voiceEnabled=true;
function escapeTime(){return new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});}
function formatText(t){let s=t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");s=s.replace(/\*\*(.*?)\*\*/g,"<b>$1</b>");s=s.replace(/`(.*?)`/g,"<code>$1</code>");return s;}
function addMessage(t,type){const b=document.createElement("div");b.className="message "+type;b.innerHTML=formatText(t);chat.appendChild(b);chat.scrollTop=chat.scrollHeight;}
function showWelcome(){chat.innerHTML="";addMessage("வணக்கம் Vasanth! 👋\n**PREMIUM EDITION** 💎\n 6 Themes\n🖼️ 4-Image Gallery\n🎵 Music Player\n Fast Voice\n📱 Mobile Ready\n🤖 JARVIS Mode\n\n**Try:** 'Draw a cyberpunk city' / 'Play AR Rahman songs'","ai");}
async function loadHistory(){try{const r=await fetch("/history");const d=await r.json();chat.innerHTML="";if(!d.history||d.history.length===0){showWelcome();return;}d.history.forEach(i=>{addMessage(i.text||"",(i.role==="user"?"user":"ai"));});}catch(e){showWelcome();}}
async function clearChat(){if(!confirm("Clear history?"))return;try{await fetch("/clear",{method:"POST"});showWelcome();}catch(e){alert("Error");}}
async function sendMessage(){const t=input.value.trim();if(!t)return;addMessage(t,"user");input.value="";try{const r=await fetch("/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t})});const d=await r.json();addMessage(d.reply||"...","ai");if(voiceEnabled){await fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:d.reply})});}}catch(e){addMessage("Server error","ai");}}
function quickSend(t){input.value=t;sendMessage();}
function startVoice(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){alert("Chrome use pannu macha");return;}const r=new SR();r.lang="ta-IN";r.onresult=(e)=>{input.value=e.results[0][0].transcript;sendMessage();};r.onerror=(e)=>{alert("Mic error: "+e.error);};try{r.start();}catch(e){}}
function toggleSettings(){alert("Settings coming soon!");}
loadHistory();
</script>
</body>
</html>"""

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
    if not text: return jsonify({"success": False}), 400
    audio_buffer, error, mime = generate_tts(text)
    if audio_buffer is None: return jsonify({"success": False, "error": error}), 503
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
    for model in ["meta-llama/llama-4-scout-17b-16e-instruct","qwen/qwen3.6-27b","openai/gpt-oss-120b"]:
        try:
            response = groq_client.chat.completions.create(model=model, messages=messages, max_tokens=600)
            content = response.choices[0].message.content
            reply = clean_think(content.strip() if content else "")
            set_brain("⚡ Groq")
            return jsonify({"reply": reply, "brain": LAST_BRAIN})
        except Exception as e:
            if any(k in str(e) for k in ["404","429","rate","decommission"]): continue
            return jsonify({"reply": f"மச்சா 😅 Vision error: {str(e)[:100]}"})
    return jsonify({"reply": "மச்சா 😅 Vision AI work aagala."})

@app.route("/command", methods=["POST"])
def command():
    data = request.get_json(silent=True) or {}
    original_text = str(data.get("command", "")).strip()
    try:
        result = process_command(original_text)
    except Exception as e:
        import traceback; traceback.print_exc()
        result = f"மச்சா 😅 Chinna error: {e}"
    reply, image_data = strip_img_token(result)
    return jsonify({"reply": reply, "brain": LAST_BRAIN, "image": image_data})

@app.route("/change-voice", methods=["POST"])
def change_voice():
    global EDGE_TTS_VOICE, EDGE_TTS_RATE, EDGE_TTS_PITCH
    data = request.get_json(silent=True) or {}
    key = data.get("voice", "pallavi")
    prof = VOICE_PROFILES.get(key, VOICE_PROFILES["pallavi"])
    EDGE_TTS_VOICE = prof["voice"]; EDGE_TTS_RATE = prof["rate"]; EDGE_TTS_PITCH = prof["pitch"]
    return jsonify({"success": True, "name": prof["label"]})

@app.route("/voice/on", methods=["POST"])
def voice_on():
    global VOICE_ENABLED
    VOICE_ENABLED = True
    return jsonify({"success": True})

@app.route("/voice/off", methods=["POST"])
def voice_off():
    global VOICE_ENABLED
    VOICE_ENABLED = False
    return jsonify({"success": True})

@app.route("/voice/stop", methods=["POST"])
def voice_stop():
    try:
        ctypes.windll.winmm.mciSendStringW('stop vasanth_audio', None, 0, 0)
        ctypes.windll.winmm.mciSendStringW('close vasanth_audio', None, 0, 0)
    except: pass
    return jsonify({"success": True})

@app.route("/api/stats")
def api_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        bat = psutil.sensors_battery()
        return jsonify({
            "cpu": cpu, "ram_pct": ram.percent,
            "ram_used": round(ram.used/1024**3,1), "ram_total": round(ram.total/1024**3,1),
            "battery": bat.percent if bat else None,
            "charging": bool(bat.power_plugged) if bat else None,
            "uptime": int(time.time() - SYSTEM_START),
            "messages": len(conversation_history),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/weather")
def api_weather():
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=13.0827&longitude=80.2707&current=temperature_2m,relative_humidity_2m,wind_speed_10m&hourly=precipitation_probability&forecast_days=1", timeout=10)
        d = r.json()
        return jsonify({
            "temp": round(d["current"]["temperature_2m"]),
            "hum": d["current"]["relative_humidity_2m"],
            "wind": d["current"]["wind_speed_10m"],
            "rain": max(d["hourly"]["precipitation_probability"]),
        })
    except: return jsonify({"temp": None, "hum": None, "wind": None, "rain": None})

@app.route("/api/notes", methods=["GET","POST"])
def api_notes():
    d = load_notes()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        act = data.get("action")
        if act == "add_note":
            d["notes"].append({"text": data.get("text",""), "time": time.time()})
        elif act == "add_todo":
            d["todos"].append({"text": data.get("text",""), "done": False, "time": time.time()})
        elif act == "toggle_todo":
            i = data.get("index")
            if isinstance(i,int) and 0 <= i < len(d["todos"]): d["todos"][i]["done"] = not d["todos"][i]["done"]
        save_notes(d)
        return jsonify({"success": True, "notes": d})
    return jsonify(d)

@app.route("/api/music", methods=["GET","POST"])
def api_music():
    load_music()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        act = data.get("action")
        if act == "play":
            q = (data.get("query") or "").strip()
            if q:
                webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
                MUSIC_STATE["playing"] = True; MUSIC_STATE["title"] = q
            else: MUSIC_STATE["playing"] = True
        elif act == "stop":
            MUSIC_STATE["playing"] = False; MUSIC_STATE["title"] = "Nothing playing"
            control_media("media_play_pause")
        elif act == "pause":
            control_media("media_play_pause")
            MUSIC_STATE["playing"] = not MUSIC_STATE.get("playing")
        elif act == "next": control_media("media_next")
        elif act == "prev": control_media("media_prev")
        save_music()
        return jsonify({"success": True, "music": MUSIC_STATE})
    return jsonify(MUSIC_STATE)

@app.route("/api/automation", methods=["GET","POST"])
def api_automation():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        key = data.get("key"); val = data.get("value")
        if key in AUTOMATION and val is not None:
            AUTOMATION[key] = bool(val); save_automation()
        return jsonify({"success": True, "automation": AUTOMATION})
    return jsonify(AUTOMATION)

@app.route("/api/personality", methods=["GET","POST"])
def api_personality():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        m = data.get("mode")
        if m in PERSONALITY_PROMPTS:
            PERSONALITY["mode"] = m
        return jsonify({"success": True, "mode": PERSONALITY["mode"]})
    return jsonify(PERSONALITY)

@app.route("/api/report")
def api_report():
    return jsonify({"report": build_daily_report(), "stats": get_today_stats()})

@app.route("/api/timer", methods=["GET", "POST"])
def api_timer():
    global FOCUS_TIMER
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        act = data.get("action")
        if act == "start_work":
            FOCUS_TIMER = {"active": True, "end_time": time.time() + 1500, "duration": 1500, "mode": "work"}
        elif act == "start_break":
            FOCUS_TIMER = {"active": True, "end_time": time.time() + 300, "duration": 300, "mode": "break"}
        elif act == "stop":
            FOCUS_TIMER["active"] = False
        return jsonify({"success": True})
    remaining = 0
    if FOCUS_TIMER["active"]:
        remaining = max(0, int(FOCUS_TIMER["end_time"] - time.time()))
        if remaining == 0: FOCUS_TIMER["active"] = False
    return jsonify({"active": FOCUS_TIMER["active"], "mode": FOCUS_TIMER["mode"], "duration": FOCUS_TIMER["duration"], "remaining": remaining})

@app.route("/api/skills", methods=["GET","POST"])
def api_skills():
    skills = load_skills()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        act = data.get("action")
        if act == "add":
            t = (data.get("trigger") or "").strip().lower()
            a = (data.get("do") or "").strip()
            if t and a:
                skills = [s for s in skills if s["trigger"] != t]
                skills.append({"trigger": t, "do": a})
                save_skills(skills)
        elif act == "del":
            t = (data.get("trigger") or "").strip().lower()
            skills = [s for s in skills if s["trigger"] != t]
            save_skills(skills)
        return jsonify({"success": True, "skills": skills})
    return jsonify({"skills": skills})

@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "Vasanth AI", "short_name": "Vasanth AI",
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#0f0a1e", "theme_color": "#e879f9",
        "icons": [{"src": "/logo.png", "sizes": "512x512", "type": "image/png"}]
    })

@app.route("/logo.png")
def logo_png():
    try:
        return send_file(os.path.join(BASE_DIR, "logo.png"), mimetype="image/png")
    except:
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
    load_music()
    threading.Thread(target=reminder_checker_thread, daemon=True).start()
    threading.Thread(target=telegram_bot_thread, daemon=True).start()
    threading.Thread(target=proactive_thread, daemon=True).start()
    threading.Thread(target=automation_thread, daemon=True).start()
    threading.Thread(target=timer_thread, daemon=True).start()
    print("\n" + "=" * 60)
    print("    VASANTH AI - ULTIMATE EDITION ")
    print("=" * 60)
    print(f"Groq:     {'READY ✅' if GROQ_API_KEY else 'MISSING ❌'}")
    print(f"AWS:      {'READY ✅' if AWS_READY else 'Not configured'}")
    print(f"Whisper:  {'🎙️ STT READY' if WHISPER_READY else 'Not installed'}")
    print(f"Piper:    {'🔊 TTS READY' if PIPER_READY else 'Not installed'}")
    print(f"Telegram: {'READY ✅' if (TELEGRAM_AVAILABLE and TELEGRAM_BOT_TOKEN) else 'Not configured'}")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, use_reloader=False)
