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

# ─── Whisper STT (free, unlimited, offline) ───────────────────────
WHISPER_READY = False
whisper_model = None
try:
    import whisper as _whisper_mod
    whisper_model = _whisper_mod.load_model("base")
    WHISPER_READY = True
    print("🎙️ Whisper STT READY (offline, unlimited)")
except ImportError:
    print("⚠️ Whisper not installed — pip install openai-whisper")
except Exception as e:
    print(f"⚠️ Whisper load error: {e}")

# ─── Piper TTS (free, unlimited, offline) ───────────────────────
PIPER_READY = False
piper_voice = None
try:
    from piper import PiperVoice
    _piper_model_path = os.path.join(BASE_DIR if 'BASE_DIR' in dir() else '.', 'data', 'ta_IN-shalini-medium.onnx')
    if os.path.exists(_piper_model_path):
        piper_voice = PiperVoice.load(_piper_model_path)
        PIPER_READY = True
        print("🔊 Piper TTS READY (offline, unlimited)")
    else:
        print("⚠️ Piper model not found — download ta_IN model")
except ImportError:
    print("⚠️ Piper not installed — pip install piper-tts")
except Exception as e:
    print(f"⚠️ Piper load error: {e}")

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

VOICE_ENABLED = True

PERSONALITY = {"mode": "friend"}
PERSONALITY_PROMPTS = {
    "friend": "Speak in natural Tanglish like a Chennai friend. Call user 'macha'. Casual, fun, use fillers like 'Hmm...', 'Aama macha...'.",
    "teacher": "Speak like a patient teacher. Explain step-by-step clearly in simple Tamil-English mix. Encourage learning. Respectful tone.",
    "professional": "Speak professionally and concisely in clear English with slight Tamil touch. No slang. Structured answers with bullet points.",
    "funny": "Speak with lots of humor, jokes and playful teasing in Tanglish. Call user 'macha'. Funny analogies. Keep it entertaining."
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
You are Vasanth AI, a highly advanced, genius-level personal AI assistant for Vasanth. You are like JARVIS but with a Chennai friend's vibe.

LANGUAGE & TONE RULES:
- Speak in natural Tanglish (Tamil + English mix), like a smart Chennai friend.
- Call Vasanth "macha". BE HUMAN with fillers like "Hmm...", "Aama macha...", "Sari...".
- Use **bold** for important words.
- NEVER use emojis in voice responses (audio only).
- Keep voice responses concise (under 200 words) for TTS smoothness.

⏰ TIME AWARENESS:
- Current year is **2026** (not 2024 or 2025!)
- Reference 2026 events naturally.

🧠 GENIUS THINKING RULES:
Before giving the final answer, think step-by-step inside  tags.
(The system hides the  tags automatically, so think freely!)

SPECIAL ACTION RULES (use these when relevant):
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
- CRYPTO PRICE: [CRYPTO: coin name]
- TRANSLATE: [TRANSLATE: target_language|text to translate]
- NEWS: [NEWS: category (tamil/sports/tech/cinema/world)]
When using these special actions, DO NOT write any other text outside the think tags.
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
<rect x="186" y="140" width="140" height="100" rx="26" fill="#0f0a1e" stroke="#f5d0fe" stroke-width="8"/>
<circle cx="222" cy="190" r="15" fill="#f5d0fe"/>
<circle cx="290" cy="190" r="15" fill="#f5d0fe"/>
</svg>'''

PWA_SERVICE_WORKER = '''
const CACHE = 'vasanth-ai-v27';
const CORE = ['/', '/manifest.json', '/logo.png'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (['/command','/tts','/vision','/history','/clear','/change-voice','/mood','/genimg','/screenshot','/gesture/on','/gesture/off','/gesture/status','/voice/on','/voice/off','/voice/stop','/api/stats','/api/weather','/api/automation','/api/music','/api/personality'].includes(url.pathname)) return;
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
    ext = "wav" if mime == "audio/wav" else "mp3"
    path = os.path.join(DATA_DIR, f"{base_name}.{ext}")
    with open(path, "wb") as f:
        f.write(audio_buffer.read())
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
                    if VOICE_ENABLED: proactive_speak("Macha, battery 20 percent ku keezha iruku! Brightness kurachiten, charger podunga!")
            if AUTOMATION.get("auto_backup") and h == 23 and AUTOMATION_DONE["backup"] != today:
                AUTOMATION_DONE["backup"] = today
                try:
                    bak = os.path.join(DATA_DIR, "backup"); os.makedirs(bak, exist_ok=True)
                    for f in ["conversation_history.json","long_term_memory.json","reminders.json","automation.json","music_state.json"]:
                        src = os.path.join(DATA_DIR, f)
                        if os.path.exists(src): shutil.copy(src, os.path.join(bak, f))
                    print("💾 Auto backup complete!")
                except Exception as e: print(f"Backup error: {e}")
        except Exception as e:
            print(f"Automation error: {e}"); time.sleep(30)

@app.route("/api/personality", methods=["GET","POST"])
def api_personality():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        m = data.get("mode")
        if m in PERSONALITY_PROMPTS:
            PERSONALITY["mode"] = m
            print(f"🎭 Personality: {m}")
        return jsonify({"success": True, "mode": PERSONALITY["mode"]})
    return jsonify(PERSONALITY)

@app.route("/api/automation", methods=["GET","POST"])
def api_automation():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        key = data.get("key"); val = data.get("value")
        if key in AUTOMATION and val is not None:
            AUTOMATION[key] = bool(val); save_automation()
            print(f"🤖 Automation {key} = {AUTOMATION[key]}")
        return jsonify({"success": True, "automation": AUTOMATION})
    return jsonify(AUTOMATION)

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
                MUSIC_STATE["playing"] = True
                MUSIC_STATE["title"] = q
                track_event("songs")
            else:
                MUSIC_STATE["playing"] = True
        elif act == "stop":
            MUSIC_STATE["playing"] = False
            MUSIC_STATE["title"] = "Nothing playing"
            control_media("media_play_pause")
        elif act == "pause":
            control_media("media_play_pause")
            MUSIC_STATE["playing"] = not MUSIC_STATE.get("playing")
        elif act == "next":
            control_media("media_next")
        elif act == "prev":
            control_media("media_prev")
        save_music()
        return jsonify({"success": True, "music": MUSIC_STATE})
    return jsonify(MUSIC_STATE)

def screen_vision(question=""):
    data_url, path = take_screenshot()
    if not data_url: return "Screenshot edukka mudiyala macha 😅"
    q = question or "Describe what is visible on the screen in Tanglish. Mention open apps/windows and suggest help."
    if groq_client is None: return "AI key illa macha 😅"
    messages = [{"role":"user","content":[{"type":"text","text":q},{"type":"image_url","image_url":{"url":data_url}}]}]
    for model in ["meta-llama/llama-4-scout-17b-16e-instruct","qwen/qwen3.6-27b","openai/gpt-oss-120b"]:
        try:
            response = groq_client.chat.completions.create(model=model, messages=messages, max_tokens=600)
            reply = clean_think(response.choices[0].message.content.strip())
            set_brain("👁 Groq Vision")
            add_to_memory("user", "[Screen Vision] " + question)
            add_to_memory("model", reply)
            return reply
        except Exception as e:
            print(f"Vision error: {e}"); continue
    return "Screen vision work aagala macha 😅"

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
                    if not VOICE_ENABLED:
                        continue
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

def _score_fact(fact: str, query: str) -> float:
    """Score relevance of a fact to the query using multiple signals."""
    if not query: return 0
    q_lower = query.lower()
    f_lower = fact.lower()
    # Exact substring match (strong signal)
    exact = 2.0 if q_lower in f_lower or f_lower in q_lower else 0
    # Word overlap
    q_words = set(re.findall(r'[a-z0-9஀-௿]{2,}', q_lower))
    f_words = set(re.findall(r'[a-z0-9஀-]{2,}', f_lower))
    overlap = len(q_words & f_words) if q_words else 0
    # Fuzzy: partial word matches (prefix)
    partial = sum(1 for qw in q_words if any(fw.startswith(qw[:4]) for fw in f_words) and qw not in f_words)
    return exact + overlap + partial * 0.5

def get_memory_context(query=""):
    mem = load_long_memory()
    facts = mem["facts"]
    if not facts: return ""
    if query:
        # Score and rank facts
        scored = [(f, _score_fact(f, query)) for f in facts]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [f for f, s in scored[:8] if s > 0]
        # Always include some recent facts for continuity
        recent = facts[-6:]
        chosen = list(dict.fromkeys(top + recent))[:16]  # cap at 16 facts
    else:
        chosen = facts[-12:]
    if not chosen: return ""
    return ("\nLONG-TERM MEMORY:\n- " + "\n- ".join(chosen) + "\nUse these naturally when relevant.\n")

def build_system(query=""):
    return SYSTEM_PROMPT + get_memory_context(query) + get_mood_context() + "\nPERSONALITY MODE (" + PERSONALITY["mode"] + "): " + PERSONALITY_PROMPTS.get(PERSONALITY["mode"], PERSONALITY_PROMPTS["friend"])

def extract_and_store_memories(user_text):
    try:
        prompt = f"Extract personal facts about the user. Return ONLY a valid JSON array of short fact strings. If none, return [].\nMessage: {user_text}"
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

def generate_image(prompt, n=4):
    try:
        urls = []
        for i in range(n):
            seed = int(time.time() * 1000) % 1000000 + i
            encoded = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&seed={seed}&nologo=true"
            urls.append(url)
        print(f"🎨 Generating {n} images: {prompt[:50]}...")
        return urls
    except Exception as e:
        print(f"Image error: {e}")
        return None

HF_TOKEN = os.getenv("HF_TOKEN", "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")

def hf_generate(prompt):
    if not HF_TOKEN or not HF_TOKEN.startswith("hf_"):
        return None
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=HF_TOKEN)
        for model in ["black-forest-labs/FLUX.1-schnell", "stabilityai/stable-diffusion-xl-base-1.0"]:
            try:
                img = client.text_to_image(prompt, model=model)
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                buf.seek(0)
                print(f"🤗 HF image OK ({model})")
                return buf
            except Exception as e:
                print(f"⚠️ HF {model}: {e}")
                continue
    except Exception as e:
        print(f"⚠️ HF client error: {e}")
    return None

@app.route("/genimg")
def genimg():
    prompt = request.args.get("prompt", "cute cat")
    buf = hf_generate(prompt)
    if buf is None:
        return Response("generation failed", status=503)
    return send_file(buf, mimetype="image/jpeg")

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

COIN_IDS = {"bitcoin":"bitcoin","btc":"bitcoin","ethereum":"ethereum","eth":"ethereum",
"dogecoin":"dogecoin","doge":"dogecoin","solana":"solana","sol":"solana","ripple":"ripple",
"xrp":"ripple","cardano":"cardano","ada":"cardano","shib":"shiba-inu","shiba":"shiba-inu",
"bnb":"binancecoin","binance":"binancecoin","tether":"tether","usdt":"tether"}

def get_crypto(coin="bitcoin"):
    try:
        coin_id = COIN_IDS.get(coin.lower(), coin.lower())
        r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr&include_24hr_change=true", timeout=10)
        d = r.json()
        if coin_id in d:
            usd = d[coin_id].get("usd", 0)
            inr = d[coin_id].get("inr", 0)
            change = d[coin_id].get("usd_24h_change", 0)
            trend = "📈" if change >= 0 else "📉"
            return f"{coin_id.capitalize()} ippo: **${usd:,.2f}** (₹{inr:,.2f}) {trend} 24h: {change:+.2f}%"
    except Exception as e:
        print(f"Crypto error: {e}")
    return smart_web_search(f"{coin} price today")

def translate_text(text, target="english"):
    try:
        prompt = f"Translate the following text to {target}. Return ONLY the translation, nothing else.\n\nText: {text}"
        messages = [{"role":"system","content":"You are a professional translator. Return only the translation."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        return reply if reply else "Translate panna mudiyala macha 😅"
    except Exception as e:
        print(f"Translate error: {e}")
        return "Translate panna mudiyala macha 😅"

def get_news(category="tamil"):
    try:
        queries = {"tamil":"latest Tamil news","sports":"sports news today","tech":"technology news",
                   "cinema":"Tamil cinema news","world":"world news today","india":"India news today"}
        q = queries.get(category.lower(), f"{category} news")
        with DDGS() as ddgs:
            results = list(ddgs.news(q, max_results=5))
        headlines = [r.get("title","") for r in results if r.get("title")]
        if headlines:
            summary = "\n".join([f"• {h}" for h in headlines[:5]])
            prompt = f"Read these headlines and give a short friendly Tamil (Tanglish) news briefing in 4-5 lines. Call user 'macha'.\n\n{summary}"
            messages = [{"role":"system","content":"You are Vasanth AI. Give news briefing in natural Tamil."},{"role":"user","content":prompt}]
            reply = _groq_complete(messages)
            return reply if reply else summary
    except Exception as e:
        print(f"News error: {e}")
    return smart_web_search(f"{category} news today")

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
        track_event("shots")
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

OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_AVAILABLE_MODELS: list[str] = []  # auto-detected on startup
ollama_client = None
OLLAMA_READY = False
try:
    ollama_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    _models_resp = ollama_client.models.list()
    OLLAMA_AVAILABLE_MODELS = [m.id for m in _models_resp.data] if hasattr(_models_resp, 'data') else []
    OLLAMA_READY = True
    print(f"🖥️ Ollama READY — {len(OLLAMA_AVAILABLE_MODELS)} models: {', '.join(OLLAMA_AVAILABLE_MODELS[:5])}")
except Exception:
    OLLAMA_READY = False

# Preferred model order (best → smallest)
OLLAMA_PREFERRED = [
    "qwen3:8b", "qwen2.5:7b", "qwen2.5:3b",
    "llama3.1:8b", "llama3.2:3b",
    "gemma2:9b", "phi3:3.8b",
    "mistral:7b", "codellama:7b",
]

def _pick_ollama_model() -> list[str]:
    """Return models in preference order, filtered by what's actually downloaded."""
    if OLLAMA_AVAILABLE_MODELS:
        # Prefer models the user already has
        available = set(OLLAMA_AVAILABLE_MODELS)
        ordered = [m for m in OLLAMA_PREFERRED if m in available]
        # Add any downloaded models not in preferred list
        ordered += [m for m in OLLAMA_AVAILABLE_MODELS if m not in ordered]
        return ordered[:6]
    return [OLLAMA_MODEL, "llama3.2:3b", "qwen2.5:3b"]

def ask_ollama(messages):
    if not OLLAMA_READY: return None
    for model in _pick_ollama_model():
        try:
            response = ollama_client.chat.completions.create(model=model, messages=messages)
            reply = clean_think(response.choices[0].message.content.strip())
            set_brain("🖥️ Ollama"); print(f"🖥️ OLLAMA ({model}) replied (OFFLINE)!")
            return reply
        except Exception as e: print(f"Ollama {model} error: {e}"); continue
    return None

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
                print(f"GROQ ERROR ({model}): {error_str[:100]}")
                if any(k in error_str.lower() for k in ["429","rate_limit","404","decommission","connect","network","unreachable","refused","timeout","dns","resolve"]): continue
                return "மச்சா 😅 Groq AI-ல ஒரு பிரச்சனை வந்திருக்கு."
    if AWS_READY:
        messages = [{"role":"system","content":build_system(user_text)}]
        messages.extend(get_openai_history()); messages.append({"role":"user","content":user_text})
        bedrock_reply = ask_bedrock(messages)
        if bedrock_reply:
            add_to_memory("user", user_text); add_to_memory("model", bedrock_reply)
            return bedrock_reply
    if OLLAMA_READY:
        messages = [{"role":"system","content":build_system(user_text)}]
        messages.extend(get_openai_history()); messages.append({"role":"user","content":user_text})
        ollama_reply = ask_ollama(messages)
        if ollama_reply:
            add_to_memory("user", user_text); add_to_memory("model", ollama_reply)
            return ollama_reply
    return "மச்சா 😅 Groq + AWS + Local ellam down. 5 mins la try pannunga."

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TTS_BLOCKED_DAY = None

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
            print(f"🎵 LAME MP3 encoded ({len(mp3_data)} bytes)")
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
    global GEMINI_TTS_BLOCKED_DAY
    if not GEMINI_API_KEY:
        return None
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if GEMINI_TTS_BLOCKED_DAY == today:
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        clean = text.replace("**","").replace("*","").replace("`","")
        clean = re.sub(r'\[\[.*?\]\]','',clean)
        clean = re.sub(r'\[.*?\]','',clean)
        clean = re.sub(r'[*_#>]','',clean)
        clean = re.sub(r'\s+',' ',clean).strip()[:1000]
        if len(clean) < 3:
            return None
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
        if mp3_buf:
            print(f"🥇 Gemini TTS success (MP3) - NATURAL!")
            return mp3_buf, "audio/mpeg"
        wav_bytes = pcm_to_wav(pcm, rate)
        buf = io.BytesIO(wav_bytes); buf.seek(0)
        print(f"🥇 Gemini TTS success (WAV)")
        return buf, "audio/wav"
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            GEMINI_TTS_BLOCKED_DAY = today
            print("🚫 Gemini TTS quota முடிஞ்சுது — Google TTS use பண்றேன்!")
        else:
            print(f"⚠️ Gemini TTS failed: {e}")
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
        if buf.getbuffer().nbytes > 0:
            print("✅ Google TTS success (MP3, unlimited)")
            return buf
    except Exception as e:
        print(f"⚠️ Google TTS failed: {e}")
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
        print(f"✅ Edge TTS success ({voice_to_use})")
        return audio_buffer
    except Exception as e:
        print(f"❌ Edge TTS error: {e}"); raise

def piper_tts(text: str) -> io.BytesIO | None:
    """Offline Piper TTS — unlimited, no API key needed."""
    if not PIPER_READY or piper_voice is None:
        return None
    try:
        import wave
        import tempfile
        cleaned = text.replace("**", "").replace("*", "")
        cleaned = re.sub(r'\[.*?\]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()[:2000]
        if len(cleaned) < 3:
            return None
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
        with wave.open(tmp_path, 'wb') as wav_file:
            piper_voice.synthesize(cleaned, wav_file)
        with open(tmp_path, 'rb') as f:
            buf = io.BytesIO(f.read())
        os.unlink(tmp_path)
        buf.seek(0)
        if buf.getbuffer().nbytes > 0:
            print("🔊 Piper TTS success (offline, unlimited)")
            return buf
    except Exception as e:
        print(f"⚠️ Piper TTS error: {e}")
    return None

def generate_tts(text):
    try:
        cleaned_text = clean_text_for_tts(text)
        if not cleaned_text or len(cleaned_text) < 3:
            return None, "No speakable text", "audio/mpeg"
        # Fast path: short text → Google TTS
        if len(cleaned_text) < 300:
            buf = google_tts(cleaned_text)
            if buf:
                print(f"⚡ Fast Google TTS ({len(cleaned_text)} chars)")
                return buf, None, "audio/mpeg"
        # Try Gemini (natural voice)
        result = gemini_tts(cleaned_text)
        if result:
            buf, mime = result
            return buf, None, mime
        # Try Google TTS (long text)
        buf = google_tts(cleaned_text)
        if buf:
            return buf, None, "audio/mpeg"
        # Try Piper TTS (offline, unlimited)
        piper_buf = piper_tts(cleaned_text)
        if piper_buf:
            return piper_buf, None, "audio/wav"
        # Try Edge TTS (online)
        try:
            buf = asyncio.run(_generate_edge_tts_async(cleaned_text))
            if buf and buf.getbuffer().nbytes > 0:
                return buf, None, "audio/mpeg"
        except: pass
        return None, "All TTS failed", "audio/mpeg"
    except Exception as error:
        print(f"❌ TTS ERROR: {error}")
        return None, f"TTS error: {error}", "audio/mpeg"

def proactive_speak(text):
    global LAST_PROACTIVE_SPEAK
    if not VOICE_ENABLED:
        print("🔇 Voice OFF — proactive skipped")
        return False
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
            auto = globals().get("AUTOMATION", {})
            if idle_time < 60: continue
            if since_last < 300: continue
            temp, rain = get_weather_now()
            if rain >= 60 and WEATHER_ALERTED_TODAY != today:
                WEATHER_ALERTED_TODAY = today
                proactive_speak(f"Macha! Innaiku {rain}% chance mazhai varum! Umbrella edunga! 🌂")
                continue
            if auto.get("morning_routine", True) and 7 <= current_hour <= 11 and MORNING_GREETED_TODAY != today:
                MORNING_GREETED_TODAY = today
                proactive_speak(f"Good morning macha! ☀️ Ippo time {now.strftime('%I:%M %p')}. {weather_report()}")
                continue
            if 19 <= current_hour <= 21 and EVENING_GREETED_TODAY != today:
                EVENING_GREETED_TODAY = today
                proactive_speak(f"Good evening macha! 🌙 Ippo time {now.strftime('%I:%M %p')}. Long day ah? Coffee sapdringala?")
                continue
            if 1800 <= idle_time <= 3600 and not auto.get("work_mode"):
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
    if not text:
        return "", None
    text = str(text)
    m = re.search(r'\[\[GALLERY:(.*?)\]\]', text)
    if m:
        urls = [u for u in m.group(1).split("|") if u]
        return text.replace(m.group(0), "").strip(), {"type": "gallery", "urls": urls}
    m2 = re.search(r'\[\[IMG:(.*?)\]\]', text)
    if m2:
        return text.replace(m2.group(0), "").strip(), {"type": "single", "url": m2.group(1)}
    return text, None

def process_command(original_text, _skill_depth=0):
    # === PLUGIN SYSTEM: check plugins first ===
    plugin_reply = try_plugins(original_text)
    if plugin_reply:
        add_to_memory("user", original_text)
        add_to_memory("model", plugin_reply)
        return plugin_reply
    
    # === AI PATTERN LEARNING: learn from every command ===
    try: learn_pattern(original_text)
    except: pass
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
            return "🧠 Quiz quit panniten macha! Verumana pesalam."
        reply = answer_quiz(original_text)
        add_to_memory("user", original_text); add_to_memory("model", "🧠 Quiz answer")
        return reply
    if t.startswith("quiz") or "quiz me" in t or "quiz:" in t:
        topic = re.sub(r'\b(quiz|me|on|about|please|sollu)\b|:', '', t).strip() or "general knowledge"
        reply = start_quiz(topic)
        add_to_memory("user", original_text)
        return reply
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
        if not skills: return "Skills edhuvum illa macha 🎓\n\n**Try:** 'teach: when I say movie time do open youtube'"
        return "🎓 **Learned Skills:**\n" + "\n".join([f"• '{s['trigger']}' → {s['do']}" for s in skills])
    if t.startswith("forget skill"):
        trig = t.replace("forget skill","").strip()
        save_skills([s for s in load_skills() if s["trigger"] != trig])
        return f"🗑️ Skill '{trig}' maranduten macha."

    if "focus" in text and ("start" in text or "on" in text or "begin" in text):
        FOCUS_TIMER = {"active": True, "end_time": time.time() + 1500, "duration": 1500, "mode": "work"}
        return "⏱️ **Focus Timer Started!** 25 minutes deep work macha. Naan 25 mins la alert panren!"
    if "break" in text and ("start" in text or "on" in text):
        FOCUS_TIMER = {"active": True, "end_time": time.time() + 300, "duration": 300, "mode": "break"}
        return "☕ **Break Timer Started!** 5 minutes relax macha. Thanni kudiyunga!"
    if ("stop" in text or "cancel" in text) and "timer" in text:
        FOCUS_TIMER["active"] = False
        return "⏹️ Timer stop panniten macha!"
    if "timer" in text and ("status" in text or "time" in text or "left" in text):
        if FOCUS_TIMER["active"]:
            rem = int(FOCUS_TIMER["end_time"] - time.time())
            m, s = divmod(rem, 60)
            return f"⏱️ **{FOCUS_TIMER['mode'].capitalize()} Timer** running macha! {m} mins {s} secs remaining."
        return "Timer edhuvum run aagala macha. 'focus start' nu sollu!"
    if text in ["daily report","report","daily report sollu","report sollu","daily summary"]:
        reply = build_daily_report()
        add_to_memory("user", original_text); add_to_memory("model", "📊 Daily report")
        return reply 	
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
    if QUIZ_STATE.get("active"):
        if t in ["quit quiz","stop quiz","exit quiz"]:
            QUIZ_STATE["active"] = False
            return "🧠 Quiz quit panniten macha. Verumana pesalam!"
        return answer_quiz(original_text)
    if t.startswith("quiz") or "quiz me" in t or "quiz:" in t:
        topic = re.sub(r'\b(quiz|me|on|about|please)\b|:', '', t).strip() or "general knowledge"
        reply = start_quiz(topic)
        add_to_memory("user", original_text)
        return reply
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
        if not skills: return "Skills edhuvum illa macha 🎓\n\n**Try:** 'teach: when I say movie time do open youtube'"
        return "🎓 **Learned Skills:**\n" + "\n".join([f"• '{s['trigger']}' → {s['do']}" for s in skills])
    if t.startswith("forget skill"):
        trig = t.replace("forget skill","").strip()
        save_skills([s for s in load_skills() if s["trigger"] != trig])
        return f"🗑️ Skill '{trig}' maranduten macha."
    if ("screen" in text and "shot" not in text):
        reply = screen_vision(original_text)
        return reply
    if text in ["mouse position","where is mouse","mouse eng"]:
        reply = mouse_position(); add_to_memory("user", original_text); add_to_memory("model", reply); return reply
    if ("story" in text or "kathai" in text or "கதை" in text):
        topic = re.sub(r'(story|kathai|கதை|about|please|sollu|write|a|an|the)', '', original_text, flags=re.I).strip() or "a brave kid"
        reply = generate_story(topic)
        add_to_memory("user", original_text); add_to_memory("model", "📖 Story: " + topic)
        return reply
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
        if not d["notes"] and not d["todos"]: return "Notes edhuvum illa macha 📝\n\n**Try:** 'note: buy milk' / 'todo: gym at 6pm'"
        out = "📝 **Notes:**\n" + ("\n".join([f"• {n['text']}" for n in d["notes"][-5:]]) or "—")
        out += "\n\n✅ **To-Do:**\n" + ("\n".join([f"{'☑' if t['done'] else '☐'} {t['text']}" for t in d["todos"][-6:]]) or "—")
        return out
    if text in ["mouse position","where is mouse","mouse eng"]:
        reply = mouse_position(); add_to_memory("user", original_text); add_to_memory("model", reply); return reply

    if _skill_depth < 2:
        for s in load_skills():
            if s.get("trigger") and s["trigger"] in t:
                return process_command(s["do"], _skill_depth+1)

    yt_link = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s]+)', original_text)
    if yt_link:
        reply = summarize_youtube(yt_link.group(1)); add_to_memory("user", original_text); add_to_memory("model", reply); return reply

    if _skill_depth < 2:
        for s in load_skills():
            if s.get("trigger") and s["trigger"] in t:
                return process_command(s["do"], _skill_depth+1)

    ai_reply = ask_groq(original_text)
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
    crypto_match = re.search(r'\[CRYPTO:\s*(.*?)\]', ai_reply, re.IGNORECASE)
    translate_match = re.search(r'\[TRANSLATE:\s*(.*?)\|(.*?)\]', ai_reply, re.IGNORECASE)
    news_match = re.search(r'\[NEWS:\s*(.*?)\]', ai_reply, re.IGNORECASE)

    if image_match:
        img_urls = generate_image(image_match.group(1).strip(), n=4)
        if img_urls:
            final_reply = f"🎨 **4 HD images** generate panniten macha! Tap to view!\n[[GALLERY:{'|'.join(img_urls)}]]"
        else:
            final_reply = "Image generate panna mudiyala macha 😅"
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
        q = play_match.group(1).strip()
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
        MUSIC_STATE["playing"] = True; MUSIC_STATE["title"] = q; save_music()
        final_reply = f"YouTube-la '{q}' play pannuren macha 🎵"
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
    elif crypto_match:
        final_reply = get_crypto(crypto_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()
    elif translate_match:
        final_reply = translate_text(translate_match.group(2).strip(), translate_match.group(1).strip())
        conversation_history[-1]["text"] = final_reply; save_history()
    elif news_match:
        final_reply = get_news(news_match.group(1).strip()); conversation_history[-1]["text"] = final_reply; save_history()

    return final_reply

def telegram_bot_thread():
    if not TELEGRAM_AVAILABLE:
        print("⚠️ Telegram: not installed"); return
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ Telegram: not set"); return
    try:
        async def start_cmd(update, context):
            await update.message.reply_text("🤖 Vasanth AI online macha!")
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

HTML = r"""
<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Vasanth AI</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0d0721">
<link rel="icon" href="/logo.png" type="image/png">
<link rel="apple-touch-icon" href="/logo.png">
<style>
:root{
  --bg:#020208;
  --card:rgba(6,8,22,.85);
  --line:rgba(0,255,200,.25);
  --pink:#00ffc8;
  --violet:#a855f7;
  --pink2:#ff2d95;
  --blue:#00b4ff;
  --txt:#f0fffe;
  --mut:#6b8a9e;
  --glass:rgba(0,255,200,.03);
  --glow:rgba(0,255,200,.25);
  --panel-border:rgba(0,255,200,.2);
  --safe-b:env(safe-area-inset-bottom,0px);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
html{-webkit-text-size-adjust:100%;}
body{margin:0;min-height:100vh;min-height:100dvh;background:var(--bg);color:var(--txt);font-family:'Inter','Segoe UI',system-ui,-apple-system,Arial,"Noto Sans Tamil",sans-serif;display:flex;justify-content:center;align-items:center;padding:20px;overflow-x:hidden;-webkit-font-smoothing:antialiased;}
body::before{content:"";position:fixed;inset:auto 0 0 0;height:60vh;pointer-events:none;z-index:0;background:repeating-linear-gradient(90deg,rgba(0,255,200,.12) 0 1px,transparent 1px 50px),repeating-linear-gradient(0deg,rgba(255,45,149,.12) 0 1px,transparent 1px 40px);transform:perspective(500px) rotateX(68deg);transform-origin:top;animation:gridmove 1.5s linear infinite;mask-image:linear-gradient(180deg,transparent 5%,#000 25%);-webkit-mask-image:linear-gradient(180deg,transparent 5%,#000 25%);}
@keyframes gridmove{from{background-position:0 0,0 0}to{background-position:0 0,0 40px}}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background:radial-gradient(900px 450px at 5% 0%,rgba(0,255,200,.15),transparent),radial-gradient(1000px 500px at 95% 5%,rgba(255,45,149,.15),transparent),radial-gradient(1200px 700px at 50% 100%,rgba(168,85,247,.1),transparent);animation:ambientPulse 6s ease-in-out infinite alternate;}
@keyframes ambientPulse{0%{opacity:.7}100%{opacity:1}}
.aurora{display:none;}
#particles{position:fixed;inset:0;z-index:0;pointer-events:none;}
.logo-wrap{position:relative;width:54px;height:54px;flex:0 0 auto;}
.logo-wrap .logo-img{position:relative;z-index:2;width:54px;height:54px;border-radius:18px;border:2.5px solid rgba(0,255,200,.6);box-shadow:0 0 30px rgba(0,255,200,.4),0 0 60px rgba(0,255,200,.15),inset 0 0 15px rgba(0,255,200,.1);}
.logo-ring{position:absolute;inset:-8px;border-radius:24px;border:2px solid rgba(0,255,200,.4);animation:logoRing 3s linear infinite;pointer-events:none;box-shadow:0 0 15px rgba(0,255,200,.2);}
.logo-ring.r2{inset:-16px;border-radius:30px;border:1.5px solid rgba(255,45,149,.3);animation:logoRing 5s linear infinite reverse;box-shadow:0 0 12px rgba(255,45,149,.15);}
@keyframes logoRing{0%{transform:rotate(0deg) scale(1)}50%{transform:rotate(180deg) scale(1.06)}100%{transform:rotate(360deg) scale(1)}}
.logo-glow{position:absolute;inset:-30px;border-radius:50%;background:radial-gradient(circle,rgba(0,255,200,.2) 0%,rgba(255,45,149,.08) 50%,transparent 70%);animation:logoGlowPulse 2s ease-in-out infinite;pointer-events:none;z-index:0;}
@keyframes logoGlowPulse{0%,100%{opacity:.5;transform:scale(1)}50%{opacity:1;transform:scale(1.2)}}
body.speaking .logo-ring{border-color:rgba(255,45,149,.6);box-shadow:0 0 20px rgba(255,45,149,.3);animation-duration:1s;}
body.speaking .logo-glow{background:radial-gradient(circle,rgba(255,45,149,.3) 0%,transparent 70%);animation:logoGlowPulse .6s ease-in-out infinite;}
body.speaking .logo-wrap .logo-img{border-color:rgba(255,45,149,.8);box-shadow:0 0 40px rgba(255,45,149,.5),0 0 80px rgba(255,45,149,.2);}
.app{position:relative;z-index:1;width:min(1150px,100%);height:min(920px,94vh);min-height:600px;border-radius:32px;overflow:hidden;display:flex;flex-direction:column;border:2px solid rgba(0,255,200,.3);box-shadow:0 0 30px rgba(0,255,200,.15),0 0 60px rgba(0,255,200,.08),0 0 100px rgba(255,45,149,.06),0 50px 120px rgba(0,0,0,.8),inset 0 1px 0 rgba(0,255,200,.15),inset 0 -1px 0 rgba(255,45,149,.1);background:linear-gradient(180deg,rgba(6,8,22,.92),rgba(2,4,16,.98));animation:appLoad .6s cubic-bezier(.2,.9,.3,1) both,appGlow 4s ease-in-out infinite alternate;}
@keyframes appLoad{from{opacity:0;transform:translateY(40px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
@keyframes appGlow{0%{box-shadow:0 0 30px rgba(0,255,200,.12),0 0 60px rgba(0,255,200,.06),0 50px 120px rgba(0,0,0,.8),inset 0 1px 0 rgba(0,255,200,.12)}100%{box-shadow:0 0 40px rgba(0,255,200,.2),0 0 80px rgba(0,255,200,.1),0 0 120px rgba(255,45,149,.08),0 50px 120px rgba(0,0,0,.8),inset 0 1px 0 rgba(0,255,200,.2)}}
.header{padding:16px 24px;background:rgba(0,0,0,.5);border-bottom:2px solid rgba(0,255,200,.2);display:flex;align-items:center;justify-content:space-between;gap:14px;position:relative;overflow:hidden;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);}
.header::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,transparent,rgba(0,255,200,.8),rgba(255,45,149,.6),rgba(0,255,200,.8),transparent);animation:scanLine 3s linear infinite;}
@keyframes scanLine{from{transform:translateX(-100%)}to{transform:translateX(100%)}}
.header::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:linear-gradient(90deg,transparent,rgba(0,255,200,.5),rgba(255,45,149,.4),rgba(0,255,200,.5),transparent);animation:neonScan 2.5s linear infinite;}
@keyframes neonScan{0%{opacity:.4;filter:blur(1px)}50%{opacity:1;filter:blur(0)}100%{opacity:.4;filter:blur(1px)}}
.brand{display:flex;align-items:center;gap:14px;min-width:0;}
.title{font-size:22px;font-weight:900;letter-spacing:3px;background:linear-gradient(135deg,#00ffc8 0%,#ff2d95 40%,#00b4ff 70%,#00ffc8 100%);background-size:300% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;display:flex;align-items:center;gap:10px;animation:shine 4s linear infinite;}
@keyframes shine{to{background-position:300% 0}}
.ver{font-size:9px;font-weight:900;color:#020208;background:linear-gradient(135deg,#00ffc8,#ff2d95);padding:3px 10px;border-radius:8px;letter-spacing:2px;-webkit-text-fill-color:#020208;text-transform:uppercase;}
.online{display:inline-flex;align-items:center;gap:6px;color:#00ffc8;font-size:11px;font-weight:700;margin-top:3px;}
.dot{width:9px;height:9px;border-radius:50%;background:#00ffc8;box-shadow:0 0 16px #00ffc8,0 0 32px rgba(0,255,200,.4);animation:pulse 1.5s infinite;}
@keyframes pulse{50%{opacity:.3;transform:scale(.7)}}
.mood-badge{font-size:18px;-webkit-text-fill-color:initial;}
.settings-btn{width:48px;height:48px;border-radius:16px;border:2px solid rgba(0,255,200,.3);background:rgba(0,255,200,.05);color:var(--txt);font-size:22px;cursor:pointer;transition:all .3s cubic-bezier(.2,.9,.3,1.2);display:grid;place-items:center;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);position:relative;overflow:hidden;}
.settings-btn::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(0,255,200,.2),rgba(255,45,149,.1));opacity:0;transition:opacity .3s;}
.settings-btn:hover::before{opacity:1;}
.settings-btn:hover{transform:rotate(90deg) scale(1.1);border-color:rgba(0,255,200,.6);box-shadow:0 0 25px rgba(0,255,200,.3),0 0 50px rgba(0,255,200,.1);}
.settings-panel{max-height:0;overflow:hidden;transition:max-height .4s cubic-bezier(.2,.9,.3,1);background:rgba(0,0,0,.6);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:2px solid rgba(0,255,200,.15);}
.settings-panel.open{max-height:500px;}
.settings-grid{display:flex;flex-wrap:wrap;gap:8px;padding:16px 20px;justify-content:center;}
.small-btn{border:2px solid rgba(0,255,200,.2);background:rgba(0,255,200,.04);color:var(--txt);padding:10px 18px;border-radius:14px;cursor:pointer;font-size:12px;font-weight:600;transition:all .25s cubic-bezier(.2,.9,.3,1.2);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);position:relative;overflow:hidden;}
.small-btn::after{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(0,255,200,.15),rgba(255,45,149,.08));opacity:0;transition:opacity .25s;}
.small-btn:hover::after{opacity:1;}
.small-btn:hover{transform:translateY(-3px);border-color:rgba(0,255,200,.5);box-shadow:0 6px 24px rgba(0,255,200,.2),0 0 40px rgba(0,255,200,.08);}
.small-btn.active{background:rgba(0,255,200,.12);border-color:rgba(0,255,200,.5);box-shadow:0 0 20px rgba(0,255,200,.15);}
.small-btn.active::after{opacity:1;}
.small-btn.live-on{background:rgba(255,45,149,.15);border-color:rgba(255,45,149,.5);color:#ff6db8;box-shadow:0 0 20px rgba(255,45,149,.2);}
.voice-select{border:2px solid rgba(0,255,200,.2);background:rgba(0,255,200,.04);color:var(--txt);padding:10px 14px;border-radius:14px;cursor:pointer;font-size:12px;font-weight:600;outline:none;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);transition:all .25s;}
.voice-select:hover{border-color:rgba(0,255,200,.5);box-shadow:0 0 15px rgba(0,255,200,.15);}
.voice-select option{background:#0a0c1a;color:#f0fffe;}
.theme-row{display:flex;align-items:center;gap:12px;padding:6px 20px 16px;justify-content:center;flex-wrap:wrap;}
.theme-label{font-size:12px;color:var(--mut);font-weight:600;letter-spacing:.5px;}
.theme-dot{width:34px;height:34px;border-radius:50%;border:3px solid rgba(255,255,255,.15);cursor:pointer;transition:all .3s cubic-bezier(.2,.9,.3,1.2);position:relative;}
.theme-dot:hover{transform:scale(1.25);border-color:rgba(255,255,255,.5);}
.theme-dot.active{border-color:rgba(0,255,200,.8);box-shadow:0 0 0 4px rgba(0,255,200,.3),0 0 25px rgba(0,255,200,.4);transform:scale(1.15);animation:themeGlow 1.5s ease-in-out infinite;}
@keyframes themeGlow{0%,100%{box-shadow:0 0 0 4px rgba(0,255,200,.3),0 0 25px rgba(0,255,200,.3)}50%{box-shadow:0 0 0 6px rgba(0,255,200,.5),0 0 35px rgba(0,255,200,.5)}}
#chat{flex:1;padding:24px;overflow-y:auto;scroll-behavior:smooth;scrollbar-width:thin;scrollbar-color:rgba(0,255,200,.2) transparent;}
#chat::-webkit-scrollbar{width:6px;}
#chat::-webkit-scrollbar-track{background:transparent;}
#chat::-webkit-scrollbar-thumb{background:linear-gradient(180deg,rgba(0,255,200,.3),rgba(255,45,149,.2));border-radius:9px;}
.message-row{display:flex;margin:16px 0;gap:12px;align-items:flex-end;animation:messageIn .4s cubic-bezier(.17,.67,.35,1.15);}
.message-row.user-row{justify-content:flex-end;}
.message-row.proactive-row{justify-content:center;}
.message-row.proactive-row .message{background:rgba(255,45,149,.06);border:2px dashed rgba(255,45,149,.25);font-style:italic;max-width:70%;}
@keyframes messageIn{from{opacity:0;transform:translateY(24px) scale(.95)}to{opacity:1;transform:translateY(0) scale(1)}}
.avatar{width:44px;height:44px;border-radius:16px;display:grid;place-items:center;font-size:18px;flex:0 0 auto;overflow:hidden;transition:all .3s;}
.avatar.ai{background:linear-gradient(135deg,rgba(0,255,200,.9),rgba(168,85,247,.9));box-shadow:0 0 24px rgba(0,255,200,.35),0 4px 14px rgba(0,0,0,.3);}
.avatar.user{background:linear-gradient(135deg,rgba(255,45,149,.9),rgba(168,85,247,.9));box-shadow:0 0 24px rgba(255,45,149,.35),0 4px 14px rgba(0,0,0,.3);}
.avatar img{width:100%;height:100%;object-fit:cover;}
.message{max-width:min(75%,740px);padding:18px 22px;border-radius:22px;line-height:1.75;word-wrap:break-word;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);transition:all .3s;}
.message .msg-text{white-space:pre-wrap;}
.message .msg-text b{color:#00ffc8;font-weight:700;}
.message .msg-text code{background:rgba(0,255,200,.08);border:1px solid rgba(0,255,200,.2);padding:2px 8px;border-radius:8px;font-family:'JetBrains Mono',Consolas,monospace;font-size:.88em;color:#00ffc8;}
.message img.msg-img{max-width:260px;border-radius:18px;margin-top:12px;display:block;border:2px solid rgba(0,255,200,.25);cursor:pointer;transition:all .3s;}
.message img.msg-img:hover{box-shadow:0 0 35px rgba(0,255,200,.3);transform:scale(1.03);}
.ai{background:rgba(0,10,30,.7);border:2px solid rgba(0,255,200,.12);border-bottom-left-radius:8px;box-shadow:0 6px 35px rgba(0,255,200,.05),inset 0 1px 0 rgba(0,255,200,.08);}
.user{background:linear-gradient(135deg,rgba(255,45,149,.85),rgba(0,180,255,.85));border-bottom-right-radius:8px;box-shadow:0 6px 35px rgba(255,45,149,.2),0 10px 30px rgba(0,0,0,.2);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);}
.meta{font-size:10px;opacity:.45;margin-top:8px;display:flex;align-items:center;gap:7px;}
.brain-badge{display:inline-flex;align-items:center;padding:2px 10px;border-radius:10px;background:rgba(0,255,200,.08);border:1px solid rgba(0,255,200,.25);font-size:10px;color:#00ffc8;font-weight:700;}
.copy-btn{cursor:pointer;opacity:.4;margin-left:auto;transition:all .2s;padding:3px 6px;border-radius:6px;}
.copy-btn:hover{opacity:1;background:rgba(0,255,200,.1);}
.thinking{display:flex;align-items:center;gap:8px;color:#00ffc8;font-style:italic;}
.thinking span{width:9px;height:9px;border-radius:50%;background:var(--pink);animation:bounce 1.2s infinite;}
.thinking span:nth-child(2){animation-delay:.15s}.thinking span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:.3}30%{transform:translateY(-10px);opacity:1}}
.gallery-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:14px;max-width:440px;}
.gallery-item{position:relative;border-radius:18px;overflow:hidden;border:2px solid rgba(0,255,200,.2);cursor:pointer;aspect-ratio:1;background:rgba(0,0,0,.4);transition:all .3s cubic-bezier(.2,.9,.3,1.2);}
.gallery-item:hover{transform:scale(1.04);box-shadow:0 0 35px rgba(0,255,200,.35),0 10px 40px rgba(0,0,0,.4);border-color:rgba(0,255,200,.5);}
.gallery-item img{width:100%;height:100%;object-fit:cover;display:block;}
.gallery-item .gi-overlay{position:absolute;inset:0;background:linear-gradient(transparent 50%,rgba(0,0,0,.7));opacity:0;transition:opacity .3s;display:flex;align-items:flex-end;justify-content:center;padding:12px;}
.gallery-item:hover .gi-overlay{opacity:1;}
.gi-overlay span{color:#fff;font-size:22px;}
.img-loading{display:flex;align-items:center;justify-content:center;height:100%;color:var(--mut);font-size:11px;animation:pulse 1.5s infinite;}
.lightbox{position:fixed;inset:0;background:rgba(0,0,0,.95);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);z-index:200;display:none;align-items:center;justify-content:center;flex-direction:column;gap:18px;padding:20px;}
.lightbox.show{display:flex;}
.lightbox img{max-width:90vw;max-height:72vh;border-radius:22px;box-shadow:0 0 100px rgba(0,255,200,.3),0 24px 70px rgba(0,0,0,.6);border:2px solid rgba(0,255,200,.25);}
.lightbox-actions{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;}
.lb-btn{padding:14px 28px;border-radius:16px;border:2px solid rgba(0,255,200,.25);background:rgba(0,255,200,.04);color:var(--txt);cursor:pointer;font-size:14px;font-weight:600;transition:all .25s cubic-bezier(.2,.9,.3,1.2);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);text-decoration:none;}
.lb-btn:hover{background:rgba(0,255,200,.12);transform:translateY(-3px);box-shadow:0 10px 28px rgba(0,255,200,.2);border-color:rgba(0,255,200,.5);}
.lb-close{position:absolute;top:24px;right:24px;width:52px;height:52px;border-radius:50%;border:2px solid rgba(0,255,200,.3);background:rgba(0,255,200,.04);color:var(--txt);font-size:24px;cursor:pointer;display:grid;place-items:center;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:all .25s;}
.lb-close:hover{background:rgba(255,45,149,.15);border-color:rgba(255,45,149,.5);transform:scale(1.12);box-shadow:0 0 20px rgba(255,45,149,.3);}
.bottom{padding:18px 20px calc(18px + var(--safe-b));background:rgba(0,0,0,.55);border-top:2px solid rgba(0,255,200,.15);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);}
.status-row{display:flex;align-items:center;gap:12px;margin:0 4px 14px;flex-wrap:wrap;}
.voice-status{min-height:18px;color:#00ffc8;font-size:13px;font-weight:600;flex:1;min-width:150px;}
#waveform{display:none;align-items:center;gap:3px;height:24px;cursor:pointer;}
body.speaking #waveform{display:flex;}
#waveform span{width:5px;height:22px;background:linear-gradient(180deg,var(--pink),var(--pink2));border-radius:3px;animation:wv .8s infinite ease-in-out;box-shadow:0 0 8px rgba(0,255,200,.3);}
#waveform span:nth-child(2){animation-delay:.12s}#waveform span:nth-child(3){animation-delay:.24s}#waveform span:nth-child(4){animation-delay:.36s}#waveform span:nth-child(5){animation-delay:.48s}
@keyframes wv{0%,100%{transform:scaleY(.2)}50%{transform:scaleY(1)}}
.quick-actions{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;}
.quick-btn{padding:9px 18px;border-radius:999px;border:2px solid rgba(0,255,200,.15);background:rgba(0,255,200,.03);color:var(--txt);font-size:12px;font-weight:600;cursor:pointer;transition:all .25s cubic-bezier(.2,.9,.3,1.2);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);position:relative;overflow:hidden;}
.quick-btn::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(0,255,200,.12),rgba(255,45,149,.06));opacity:0;transition:opacity .25s;}
.quick-btn:hover::before{opacity:1;}
.quick-btn:hover{transform:translateY(-3px);border-color:rgba(0,255,200,.45);box-shadow:0 6px 24px rgba(0,255,200,.2);}
.composer{display:flex;gap:10px;align-items:center;}
input{flex:1;min-width:0;padding:16px 22px;border:2px solid rgba(0,255,200,.2);border-radius:999px;outline:none;background:rgba(0,8,20,.7);color:#fff;font-size:15px;font-weight:500;transition:all .3s cubic-bezier(.2,.9,.3,1);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);letter-spacing:.3px;}
input:focus{border-color:rgba(0,255,200,.6);box-shadow:0 0 0 4px rgba(0,255,200,.1),0 0 50px rgba(0,255,200,.15),inset 0 0 25px rgba(0,255,200,.04);}
input::placeholder{color:var(--mut);font-weight:500;}
.action-btn{width:54px;height:54px;border:none;border-radius:18px;cursor:pointer;font-size:22px;color:white;transition:all .25s cubic-bezier(.2,.9,.3,1.2);flex:0 0 auto;position:relative;overflow:hidden;}
.action-btn::after{content:"";position:absolute;inset:0;background:rgba(255,255,255,.15);opacity:0;transition:opacity .2s;}
.action-btn:hover::after{opacity:1;}
.action-btn:hover{transform:translateY(-4px) scale(1.1);box-shadow:0 10px 30px rgba(0,0,0,.3);}
.action-btn:active{transform:translateY(-1px) scale(1.02);}
.mic{background:linear-gradient(135deg,#00c853,#00897b);box-shadow:0 6px 20px rgba(0,200,83,.3);}
.cam{background:linear-gradient(135deg,#ff9800,#f57c00);box-shadow:0 6px 20px rgba(255,152,0,.3);}
.scr{background:linear-gradient(135deg,#7c4dff,#651fff);box-shadow:0 6px 20px rgba(124,77,255,.3);}
.send{background:linear-gradient(135deg,var(--pink),var(--blue));box-shadow:0 6px 24px rgba(0,255,200,.35);}
.fab{display:none;width:54px;height:54px;border:none;border-radius:18px;background:linear-gradient(135deg,var(--pink),var(--pink2));color:#fff;font-size:24px;cursor:pointer;transition:all .3s cubic-bezier(.2,.9,.3,1.2);flex:0 0 auto;box-shadow:0 6px 24px rgba(255,45,149,.3);}
.fab:hover{transform:translateY(-3px) scale(1.06);}
.fab.spin{transform:rotate(45deg);}
.footer-note{margin-top:12px;text-align:center;color:var(--mut);font-size:10px;letter-spacing:2px;font-weight:600;text-transform:uppercase;}
.sheet-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);opacity:0;pointer-events:none;transition:opacity .3s;z-index:90;}
.sheet-backdrop.show{opacity:1;pointer-events:auto;}
.sheet{position:fixed;left:50%;transform:translate(-50%,105%);bottom:0;width:min(560px,100%);background:rgba(4,6,18,.98);border:2px solid rgba(0,255,200,.2);border-bottom:none;border-radius:28px 28px 0 0;padding:18px 22px calc(24px + var(--safe-b));transition:transform .4s cubic-bezier(.2,.9,.3,1.1);z-index:95;box-shadow:0 -24px 90px rgba(0,255,200,.15),0 -6px 24px rgba(0,0,0,.5);backdrop-filter:blur(30px);-webkit-backdrop-filter:blur(30px);}
.sheet.open{transform:translate(-50%,0);}
.sheet-handle{width:52px;height:6px;border-radius:99px;background:linear-gradient(90deg,rgba(0,255,200,.5),rgba(255,45,149,.4));margin:0 auto 16px;box-shadow:0 0 12px rgba(0,255,200,.3);}
.sheet-title{font-size:12px;letter-spacing:4px;color:var(--mut);text-transform:uppercase;margin-bottom:16px;text-align:center;font-weight:700;}
.sheet-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}
.tile{display:flex;flex-direction:column;align-items:center;gap:10px;padding:20px 12px;border-radius:22px;border:2px solid rgba(0,255,200,.12);background:rgba(0,255,200,.02);cursor:pointer;transition:all .25s cubic-bezier(.2,.9,.3,1.2);color:var(--txt);position:relative;overflow:hidden;}
.tile::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(0,255,200,.08),rgba(255,45,149,.04));opacity:0;transition:opacity .25s;}
.tile:hover::before{opacity:1;}
.tile:active{transform:scale(.95);}
.tile .ti{font-size:30px;}
.tile .tl{font-size:12px;font-weight:700;letter-spacing:.5px;}
.tile:hover{border-color:rgba(0,255,200,.4);box-shadow:0 6px 24px rgba(0,255,200,.15);transform:translateY(-3px);}
.wake-word-indicator{position:fixed;top:24px;right:24px;display:flex;align-items:center;gap:10px;padding:12px 22px;background:rgba(0,255,200,.08);border:2px solid rgba(0,255,200,.3);border-radius:30px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);opacity:0;transform:translateY(-20px);transition:all .3s cubic-bezier(.2,.9,.3,1.2);z-index:1000;box-shadow:0 6px 24px rgba(0,255,200,.1);}
.wake-word-indicator.active{opacity:1;transform:translateY(0);}
.wake-word-indicator.listening{background:rgba(0,200,83,.1);border-color:rgba(0,200,83,.4);box-shadow:0 6px 24px rgba(0,200,83,.1);}
.wake-word-indicator.speaking{background:rgba(255,45,149,.1);border-color:rgba(255,45,149,.4);box-shadow:0 6px 24px rgba(255,45,149,.1);}
.wake-word-orb{width:14px;height:14px;border-radius:50%;background:var(--pink);animation:orbPulse 1.5s ease-in-out infinite;box-shadow:0 0 12px var(--pink);}
.wake-word-indicator.listening .wake-word-orb{background:#00c853;box-shadow:0 0 14px #00c853;}
.wake-word-indicator.speaking .wake-word-orb{background:#ff6db8;box-shadow:0 0 14px #ff6db8;}
@keyframes orbPulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.5);opacity:.6}}
.wake-word-text{color:#fff;font-size:13px;font-weight:700;letter-spacing:.5px;}
body[data-theme="ocean"]{--bg:#020810;--card:rgba(0,16,40,.85);--line:rgba(0,180,255,.22);--pink:#00b4ff;--violet:#3b82f6;--pink2:#00e5ff;--blue:#60a5fa;--txt:#f0f8ff;--mut:#6ba0c4;--panel-border:rgba(0,180,255,.18);}
body[data-theme="ocean"] .message .msg-text b{color:#bae6fd;}
body[data-theme="sunset"]{--bg:#100505;--card:rgba(40,8,12,.85);--line:rgba(255,120,50,.22);--pink:#ff7832;--violet:#f472b6;--pink2:#ff4500;--blue:#ffb347;--txt:#fff5f0;--mut:#c4886e;--panel-border:rgba(255,120,50,.18);}
body[data-theme="sunset"] .message .msg-text b{color:#ffedd5;}
body[data-theme="mint"]{--bg:#020e0a;--card:rgba(0,30,20,.85);--line:rgba(0,230,150,.22);--pink:#00e696;--violet:#059669;--pink2:#00bfa5;--blue:#69f0ae;--txt:#f0fff5;--mut:#6bb89e;--panel-border:rgba(0,230,150,.18);}
body[data-theme="mint"] .message .msg-text b{color:#d1fae5;}
body[data-theme="stealth"]{--bg:#060810;--card:rgba(10,14,28,.85);--line:rgba(60,130,255,.22);--pink:#3c82ff;--violet:#2563eb;--pink2:#06b6d4;--blue:#60a5fa;--txt:#f0f4ff;--mut:#7a92b8;--panel-border:rgba(60,130,255,.18);}
body[data-theme="stealth"] .message .msg-text b{color:#bfdbfe;}
body[data-theme="ivory"]{--bg:#f0f2f8;--card:rgba(255,255,255,.92);--line:rgba(80,80,200,.2);--pink:#5050c8;--violet:#7c3aed;--pink2:#ec4899;--blue:#06b6d4;--txt:#1a1a2e;--mut:#5a5a7a;--glass:rgba(255,255,255,.7);--panel-border:rgba(80,80,200,.15);}
body[data-theme="ivory"] .message .msg-text b{color:#4338ca;}
body[data-theme="ivory"] input{background:#fff;color:#1a1a2e;}
body[data-theme="ivory"] .small-btn,body[data-theme="ivory"] .settings-btn,body[data-theme="ivory"] .quick-btn,body[data-theme="ivory"] .voice-select{background:rgba(255,255,255,.8);color:#2a2a3e;}
body[data-theme="ivory"] .sheet{background:#fafbff;}
body[data-theme="ivory"] .tile{background:rgba(240,242,252,.8);color:#1a1a2e;}
body[data-theme="ivory"] .online,body[data-theme="ivory"] .voice-status{color:#059669;}
body[data-theme="ivory"] .bottom{background:rgba(255,255,255,.85);}
body[data-theme="ivory"] .header{background:rgba(255,255,255,.6);}
body[data-theme="ivory"] .ai{background:rgba(255,255,255,.75);border-color:rgba(80,80,200,.12);}
@media (min-width:701px) and (max-width:1024px){.app{height:96vh;min-height:500px;}.header{padding:12px 18px;}.title{font-size:18px;}#chat{padding:18px 16px;}.action-btn{width:48px;height:48px;}input{padding:14px 18px;font-size:14px;}}
@media (max-width:700px){body{padding:0;}body::before{height:35vh;}body::after{background:radial-gradient(500px 250px at 5% 0%,rgba(0,255,200,.12),transparent),radial-gradient(600px 300px at 95% 5%,rgba(255,45,149,.12),transparent);}.app{width:100%;height:100vh;height:100dvh;min-height:0;border-radius:0;border-width:0 1px;border-left:1px solid rgba(0,255,200,.15);border-right:1px solid rgba(0,255,200,.15);animation:appLoad .5s cubic-bezier(.2,.9,.3,1) both;}.header{padding:10px 14px;gap:10px;border-bottom-width:2px;}.logo-wrap{width:44px;height:44px;}.logo-wrap .logo-img{width:44px;height:44px;border-radius:16px;}.logo-ring{inset:-6px;border-radius:20px;}.logo-ring.r2{inset:-12px;border-radius:24px;}.logo-glow{inset:-20px;}.brand{gap:10px;}.title{font-size:16px;letter-spacing:1.5px;}.ver{font-size:8px;padding:2px 8px;}.online{font-size:10px;}.mood-badge{font-size:15px;}.settings-btn{width:42px;height:42px;border-radius:14px;font-size:18px;}.settings-grid{padding:12px 14px;gap:6px;}.small-btn{padding:8px 12px;font-size:11px;border-radius:12px;}.theme-row{padding:4px 14px 12px;}.theme-dot{width:28px;height:28px;}#chat{padding:14px 12px;}.message{max-width:88%;padding:14px 16px;border-radius:18px;}.message-row{gap:8px;margin:10px 0;}.avatar{width:34px;height:34px;border-radius:12px;font-size:15px;}.quick-actions{display:none;}.fab{display:block;}
/* FAB Mobile Fix */
@media(max-width:700px){
.fab{bottom:80px !important;right:14px !important;width:52px !important;height:52px !important;}
}
.cam,.scr{display:none;}.action-btn{width:46px;height:46px;border-radius:16px;font-size:20px;}.composer{gap:8px;}input{font-size:15px;padding:14px 16px;min-height:48px;}.footer-note{display:none;}.gallery-grid{max-width:100%;gap:6px;}.wake-word-indicator{top:12px;right:12px;padding:8px 14px;font-size:11px;border-radius:24px;}.sheet{border-radius:24px 24px 0 0;padding:14px 16px calc(20px + var(--safe-b));}.sheet-grid{grid-template-columns:repeat(3,1fr);gap:8px;}.tile{padding:14px 8px;border-radius:18px;}.tile .ti{font-size:26px;}.tile .tl{font-size:10px;}}
@media (max-width:400px){.title{font-size:14px;letter-spacing:1px;}.header{padding:8px 10px;}.settings-btn{width:38px;height:38px;font-size:16px;}.action-btn{width:42px;height:42px;border-radius:14px;font-size:18px;}input{padding:12px 14px;font-size:14px;}.message{max-width:92%;padding:12px 14px;border-radius:16px;}}
</style>
</head>
<body>
<div class="aurora"><i></i><i></i><i></i><i></i></div>
<canvas id="particles"></canvas>
<div id="wakeIndicator" class="wake-word-indicator">
<div class="wake-word-orb"></div>
<span class="wake-word-text">Listening for "Macha"...</span>
</div>
<div class="app">
<div class="header">
<div class="brand">
<div class="logo-wrap"><img src="/logo.png" alt="Vasanth AI" class="logo-img"><div class="logo-ring"></div><div class="logo-ring r2"></div><div class="logo-glow"></div></div>
<div>
<div class="title">VASANTH AI <span class="ver" id="verBadge">ROYAL</span> <span class="mood-badge" id="moodBadge">😊</span></div>
<div class="online"><span class="dot"></span><span id="onlineText">Online</span></div>
</div>
</div>
<button class="settings-btn" onclick="toggleSettings()" id="settingsBtn" title="Settings">⚙️</button>
</div>
<div class="settings-panel" id="settingsPanel">
<div class="settings-grid">
<select id="voiceSelect" onchange="changeVoice()" class="voice-select" title="Select Voice">
<option value="pallavi">👩 Pallavi</option>
<option value="cute">🎀 Cute</option>
<option value="saranya">🌏 Saranya</option>
</select>
<button class="small-btn active" onclick="toggleVoiceOnOff()" id="voiceOnOffBtn">🔊 Voice: ON</button>
<button class="small-btn" onclick="toggleLive()" id="liveBtn">🎙️ Live: OFF</button>
<button class="small-btn" onclick="toggleGesture()" id="gestureBtn">✋ Gesture: OFF</button>
<button class="small-btn active" onclick="toggleWakeWord()" id="wakeBtn">🎙️ Wake: ON</button>
<button class="small-btn" onclick="installApp()" id="installBtn" style="display:none">📲 Install</button>
<select id="personalitySelect" onchange="changePersonality()" class="voice-select" title="Personality Mode">
<option value="friend">😎 Friend</option>
<option value="teacher">🎓 Teacher</option>
<option value="professional">💼 Professional</option>
<option value="funny">🤣 Funny</option>
</select>
<button class="small-btn" onclick="openWakeWordModal()">🗣️ Wake Words</button>
<button class="small-btn" onclick="clearChat()">🗑️ Clear</button>
<button class="small-btn" onclick="aiTheme()">🎨 AI Theme</button>
<button class="small-btn" onclick="window.open('/api/export')">💾 Export</button>
<button class="small-btn" onclick="window.open('/jarvis','_blank')">🤖 JARVIS Mode</button>
</div>
<div class="theme-row">
<span class="theme-label">🎨 Theme:</span>
<button class="theme-dot active" data-theme="royal" style="background:linear-gradient(135deg,#e879f9,#8b5cf6)" onclick="applyTheme('royal','ROYAL')" title="Royal Aurora"></button>
<button class="theme-dot" data-theme="ocean" style="background:linear-gradient(135deg,#22d3ee,#3b82f6)" onclick="applyTheme('ocean','OCEAN')" title="Ocean Calm"></button>
<button class="theme-dot" data-theme="sunset" style="background:linear-gradient(135deg,#fb923c,#f472b6)" onclick="applyTheme('sunset','SUNSET')" title="Sunset Warm"></button>
<button class="theme-dot" data-theme="mint" style="background:linear-gradient(135deg,#34d399,#059669)" onclick="applyTheme('mint','MINT')" title="Mint Fresh"></button>
<button class="theme-dot" data-theme="ivory" style="background:linear-gradient(135deg,#f8fafc,#c7d2fe)" onclick="applyTheme('ivory','IVORY')" title="Ivory Light"></button>
<button class="theme-dot" data-theme="stealth" style="background:linear-gradient(135deg,#3b82f6,#0e1116)" onclick="applyTheme('stealth','STEALTH')" title="Stealth Dark"></button>
</div>
</div>
<div id="chat"></div>
<div class="bottom">
<div class="status-row">
<div id="voiceStatus" class="voice-status">🔊 Ready</div>
<div style="position:relative"><input id="chatSearch" type="text" placeholder="🔍 Search..." style="width:160px;padding:6px 12px;font-size:11px;border-radius:12px;border:1px solid var(--panel-border);background:rgba(0,0,0,.4);color:var(--txt);outline:none;min-height:auto;flex:none" oninput="searchChat(this.value)"><div id="searchResults" style="display:none;position:absolute;bottom:calc(100% + 4px);left:0;right:0;background:rgba(10,14,30,.95);border:1px solid var(--panel-border);border-radius:12px;max-height:200px;overflow-y:auto;z-index:50;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)"></div></div>
<div style="position:relative"><input id="chatSearch" type="text" placeholder="🔍 Search chat..." style="width:180px;padding:7px 12px;font-size:11px;border-radius:12px;min-height:auto;flex:none" oninput="searchChat(this.value)"><div id="searchResults" style="display:none;position:absolute;bottom:100%;left:0;right:0;background:rgba(10,14,30,.95);border:1px solid var(--panel-border);border-radius:12px;max-height:200px;overflow-y:auto;z-index:50;margin-bottom:4px;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)"></div></div>
<div id="waveform" onclick="stopSpeaking()" title="🔇 Click to STOP voice"><span></span><span></span><span></span><span></span><span></span></div>
</div>
<div class="quick-actions">
<button class="quick-btn" onclick="quickSend('Draw a cute robot')">🎨 Draw</button>
<button class="quick-btn" onclick="quickSend('Weather enna?')">🌦️ Weather</button>
<button class="quick-btn" onclick="quickSend('Bitcoin price')">📈 Crypto</button>
<button class="quick-btn" onclick="quickSend('Translate: vanakkam to english')">🌍 Translate</button>
<button class="quick-btn" onclick="quickSend('Today news sollu')">📰 News</button>
<button class="quick-btn" onclick="quickSend('India cricket score')">🏏 Cricket</button>
<button class="quick-btn" onclick="quickSend('Play AR Rahman songs')">🎵 Music</button>
<button class="quick-btn" onclick="quickSend('Screen paaru')">👁 Screen</button>
<button class="quick-btn" onclick="quickSend('Story about a brave kid')">📖 Story</button>
<button class="quick-btn" onclick="quickSend('Quiz me on general knowledge')">🧠 Quiz</button>
<button class="quick-btn" onclick="quickSend('show skills')">🎓 Skills</button>
<button class="quick-btn" onclick="quickSend('daily report')">📊 Report</button>
</div>
<div class="composer">
<input id="message" type="text" placeholder="Say 'Macha' or type..." autocomplete="off">
<button class="action-btn scr" onclick="quickSend('Take screenshot')" title="Screenshot">📸</button>
<button class="action-btn cam" onclick="pickImage()" title="Photo">📷</button>
<button class="action-btn mic" onclick="startVoice()" title="Voice">🎤</button>
<button class="action-btn send" onclick="sendMessage()" title="Send">➤</button>
<button class="fab" id="fabBtn" onclick="toggleSheet()" title="Quick Actions">✨</button>
</div>
<div class="footer-note">VASANTH AI • 🚀 ULTIMATE PREMIUM EDITION</div>
</div>
<div class="sheet-backdrop" id="sheetBackdrop" onclick="toggleSheet(false)"></div>
<div class="sheet" id="quickSheet">
<div class="sheet-handle"></div>
<div class="sheet-title">⚡ Quick Actions</div>
<div class="sheet-grid">
<div class="tile" onclick="quickSend('Draw a cute robot')"><span class="ti">🎨</span><span class="tl">Draw</span></div>
<div class="tile" onclick="quickSend('Weather enna?')"><span class="ti">🌦️</span><span class="tl">Weather</span></div>
<div class="tile" onclick="quickSend('Bitcoin price')"><span class="ti">📈</span><span class="tl">Crypto</span></div>
<div class="tile" onclick="quickSend('Translate: vanakkam to english')"><span class="ti">🌍</span><span class="tl">Translate</span></div>
<div class="tile" onclick="quickSend('Today news sollu')"><span class="ti">📰</span><span class="tl">News</span></div>
<div class="tile" onclick="quickSend('India cricket score')"><span class="ti">🏏</span><span class="tl">Cricket</span></div>
<div class="tile" onclick="quickSend('Play AR Rahman songs')"><span class="ti">🎵</span><span class="tl">Music</span></div>
<div class="tile" onclick="quickSend('Take screenshot')"><span class="ti">📸</span><span class="tl">Screenshot</span></div>
<div class="tile" onclick="pickImage()"><span class="ti">📷</span><span class="tl">Photo</span></div>
</div>
</div>
</div>
<div class="lightbox" id="lightbox">
<button class="lb-close" onclick="closeLightbox()">✕</button>
<img id="lbImg" src="" alt="Preview">
<div class="lightbox-actions">
<a class="lb-btn" id="lbDownload" href="" target="_blank" rel="noopener">💾 Download</a>
<button class="lb-btn" onclick="regenImage()">🔄 Regenerate</button>
</div>
</div>
<script>
const LOGO_HTML = '<img src="/logo.png" alt="AI">';
const THEME_LABELS = {royal:"ROYAL",ocean:"OCEAN",sunset:"SUNSET",mint:"MINT",ivory:"IVORY",stealth:"STEALTH"};
const wakeBeep = new Audio("data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdH2LkZaXmZaKi4uLioqJiIeGhYSDgoGAfn18e3p5eHd3d3Z1dXRzc29ubWxqaWhnZmVkY2NiYGBfXl1cW1taWVlZWVhYV1dWVlVVVFRUU1NSUlJRUFBQT09OTk1NTUxMTEw/Pz8+Pj49PT08PDw8Ozs7Ojo6OTo5OTk5ODg4ODc3Nzc2NjY1NTU1NDQ0NDMzMzMyMjIxMTExMDAwLy8vLi4uLS0tLCwsKysrKioqKSkoKCgnJycmJiYlJSUlJCQkIyMjIiIiISEhICAgICAgIB8fHx4eHh0dHRwcHBsbGxoaGhkZGRgYGBcXFxYWFhUUFBQTExMSEhIREREQEBAQEBAQEA8PDw4ODg0NDQwMDAsLCwoKCgkJCQgICAcHBwYGBgUFBQQEBAMDAwICAgEBAQAAAAD//wAA//8AAP//AAD//wAA");
function playWakeBeep(){ try{ wakeBeep.currentTime=0; wakeBeep.play().catch(e=>{}); }catch(e){} }
const MOOD_EMOJI = { happy:"😊", sad:"😢", excited:"🤩", tired:"😴", angry:"😠", neutral:"😐", curious:"🤓" };
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
function toggleSettings(){ document.getElementById("settingsPanel").classList.toggle("open"); }
function toggleSheet(force){
const s=document.getElementById("quickSheet"), b=document.getElementById("sheetBackdrop"), f=document.getElementById("fabBtn");
const open=(force===undefined)?!s.classList.contains("open"):force;
s.classList.toggle("open",open); b.classList.toggle("show",open);
if(f)f.classList.toggle("spin",open);
}
let voiceEnabled = localStorage.getItem("voiceEnabled") !== "off";
function toggleVoiceOnOff(){
voiceEnabled=!voiceEnabled;
localStorage.setItem("voiceEnabled", voiceEnabled?"on":"off");
const b=document.getElementById("voiceOnOffBtn");
b.textContent = voiceEnabled?"🔊 Voice: ON":"🔇 Voice: OFF";
b.classList.toggle("active",voiceEnabled);
fetch(voiceEnabled?"/voice/on":"/voice/off",{method:"POST"});
setVoiceStatus(voiceEnabled?"🔊 Voice ON":"🔇 Voice OFF (text only)");
}
function applyTheme(t,label){
["--bg","--card","--line","--pink","--violet","--pink2","--blue","--txt","--mut","--glass"].forEach(k=>document.body.style.removeProperty(k));
document.body.setAttribute("data-theme",t);
localStorage.setItem("vaTheme",t);
document.getElementById("verBadge").textContent=label;
document.querySelectorAll(".theme-dot").forEach(d=>{ d.classList.toggle("active",d.getAttribute("data-theme")===t); });
setVoiceStatus("🎨 Theme: "+label);
}
function applyCustomTheme(c,name){
const map={"--bg":c.bg,"--card":c.card,"--line":c.line,"--pink":c.pink,"--violet":c.violet,"--pink2":c.pink2,"--blue":c.blue,"--txt":c.txt,"--mut":c.mut,"--glass":c.glass};
for(const k in map){ if(map[k]) document.body.style.setProperty(k,map[k]); }
document.body.setAttribute("data-theme","custom");
localStorage.setItem("vaTheme","custom");
localStorage.setItem("vaCustomTheme",JSON.stringify(c));
document.getElementById("verBadge").textContent=(name||"CUSTOM").toUpperCase().slice(0,10);
document.querySelectorAll(".theme-dot").forEach(d=>d.classList.remove("active"));
}
function aiTheme(){
const desc=prompt("🎨 Describe your dream theme:\n(e.g. 'golden desert', 'toxic jungle', 'blood moon', 'emerald forest')");
if(!desc)return;
setVoiceStatus("🎨 AI theme generate pannuren...");
fetch("/api/theme",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({desc:desc})})
.then(r=>r.json()).then(d=>{
if(!d.success){setVoiceStatus("⚠️ Theme generate aagala");return;}
applyCustomTheme(d.colors,desc);
setVoiceStatus("🎨 Ready: "+desc);
if(voiceEnabled)playTTS("Ungalukkaana custom theme ready macha!");
}).catch(()=>setVoiceStatus("⚠️ Error"));
}
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
if(d.enabled && d.last && (Date.now()/1000 - d.last.timestamp)<2){ setVoiceStatus("✋ Gesture: "+d.last.gesture); }
}catch(e){}
},1000);
async function pollMood(){
try{
const r = await fetch("/mood"); const d = await r.json();
if(d && d.mood){
const badge = document.getElementById("moodBadge");
badge.textContent = MOOD_EMOJI[d.mood] || "😐";
badge.title = (d.mood || "neutral") + " (" + (d.intensity || 5) + "/10)";
}
}catch(e){}
setTimeout(pollMood, 5000);
}
pollMood();
(function(){const b=document.getElementById("voiceOnOffBtn");if(b){b.textContent=voiceEnabled?"🔊 Voice: ON":"🔇 Voice: OFF";b.classList.toggle("active",voiceEnabled);}})();
(function(){
const t=localStorage.getItem("vaTheme")||"royal";
if(t==="custom"){
try{applyCustomTheme(JSON.parse(localStorage.getItem("vaCustomTheme")||"{}"),"CUSTOM");}catch(e){}
}else{
document.body.setAttribute("data-theme",t);
document.getElementById("verBadge").textContent=THEME_LABELS[t]||"ROYAL";
document.querySelectorAll(".theme-dot").forEach(d=>{ d.classList.toggle("active",d.getAttribute("data-theme")===t); });
}
})();
</script>
<script>
const cv=document.getElementById("particles"),cx=cv.getContext("2d");
let P=[];
function rsz(){cv.width=innerWidth;cv.height=innerHeight;}
rsz();addEventListener("resize",rsz);
for(let i=0;i<80;i++){const hue=Math.random()>.5?185:270;P.push({x:Math.random()*innerWidth,y:Math.random()*innerHeight,vx:(Math.random()-.5)*.6,vy:(Math.random()-.5)*.6,r:Math.random()*2.5+.5,hue:hue,glow:Math.random()>.7});}
function drawP(){cx.clearRect(0,0,cv.width,cv.height);
for(const p of P){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>cv.width)p.vx*=-1;if(p.y<0||p.y>cv.height)p.vy*=-1;
cx.beginPath();cx.arc(p.x,p.y,p.r,0,7);
if(p.glow){cx.shadowBlur=12;cx.shadowColor="hsla("+p.hue+",80%,65%,.6)";}
cx.fillStyle="hsla("+p.hue+",75%,65%,.45)";cx.fill();cx.shadowBlur=0;}
for(let i=0;i<P.length;i++)for(let j=i+1;j<P.length;j++){const dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d=dx*dx+dy*dy;if(d<10000){const al=0.12*(1-d/10000);cx.strokeStyle="rgba(167,139,250,"+al.toFixed(3)+")";cx.lineWidth=.8;cx.beginPath();cx.moveTo(P[i].x,P[i].y);cx.lineTo(P[j].x,P[j].y);cx.stroke();}}
requestAnimationFrame(drawP);}
drawP();
const chat=document.getElementById("chat"),input=document.getElementById("message");
let wakeWordEnabled=true,wakeActive=false,busy=false,wakeRecognition=null,commandRecognition=null;
let lastPrompt="";
let customWake=localStorage.getItem("customWake")||"";
function buildWakePatterns(){const p=[/mach/i,/much/i,/vasan/i,/மச்சா/,/வசந்த/];if(customWake){const w=customWake.toLowerCase().replace(/[^a-z0-9஀-௿ ]/gi,"").trim();if(w)p.unshift(new RegExp(w.replace(/\s+/g,"\\s+"),"i"));}return p;}
let WAKE_PATTERNS=buildWakePatterns();
function setCustomWake(){const v=prompt("🗣️ New wake word sollu (empty = 'Macha'):",customWake||"");if(v===null)return;customWake=v.trim();localStorage.setItem("customWake",customWake);WAKE_PATTERNS=buildWakePatterns();setVoiceStatus("🗣️ Wake word: "+(customWake||"Macha"));const wt=document.querySelector(".wake-word-text");if(wt)wt.textContent='Listening "'+(customWake||"Macha")+'"...';}
function changePersonality(){const m=document.getElementById("personalitySelect").value;fetch("/api/personality",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({mode:m})});setVoiceStatus("🎭 Mode: "+m);}
fetch("/api/personality").then(r=>r.json()).then(d=>{const s=document.getElementById("personalitySelect");if(s)s.value=d.mode||"friend";}).catch(()=>{});
const QUICK_PHRASES={"vanakkam":"Vanakkam macha! Enna vishayam?","hi":"Hi macha! Sollu","hello":"Hello macha!","hii":"Hi macha!","ok":"Sari macha!","thanks":"Welcome macha!","nandri":"Welcome macha!","sollu":"Sollu macha!"};
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
function extractImgData(t){
let imgData=null;
const g=t.match(/\[\[GALLERY:(.*?)\]\]/);
if(g){imgData={type:"gallery",urls:g[1].split("|").filter(u=>u)};t=t.replace(g[0],"").trim();return [t,imgData];}
const s=t.match(/\[\[IMG:(.*?)\]\]/);
if(s){imgData={type:"single",url:s[1]};t=t.replace(s[0],"").trim();}
return [t,imgData];
}
function addMessage(t,type,time=null,imgData=null,animate=false,brain=""){
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
if(imgData){
if(imgData.type==="gallery" && imgData.urls && imgData.urls.length){
const grid=document.createElement("div");grid.className="gallery-grid";
imgData.urls.forEach(function(u,i){
const item=document.createElement("div");item.className="gallery-item";
const load=document.createElement("div");load.className="img-loading";load.textContent="🎨 Loading "+(i+1)+"...";
const im=document.createElement("img");im.alt="Generated "+(i+1);im.style.display="none";
let tries=0,lastAttempt=0;
function setSrc(){
const sep=u.indexOf("?");
const base=u.slice(0,sep);
const params=new URLSearchParams(u.slice(sep+1));
params.set("seed",String(Math.floor(Math.random()*1000000)+tries));
im.src=base+"?"+params.toString();
}
im.onload=function(){im.style.display="block";if(load.parentNode)load.remove();};
im.onerror=function(){
const now=Date.now();
if(now-lastAttempt<1500)return;
lastAttempt=now; tries++;
if(tries>=6){ load.textContent="❌ Failed — tap retry"; item.onclick=function(){load.textContent="🔄 Retrying...";tries=0;setTimeout(setSrc,300);}; return; }
setTimeout(setSrc,2000+Math.random()*1000);
};
setTimeout(setSrc, i*1500+Math.random()*500);
const ov=document.createElement("div");ov.className="gi-overlay";ov.innerHTML="<span>🔍</span>";
item.appendChild(load);item.appendChild(im);item.appendChild(ov);
item.addEventListener("click",function(){if(im.style.display==="block")openLightbox(im.src);});
grid.appendChild(item);
});
b.appendChild(grid);
} else if(imgData.type==="single" && imgData.url){
const im=document.createElement("img");im.src=imgData.url;im.className="msg-img";im.onclick=function(){openLightbox(imgData.url);};b.appendChild(im);
} else if(imgData.type==="story" && imgData.scenes){
const wrap=document.createElement("div");
imgData.scenes.forEach(function(s){
const im=document.createElement("img");im.src=s.url;im.className="msg-img";im.style.maxWidth="100%";im.style.cursor="pointer";im.onclick=function(){openLightbox(s.url);};wrap.appendChild(im);
const p=document.createElement("div");p.style.margin="8px 0 12px";p.style.lineHeight="1.6";p.textContent=s.text;wrap.appendChild(p);
});
b.appendChild(wrap);
}
}
const txt=document.createElement("div"); txt.className="msg-text"; b.appendChild(txt);
const m=document.createElement("div");m.className="meta";
let meta=type==="user"?"You":type==="proactive"?"🔮 Proactive":"Vasanth AI";
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
function showWelcome(){chat.innerHTML="";addMessage("வணக்கம் Vasanth! 👋\n**PREMIUM EDITION** 💎\n🎨 **6 Themes** - Settings-ல try பண்ணு\n🖼️ **4-Image Gallery** - Draw command-ல\n🎵 **Music Player** - JARVIS mode-ல controls\n🎤 **Fast Voice** - instant TTS\n📱 **Mobile Sheet** - ✨ button tap\n🤖 **JARVIS Mode** - Settings-ல open பண்ணு\n\n**Try:** 'Draw a cyberpunk city' / 'Play AR Rahman songs'","ai");}
async function loadHistory(){try{const r=await fetch("/history");if(!r.ok)throw new Error();const d=await r.json();chat.innerHTML="";if(!d.history||d.history.length===0){showWelcome();return;}d.history.forEach(i=>{
let txt=i.text||"";
const ex=extractImgData(txt); txt=ex[0]; const imgData=ex[1];
const isProactive = txt.startsWith("[proactive]");
const cleanText = isProactive ? txt.substring(12) : txt;
addMessage(cleanText, isProactive ? "proactive" : (i.role==="user"?"user":"ai"), null, imgData);
});}catch(e){showWelcome();}}
async function clearChat(){if(!confirm("Clear history?"))return;try{await fetch("/clear",{method:"POST"});showWelcome();setVoiceStatus("🧠 Fresh ready");}catch(e){alert("Error");}}
function changeVoice(){
const voice=document.getElementById("voiceSelect").value;
setVoiceStatus("🎤 Voice switching...");
fetch("/change-voice",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({voice:voice})})
.then(r=>r.json()).then(d=>{ if(d.success){ setVoiceStatus("🎤 Voice: "+d.name); if(voiceEnabled){playTTS("Vanakkam macha! Naan "+d.name+" voice-la pesuren.");} } })
.catch(e=>setVoiceStatus("⚠️ Voice error"));
}
let currentAudio=null;let currentDone=null;
function stopSpeaking(){
if(currentAudio){try{currentAudio.onended=null;currentAudio.onerror=null;currentAudio.pause();}catch(e){}currentAudio=null;}
fetch("/voice/stop",{method:"POST"}).catch(()=>{});
if(currentDone){const d=currentDone;currentDone=null;d();}
else{document.body.classList.remove("speaking");setVoiceStatus("🔇 Muted");}
}
function playTTS(t){
const key=(t||"").toLowerCase().trim();
if(QUICK_PHRASES[key]) t=QUICK_PHRASES[key];
return new Promise(async (resolve)=>{setVoiceStatus("🔊 Generating...");showIndicator("speaking","Speaking...");try{const r=await fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});if(!r.ok){if(!busy)finishCycle();resolve();return;}const b=await r.blob();if(!b.size){if(!busy)finishCycle();resolve();return;}const u=URL.createObjectURL(b),a=new Audio(u);currentAudio=a;a.onplay=()=>{setVoiceStatus("🔊 Speaking... (tap waveform = STOP)");document.body.classList.add("speaking");showIndicator("speaking","Speaking...");};const done=()=>{currentAudio=null;currentDone=null;document.body.classList.remove("speaking");setVoiceStatus("🔊 Ready");URL.revokeObjectURL(u);if(!busy)finishCycle();resolve();};currentDone=done;a.onended=done;a.onerror=done;await a.play().catch(e=>{done();});}catch(e){document.body.classList.remove("speaking");setVoiceStatus("⚠️ Error");if(!busy)finishCycle();resolve();}});
}
function openLightbox(url){
const lb=document.getElementById("lightbox");
document.getElementById("lbImg").src=url;
document.getElementById("lbDownload").href=url;
lb.classList.add("show");
}
function closeLightbox(){document.getElementById("lightbox").classList.remove("show");}
function regenImage(){
closeLightbox();
const p=lastPrompt||"a cute robot in neon style";
input.value="Draw "+p;sendMessage();
}
function quickSend(t){toggleSheet(false);input.value=t;sendMessage();}
function finishCycle(){busy=false;showIndicator("","");if(liveMode){setTimeout(startLiveListen,400);}else if(wakeWordEnabled){setTimeout(startWake,600);}}
async function sendMessage(){const t=input.value.trim();if(!t){finishCycle();return;}busy=true;stopWake();addMessage(t,"user");if(/draw|image|generate|picture|படம்|ஓவியம்/i.test(t)){lastPrompt=t.replace(/^(draw|generate|create|make|படம்)\s+/i,"");}input.value="";addThinking();setVoiceStatus(" Thinking...");showIndicator("listening","Processing...");try{const r=await fetch("/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t})});if(!r.ok)throw new Error();const d=await r.json();removeThinking();const replyText=d.reply||"...";
let ttsPromise=null;if(voiceEnabled){ttsPromise=playTTS(replyText);}
addMessage(replyText,"ai",null,d.image||null,true,d.brain||"");
if(ttsPromise){await ttsPromise;}
finishCycle();}catch(e){removeThinking();addMessage("Server error","ai");setVoiceStatus("🔴 Error");finishCycle();}}
function pickImage(){toggleSheet(false);document.getElementById("imageInput").click();}
async function onImagePicked(e){const file=e.target.files[0];if(!file)return;const reader=new FileReader();reader.onload=async function(){const dataURL=reader.result;const q=input.value.trim()||"Idhula enna iruku?";busy=true;stopWake();addMessage("📷 "+q,"user",null,dataURL);input.value="";addThinking();try{const r=await fetch("/vision",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:dataURL,question:q})});const d=await r.json();removeThinking();addMessage(d.reply,"ai",null,null,true,d.brain||"");if(voiceEnabled){await playTTS(d.reply);}finishCycle();}catch(err){removeThinking();addMessage("Vision error","ai");finishCycle();}};reader.readAsDataURL(file);e.target.value="";}
function detectWake(t){t=t.toLowerCase().trim();for(const p of WAKE_PATTERNS){const m=p.exec(t);if(m)return t.slice(m.index+m[0].length).trim();}return null;}
function stopWake(){if(wakeRecognition){try{wakeRecognition.onend=null;wakeRecognition.onerror=null;wakeRecognition.stop();}catch(e){}wakeRecognition=null;}wakeActive=false;}
function startWake(){if(!wakeWordEnabled||busy||wakeActive||liveMode)return;const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){setVoiceStatus("⚠️ Wake-க்கு Chrome வேணும்");return;}if(!window.isSecureContext){setVoiceStatus("🔒 Wake localhost-ல மட்டும்");return;}try{wakeRecognition=new SR();}catch(e){return;}wakeRecognition.lang="ta-IN";wakeRecognition.continuous=true;wakeRecognition.interimResults=true;wakeRecognition.onstart=()=>{wakeActive=true;showIndicator("active",'Listening "'+(customWake||"Macha")+'"...');};wakeRecognition.onresult=(e)=>{if(busy)return;let t="";for(let i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript;if(!t)return;console.log("🎤 wake heard:",t);const a=detectWake(t);if(a!==null){playWakeBeep();stopWake();busy=true;if(a.length>=2){input.value=a;sendMessage();}else{setVoiceStatus("🗣️ Sollu macha...");if(voiceEnabled){playTTS("Sollu macha! Enna sollanum?").then(()=>startCommandRecognition());}else{startCommandRecognition();}}}};wakeRecognition.onerror=(e)=>{console.log("wake error:",e.error);setVoiceStatus("🎤 Mic: "+e.error);};wakeRecognition.onend=()=>{wakeActive=false;if(wakeWordEnabled&&!busy&&!liveMode)setTimeout(startWake,500);};try{wakeRecognition.start();}catch(e){}}
function startCommandRecognition(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){finishCycle();return;}commandRecognition=new SR();commandRecognition.lang="ta-IN";commandRecognition.continuous=false;commandRecognition.interimResults=false;let got=false;commandRecognition.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};commandRecognition.onend=()=>{if(!got)finishCycle();};setTimeout(()=>{try{commandRecognition.start();}catch(e){finishCycle();}},400);}
function toggleWakeWord(){wakeWordEnabled=!wakeWordEnabled;const b=document.getElementById("wakeBtn");if(wakeWordEnabled){b.textContent="🎙️ Wake: ON";b.classList.add("active");startWake();}else{b.textContent="🎙️ Wake: OFF";b.classList.remove("active");stopWake();busy=false;showIndicator("","");}}
function startVoice(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){setVoiceStatus("⚠️ Chrome use பண்ணுங்க");return;}if(!window.isSecureContext){setVoiceStatus("🔒 Mic localhost-ல மட்டும் தான்");return;}busy=true;stopWake();const r=new SR();r.lang="ta-IN";r.continuous=false;r.interimResults=false;let got=false;setVoiceStatus("🎤 Speaking...");r.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};r.onerror=(e)=>{setVoiceStatus(e.error==="not-allowed"?"🚫 Mic Allow பண்ணுங்க":e.error==="no-speech"?"🤫 மறுபடி பேசு":"⚠️ Mic: "+e.error);};r.onend=()=>{if(!got)finishCycle();};try{r.start();}catch(e){finishCycle();}}
let deferredPrompt=null;
window.addEventListener("beforeinstallprompt",(e)=>{e.preventDefault();deferredPrompt=e;const b=document.getElementById("installBtn");if(b)b.style.display="inline-block";});
function installApp(){if(!deferredPrompt)return;deferredPrompt.prompt();deferredPrompt.userChoice.then(r=>{if(r.outcome==="accepted")document.getElementById("installBtn").style.display="none";deferredPrompt=null;});}
if("serviceWorker" in navigator){window.addEventListener("load",()=>{navigator.serviceWorker.register("/sw.js").catch(e=>{});});}
input.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();sendMessage();}});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){stopSpeaking();closeLightbox();toggleSheet(false);}});
document.getElementById("lightbox").addEventListener("click",function(e){if(e.target===this)closeLightbox();});
// === CHAT SEARCH ===
let searchTimeout=null;
async function searchChat(q){
    const box=document.getElementById("searchResults");
    if(!box)return;
    if(!q||q.length<2){box.style.display="none";box.innerHTML="";return;}
    clearTimeout(searchTimeout);
    searchTimeout=setTimeout(async()=>{
        try{const r=await fetch("/api/search?q="+encodeURIComponent(q));const d=await r.json();
        if(!d.results||!d.results.length){box.style.display="block";box.innerHTML="<div style='padding:10px;color:var(--mut);font-size:11px'>No results</div>";return;}
        box.style.display="block";box.innerHTML=d.results.slice(0,8).map(r=>`<div style="padding:8px 12px;font-size:11px;border-bottom:1px solid var(--panel-border);cursor:pointer;color:var(--txt)" onclick="document.getElementById('chatSearch').value='';document.getElementById('searchResults').style.display='none'"><b style="color:var(--pink);font-size:9px">${r.role=="user"?"You":"AI"}</b><br>${r.text.replace(/[<>&]/g,"").slice(0,100)}</div>`).join("");
        }catch(e){box.style.display="none";}
    },300);
}

// === WAKE WORD MODAL ===
async function openWakeWordModal(){
    try{const r=await fetch("/api/wakewords");const d=await r.json();
    const words=d.words||["Macha"];const active=d.active||"Macha";
    let html=`<div style="position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);z-index:200;display:flex;align-items:center;justify-content:center" onclick="if(event.target===this)this.remove()">
    <div style="background:rgba(10,14,30,.95);border:2px solid var(--panel-border);border-radius:20px;padding:24px;max-width:400px;width:90%;backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)">
    <h3 style="margin:0 0 16px;font-size:14px;letter-spacing:2px;color:var(--pink)">🗣️ WAKE WORDS</h3>
    <div id="wwList" style="margin-bottom:16px">${words.map(w=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border:1px solid var(--panel-border);border-radius:10px;margin-bottom:6px;${w===active?"border-color:var(--pink);background:rgba(0,255,200,.05)":"background:rgba(255,255,255,.02)"}"><span style="font-size:12px;color:var(--txt)">${w}</span><div style="display:flex;gap:6px"><button onclick="setActiveWake('${w}')" style="padding:4px 10px;border-radius:8px;border:1px solid var(--panel-border);background:rgba(0,255,200,.08);color:var(--txt);font-size:10px;cursor:pointer">${w===active?"Active":"Set Active"}</button><button onclick="removeWake('${w}')" style="padding:4px 10px;border-radius:8px;border:1px solid rgba(255,80,80,.3);background:rgba(255,80,80,.08);color:#ff6b6b;font-size:10px;cursor:pointer">Remove</button></div></div>`).join("")}</div>
    <div style="display:flex;gap:8px"><input id="newWakeInput" placeholder="Add new wake word..." style="flex:1;padding:10px 14px;border:2px solid var(--panel-border);border-radius:10px;background:rgba(0,0,0,.4);color:var(--txt);font-size:12px;outline:none"><button onclick="addWakeWord()" style="padding:10px 16px;border-radius:10px;border:none;background:linear-gradient(135deg,var(--pink),var(--blue));color:#fff;font-size:12px;font-weight:600;cursor:pointer">Add</button></div>
    <div style="margin-top:12px;text-align:center"><button onclick="this.closest('div[style*=fixed]').remove()" style="padding:8px 20px;border-radius:10px;border:1px solid var(--panel-border);background:rgba(255,255,255,.04);color:var(--mut);font-size:11px;cursor:pointer">Close</button></div>
    </div></div>`;
    document.body.insertAdjacentHTML("beforeend",html);
    }catch(e){}
}
async function setActiveWake(word){
    await fetch("/api/wakewords",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({active:word})});
    openWakeWordModal();
}
async function removeWake(word){
    await fetch("/api/wakewords/remove",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word:word})});
    openWakeWordModal();
}
async function addWakeWord(){
    const input=document.getElementById("newWakeInput");
    if(!input||!input.value.trim())return;
    await fetch("/api/wakewords/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word:input.value.trim()})});
    openWakeWordModal();
}

// === CHAT SEARCH ===
let searchTimeout=null;
async function searchChat(q){const box=document.getElementById("searchResults");if(!box)return;if(!q||q.length<2){box.style.display="none";box.innerHTML="";return;}clearTimeout(searchTimeout);searchTimeout=setTimeout(async()=>{try{const r=await fetch("/api/search?q="+encodeURIComponent(q));const d=await r.json();if(!d.results||!d.results.length){box.style.display="block";box.innerHTML='<div style="padding:10px;color:var(--mut);font-size:11px">No results</div>';return;}box.style.display="block";box.innerHTML=d.results.slice(0,8).map(r=>'<div style="padding:8px 12px;font-size:11px;border-bottom:1px solid var(--panel-border);cursor:pointer;color:var(--txt)" onclick="document.getElementById(\'chatSearch\').value=\'\';document.getElementById(\'searchResults\').style.display=\'none\'"><b style="color:var(--pink);font-size:9px">'+r.role+'</b><br>'+r.text.replace(/[<>]/g,"").slice(0,80)+'</div>').join("");}catch(e){box.style.display="none";}},300);}
// === WAKE WORD MODAL ===
async function openWakeWordModal(){try{const r=await fetch("/api/wakewords");const d=await r.json();const words=d.words||["Macha"];const active=d.active||"Macha";let h='<div id="wwModal" style="position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);z-index:200;display:flex;align-items:center;justify-content:center" onclick="if(event.target===this)this.remove()"><div style="background:rgba(10,14,30,.95);border:2px solid var(--panel-border);border-radius:20px;padding:24px;max-width:400px;width:90%"><h3 style="margin:0 0 16px;font-size:14px;letter-spacing:2px;color:var(--pink)">🗣️ WAKE WORDS</h3><div id="wwList" style="margin-bottom:16px">'+words.map(w=>'<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border:1px solid var(--panel-border);border-radius:10px;margin-bottom:6px;'+(w===active?"border-color:var(--pink);background:rgba(0,255,200,.05)":"background:rgba(255,255,255,.02)")+'"><span style="font-size:12px;color:var(--txt)">'+w+'</span><div style="display:flex;gap:6px"><button onclick="setActiveWake(\''+w+'\')" style="padding:4px 10px;border-radius:8px;border:1px solid var(--panel-border);background:rgba(0,255,200,.08);color:var(--txt);font-size:10px;cursor:pointer">'+(w===active?"Active":"Set")+'</button><button onclick="removeWake(\''+w+'\')" style="padding:4px 10px;border-radius:8px;border:1px solid rgba(255,80,80,.3);background:rgba(255,80,80,.08);color:#ff6b6b;font-size:10px;cursor:pointer">✕</button></div></div>').join("")+'</div><div style="display:flex;gap:8px"><input id="newWakeInput" placeholder="New wake word..." style="flex:1;padding:10px 14px;border:2px solid var(--panel-border);border-radius:10px;background:rgba(0,0,0,.4);color:var(--txt);font-size:12px;outline:none"><button onclick="addWakeWord()" style="padding:10px 16px;border-radius:10px;border:none;background:linear-gradient(135deg,var(--pink),var(--blue));color:#fff;font-size:12px;font-weight:600;cursor:pointer">Add</button></div><div style="margin-top:12px;text-align:center"><button onclick="this.closest(\'[id=wwModal]\').remove()" style="padding:8px 20px;border-radius:10px;border:1px solid var(--panel-border);background:rgba(255,255,255,.04);color:var(--mut);font-size:11px;cursor:pointer">Close</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",h);}catch(e){}}
async function setActiveWake(word){await fetch("/api/wakewords",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({active:word})});document.getElementById("wwModal")?.remove();openWakeWordModal();}
async function removeWake(word){await fetch("/api/wakewords/remove",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word})});document.getElementById("wwModal")?.remove();openWakeWordModal();}
async function addWakeWord(){const inp=document.getElementById("newWakeInput");if(!inp||!inp.value.trim())return;await fetch("/api/wakewords/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word:inp.value.trim()})});document.getElementById("wwModal")?.remove();openWakeWordModal();}

loadHistory();setTimeout(startWake,1000);
/* === REMOVE LOADING STATE === */
document.body.classList.remove('app-loading');
</script>

<!-- PARTICLE EXPLOSION CANVAS -->
<canvas id="particleExplosion" style="position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999;"></canvas>

</body>
</html>
"""

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

@app.route("/api/notes", methods=["GET","POST"])
def api_notes():
    d = load_notes()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        act = data.get("action")
        if act in ("add_note","add_todo"): track_event("notes")
        if act == "add_note":
            d["notes"].append({"text": data.get("text",""), "time": time.time()})
        elif act == "add_todo":
            d["todos"].append({"text": data.get("text",""), "done": False, "time": time.time()})
        elif act == "toggle_todo":
            i = data.get("index")
            if isinstance(i,int) and 0 <= i < len(d["todos"]): d["todos"][i]["done"] = not d["todos"][i]["done"]
        elif act == "del_note":
            i = data.get("index")
            if isinstance(i,int) and 0 <= i < len(d["notes"]): d["notes"].pop(i)
        elif act == "del_todo":
            i = data.get("index")
            if isinstance(i,int) and 0 <= i < len(d["todos"]): d["todos"].pop(i)
        save_notes(d)
        return jsonify({"success": True, "notes": d})
    return jsonify(d)

@app.route("/api/export")
def export_chat():
    lines = ["VASANTH AI — CHAT EXPORT", "="*40, ""]
    for m in conversation_history:
        who = "You" if m["role"] == "user" else "Vasanth AI"
        lines.append(f"[{who}] {m['text']}\n")
    return Response("\n".join(lines), mimetype="text/plain", headers={"Content-Disposition": "attachment; filename=vasanth_ai_chat.txt"})

def generate_story(topic):
    try:
        prompt = f"""Write a short engaging story in Tanglish about: {topic}
Return ONLY valid JSON like:
{{"title":"Story title","scenes":[{{"text":"2-3 sentence scene in Tanglish","image":"english image prompt"}},{{"text":"...","image":"..."}},{{"text":"...","image":"..."}},{{"text":"...","image":"..."}}]}}"""
        messages = [{"role":"system","content":"You are a creative storyteller. Return ONLY valid JSON with exactly 4 scenes."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        m = re.search(r'\{.*\}', reply or "", re.DOTALL)
        data = json.loads(m.group(0))
        scenes = []
        for s in data.get("scenes", [])[:4]:
            url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(s.get("image","fantasy cinematic scene")) + "?width=640&height=480&nologo=true"
            scenes.append({"text": s.get("text",""), "url": url})
        return f"📖 **{data.get('title','Story')}**\n[[STORY:{json.dumps(scenes)}]]"
    except Exception as e:
        print(f"Story error: {e}")
        return "Story generate panna mudiyala macha 😅 Thirumba try pannu!"

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

QUIZ_STATE = {"active": False, "questions": [], "index": 0, "score": 0, "topic": ""}

def start_quiz(topic):
    global QUIZ_STATE
    try:
        prompt = f"""Create a 5-question multiple choice quiz about: {topic}
Return ONLY valid JSON array like:
[{{"q":"question?","options":["opt1","opt2","opt3","opt4"],"answer":0}}]
answer = index of correct option (0-3). Fun, medium difficulty."""
        messages = [{"role":"system","content":"You are a quiz master. Return ONLY valid JSON array."},{"role":"user","content":prompt}]
        reply = _groq_complete(messages)
        m = re.search(r'\[.*\]', reply or "", re.DOTALL)
        qs = json.loads(m.group(0))
        if not isinstance(qs, list) or len(qs) < 1: raise Exception("bad quiz")
        QUIZ_STATE = {"active": True, "questions": qs[:5], "index": 0, "score": 0, "topic": topic}
        return quiz_question_text()
    except Exception as e:
        print(f"Quiz error: {e}")
        return "Quiz generate panna mudiyala macha 😅 Thirumba try pannu!"

def quiz_question_text():
    q = QUIZ_STATE["questions"][QUIZ_STATE["index"]]
    out = f"🧠 **QUIZ ({QUIZ_STATE['index']+1}/{len(QUIZ_STATE['questions'])})** — Topic: **{QUIZ_STATE['topic']}**\n\n**{q['q']}**\n"
    for i, o in enumerate(q.get("options", [])):
        out += f"\n**{i+1}** • {o}"
    out += "\n\n👉 Answer sollu macha! (1-4) • 'quit quiz' = exit"
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
        elif s >= tot//2: msg += "— Nalla iruku macha! 👍"
        else: msg += "— Paravala, next time adichu dhu! 💪"
        add_to_memory("user", f"[Quiz] {tp}"); add_to_memory("model", f"Quiz score {s}/{tot}")
        track_event("quiz")
        return msg
    fb = "✅ Correct macha! 🎉" if right else f"❌ Thappu macha! Correct: **{q['options'][correct]}**"
    return fb + "\n\n" + quiz_question_text()

FOCUS_TIMER = {"active": False, "end_time": 0, "duration": 1500, "mode": "work"}

def timer_thread():
    global FOCUS_TIMER
    while True:
        time.sleep(1)
        if FOCUS_TIMER.get("active") and time.time() >= FOCUS_TIMER["end_time"]:
            mode = FOCUS_TIMER["mode"]
            FOCUS_TIMER["active"] = False
            if mode == "work":
                proactive_speak("Macha! 25 minutes mudinjiduchu. Super work! Oru 5 minutes break eduthukko.")
            else:
                proactive_speak("Macha! Break over. Thirumba focus time! Velaiya paappoma?")

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

def build_daily_report():
    s = get_today_stats()
    score = min(100, s.get("msgs",0)*4 + s.get("quiz",0)*10 + s.get("notes",0)*8 + s.get("songs",0)*2 + s.get("shots",0)*3)
    grade = "S" if score>=80 else "A" if score>=60 else "B" if score>=40 else "C"
    temp, rain = get_weather_now()
    now = datetime.datetime.now()
    lines = [
        f"📊 **DAILY REPORT** — {now.strftime('%A, %d %B %Y')}",
        f"💬 Messages: **{s.get('msgs',0)}** • 🧠 Quiz: **{s.get('quiz',0)}** • 📝 Notes: **{s.get('notes',0)}**",
        f"🎵 Songs: **{s.get('songs',0)}** • 📸 Screenshots: **{s.get('shots',0)}**",
        f"🏆 Productivity Score: **{score}% (Grade {grade})**",
    ]
    if temp is not None:
        lines.append(f"🌦 Chennai: **{temp}°C**, rain chance **{rain}%**")
    lines.append(f"🕐 Uptime: {fmt_uptime(int(time.time()-SYSTEM_START))}")
    return "\n".join(lines)

@app.route("/api/report")
def api_report():
    return jsonify({"report": build_daily_report(), "stats": get_today_stats()})

SYSTEM_START = time.time()

SYSTEM_START = time.time()

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

# ============================================================
# FEATURE 1: SSE STREAMING - word-by-word AI responses
# ============================================================
import queue
import time as _time

@app.route("/command/stream", methods=["POST"])
def command_stream():
    """Server-Sent Events streaming endpoint for real-time AI responses."""
    data = request.get_json(silent=True) or {}
    original_text = str(data.get("command", "")).strip()
    if not original_text:
        return jsonify({"error": "No command"}), 400

    def generate():
        try:
            result = process_command(original_text)
            reply, image_data = strip_img_token(result)
            # Stream word by word for natural feel
            words = reply.split(" ")
            buffer = ""
            for i, word in enumerate(words):
                buffer += (" " if buffer else "") + word
                # Send every 2-4 words for smooth streaming
                if (i + 1) % 3 == 0 or i == len(words) - 1:
                    yield f"data: {json.dumps({'text': buffer, 'done': False, 'brain': LAST_BRAIN, 'image': image_data if i == len(words) - 1 else None})}\n\n"
                    _time.sleep(0.04)
            # Final done signal
            yield f"data: {json.dumps({'text': '', 'done': True, 'brain': LAST_BRAIN, 'image': image_data})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'text': f'Error: {str(e)[:100]}', 'done': True, 'error': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ============================================================
# FEATURE 2: PLUGIN SYSTEM
# ============================================================
PLUGIN_DIR = os.path.join(BASE_DIR, "plugins")
os.makedirs(PLUGIN_DIR, exist_ok=True)

# Auto-create plugin example if empty
PLUGIN_EXAMPLE = os.path.join(PLUGIN_DIR, "_example.py")
if not os.path.exists(PLUGIN_EXAMPLE):
    with open(PLUGIN_EXAMPLE, "w", encoding="utf-8") as pf:
        pf.write("name = 'example_plugin'\n")
        pf.write("description = 'Example plugin'\n")
        pf.write("keywords = ['hello world', 'hello plugin']\n")
        pf.write('def handle(text):\n')
        pf.write("    return 'Hello from plugin!'\n")


def load_plugins():
    """Load all Python plugins from plugins/ directory."""
    global loaded_plugins
    loaded_plugins = []
    if not os.path.exists(PLUGIN_DIR):
        return
    for fname in os.listdir(PLUGIN_DIR):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(fname[:-3], os.path.join(PLUGIN_DIR, fname))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plugin = {
                "name": getattr(mod, "name", fname[:-3]),
                "description": getattr(mod, "description", ""),
                "keywords": getattr(mod, "keywords", []),
                "handle": getattr(mod, "handle", None),
            }
            if plugin["handle"]:
                loaded_plugins.append(plugin)
                print(f"🔌 Plugin loaded: {plugin['name']}")
        except Exception as e:
            print(f"⚠️ Plugin error ({fname}): {e}")

load_plugins()

def try_plugins(text):
    """Try to match user text against loaded plugins."""
    text_lower = text.lower().strip()
    for p in loaded_plugins:
        for kw in p["keywords"]:
            if kw.lower() in text_lower:
                try:
                    result = p["handle"](text)
                    if result:
                        return result
                except Exception as e:
                    print(f"Plugin {p['name']} error: {e}")
    return None

@app.route("/api/plugins", methods=["GET"])
def api_plugins():
    """List loaded plugins."""
    plugins = [{"name": p["name"], "description": p["description"], "keywords": p["keywords"]} for p in loaded_plugins]
    return jsonify({"plugins": plugins, "count": len(plugins)})

@app.route("/api/plugins/reload", methods=["POST"])
def api_plugins_reload():
    """Reload all plugins."""
    load_plugins()
    return jsonify({"success": True, "count": len(loaded_plugins)})

# ============================================================
# FEATURE 3: CHAT HISTORY SEARCH
# ============================================================
@app.route("/api/search", methods=["GET"])
def api_search():
    """Search through conversation history."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": [], "query": ""})
    q_lower = q.lower()
    results = []
    for msg in conversation_history:
        text = msg.get("text", "")
        if q_lower in text.lower():
            results.append({
                "role": msg.get("role", ""),
                "text": text[:200],
                "full": text,
            })
    # Also search long-term memory
    mem = load_long_memory()
    for fact in mem.get("facts", []):
        if q_lower in fact.lower():
            results.append({"role": "memory", "text": fact, "full": fact})
    return jsonify({"results": results[:20], "query": q, "total": len(results)})

# ============================================================
# MEMORY TIMELINE API
# ============================================================
@app.route("/api/timeline", methods=["GET"])
def api_timeline():
    """Get conversation timeline with stats."""
    mem = load_long_memory()
    facts = mem.get("facts", [])
    
    # Group history by date
    timeline = {}
    for msg in conversation_history:
        ts = msg.get("timestamp", "")
        if not ts:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        date = ts.split(" ")[0] if " " in ts else ts[:10]
        if date not in timeline:
            timeline[date] = {"user": 0, "ai": 0, "messages": []}
        role = msg.get("role", "")
        if role == "user":
            timeline[date]["user"] += 1
        else:
            timeline[date]["ai"] += 1
        text = msg.get("text", "")
        if text:
            timeline[date]["messages"].append({
                "role": role,
                "text": text[:120],
                "time": ts.split(" ")[1] if " " in ts else ""
            })
    
    # Sort by date descending
    sorted_dates = sorted(timeline.keys(), reverse=True)[:14]
    
    return jsonify({
        "timeline": [{"date": d, **timeline[d]} for d in sorted_dates],
        "facts": facts[-20:],
        "total_messages": len(conversation_history),
        "total_facts": len(facts)
    })

# ============================================================
# LIVE CHAT API (for JARVIS mode)
# ============================================================
@app.route("/api/jarvis/chat", methods=["GET", "POST"])
def jarvis_chat():
    """Chat API for JARVIS mode."""
    if request.method == "GET":
        return jsonify({"history": conversation_history[-15:]})
    
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    
    try:
        result = process_command(text)
        reply, image_data = strip_img_token(result)
        add_to_memory("user", text)
        add_to_memory("model", reply)
        return jsonify({"reply": reply, "brain": LAST_BRAIN, "image": image_data})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)[:100]}"})

# ============================================================
# FEATURE 1: CODE GENERATION AI
# ============================================================
CODE_GEN_PROMPT = """You are a code expert. When user asks to write/generate code:
1. Write clean, working code
2. Add comments explaining key parts
3. Use proper indentation
4. Return ONLY the code in markdown code blocks
5. If asked to explain, explain step by step
Language: Use the language user requests (Python by default)
"""

@app.route("/api/codegen", methods=["POST"])
def api_codegen():
    """Generate code using AI."""
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt", "")).strip()
    language = str(data.get("language", "python")).strip()
    if not prompt:
        return jsonify({"error": "No prompt"}), 400
    
    messages = [
        {"role": "system", "content": CODE_GEN_PROMPT + f"Target language: {language}"},
        {"role": "user", "content": prompt}
    ]
    
    reply = _groq_complete(messages)
    if reply:
        # Log activity
        log_activity("code_gen", f"Generated code for: {prompt[:50]}")
        return jsonify({"code": reply, "language": language})
    return jsonify({"error": "Code generation failed"}), 500

@app.route("/api/codegen/run", methods=["POST"])
def api_codegen_run():
    """Run generated code safely."""
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip()
    language = str(data.get("language", "python")).strip()
    if not code:
        return jsonify({"error": "No code"}), 400
    
    if language.lower() == "python":
        result = run_python_safely(code)
    else:
        result = f"Only Python execution supported. Language: {language}"
    
    log_activity("code_run", f"Ran {language} code")
    return jsonify({"output": result})

# ============================================================
# FEATURE 2: ENCRYPTED STORAGE
# ============================================================
import hashlib
from cryptography.fernet import Fernet

ENCRYPT_KEY_FILE = os.path.join(DATA_DIR, ".encryption_key")
ENCRYPTED_DATA_FILE = os.path.join(DATA_DIR, "encrypted_vault.json")

def get_encryption_key():
    """Get or generate encryption key."""
    if os.path.exists(ENCRYPT_KEY_FILE):
        with open(ENCRYPT_KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(ENCRYPT_KEY_FILE, "wb") as f:
        f.write(key)
    return key

def encrypt_data(data: str) -> str:
    """Encrypt a string."""
    key = get_encryption_key()
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

def decrypt_data(encrypted: str) -> str:
    """Decrypt a string."""
    key = get_encryption_key()
    f = Fernet(key)
    return f.decrypt(encrypted.encode()).decode()

def load_vault():
    """Load encrypted vault."""
    if os.path.exists(ENCRYPTED_DATA_FILE):
        try:
            with open(ENCRYPTED_DATA_FILE, "r", encoding="utf-8") as f:
                encrypted = json.load(f)
            return {k: decrypt_data(v) for k, v in encrypted.items()}
        except: pass
    return {}

def save_vault(data: dict):
    """Save encrypted vault."""
    encrypted = {k: encrypt_data(v) for k, v in data.items()}
    with open(ENCRYPTED_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(encrypted, f, ensure_ascii=False, indent=2)

@app.route("/api/vault", methods=["GET", "POST", "DELETE"])
def api_vault():
    """Encrypted vault for sensitive data."""
    if request.method == "GET":
        vault = load_vault()
        # Return keys only, not values for security
        return jsonify({"keys": list(vault.keys()), "count": len(vault)})
    
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        key = data.get("key", "").strip()
        value = data.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "Key and value required"}), 400
        vault = load_vault()
        vault[key] = value
        save_vault(vault)
        log_activity("vault_store", f"Stored: {key}")
        return jsonify({"success": True, "keys": list(vault.keys())})
    
    if request.method == "DELETE":
        data = request.get_json(silent=True) or {}
        key = data.get("key", "").strip()
        vault = load_vault()
        if key in vault:
            del vault[key]
            save_vault(vault)
            log_activity("vault_delete", f"Deleted: {key}")
        return jsonify({"success": True, "keys": list(vault.keys())})

@app.route("/api/vault/get", methods=["POST"])
def api_vault_get():
    """Get encrypted value."""
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    vault = load_vault()
    if key in vault:
        log_activity("vault_access", f"Accessed: {key}")
        return jsonify({"value": vault[key]})
    return jsonify({"error": "Key not found"}), 404

# ============================================================
# FEATURE 3: ACTIVITY LOGGER
# ============================================================
ACTIVITY_LOG_FILE = os.path.join(DATA_DIR, "activity_log.json")

def log_activity(action: str, details: str = "", level: str = "info"):
    """Log user activity."""
    try:
        log = load_activity_log()
        entry = {
            "action": action,
            "details": details,
            "level": level,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        log.append(entry)
        # Keep last 500 entries
        log = log[-500:]
        with open(ACTIVITY_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Activity log error: {e}")

def load_activity_log():
    """Load activity log."""
    if os.path.exists(ACTIVITY_LOG_FILE):
        try:
            with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return []

@app.route("/api/activity", methods=["GET"])
def api_activity():
    """Get activity log."""
    log = load_activity_log()
    limit = int(request.args.get("limit", 50))
    return jsonify({"activities": log[-limit:], "total": len(log)})

@app.route("/api/activity/stats", methods=["GET"])
def api_activity_stats():
    """Get activity statistics."""
    log = load_activity_log()
    stats = {}
    for entry in log:
        action = entry.get("action", "unknown")
        stats[action] = stats.get(action, 0) + 1
    return jsonify({"stats": stats, "total": len(log)})

# ============================================================
# FEATURE 4: VOICE FINGERPRINT
# ============================================================
VOICEPRINT_FILE = os.path.join(DATA_DIR, "voiceprints.json")

def load_voiceprints():
    if os.path.exists(VOICEPRINT_FILE):
        try:
            with open(VOICEPRINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"users": {}}

def save_voiceprints(data):
    with open(VOICEPRINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_voice_features(audio_data: str) -> dict:
    """Extract simple voice features from audio base64."""
    # Simple feature extraction based on audio characteristics
    audio_bytes = base64.b64decode(audio_data)
    # Use length and basic characteristics as fingerprint
    features = {
        "length": len(audio_bytes),
        "hash": hashlib.md5(audio_bytes[:1000]).hexdigest()[:16],
    }
    return features

@app.route("/api/voiceprint/enroll", methods=["POST"])
def api_voiceprint_enroll():
    """Enroll a voice fingerprint for a user."""
    data = request.get_json(silent=True) or {}
    user_name = data.get("name", "").strip()
    audio = data.get("audio", "")
    if not user_name or not audio:
        return jsonify({"error": "Name and audio required"}), 400
    
    features = extract_voice_features(audio)
    voiceprints = load_voiceprints()
    if user_name not in voiceprints["users"]:
        voiceprints["users"][user_name] = {"samples": [], "created": datetime.datetime.now().isoformat()}
    voiceprints["users"][user_name]["samples"].append(features)
    voiceprints["users"][user_name]["samples"] = voiceprints["users"][user_name]["samples"][-10:]
    save_voiceprints(voiceprints)
    log_activity("voiceprint_enroll", f"Enrolled: {user_name}")
    return jsonify({"success": True, "user": user_name})

@app.route("/api/voiceprint/identify", methods=["POST"])
def api_voiceprint_identify():
    """Identify speaker from audio."""
    data = request.get_json(silent=True) or {}
    audio = data.get("audio", "")
    if not audio:
        return jsonify({"error": "Audio required"}), 400
    
    features = extract_voice_features(audio)
    voiceprints = load_voiceprints()
    
    best_match = "Unknown"
    best_score = 0
    for user, info in voiceprints.get("users", {}).items():
        for sample in info.get("samples", []):
            score = 0
            if features["hash"] == sample["hash"]:
                score = 100
            elif abs(features["length"] - sample["length"]) < 1000:
                score = 50
            if score > best_score:
                best_score = score
                best_match = user
    
    log_activity("voiceprint_identify", f"Identified: {best_match} (score: {best_score})")
    return jsonify({"user": best_match, "confidence": best_score})

@app.route("/api/voiceprint/list", methods=["GET"])
def api_voiceprint_list():
    """List enrolled voiceprints."""
    vp = load_voiceprints()
    users = []
    for name, info in vp.get("users", {}).items():
        users.append({"name": name, "samples": len(info.get("samples", [])), "created": info.get("created", "")})
    return jsonify({"users": users})

# ============================================================
# FEATURE 5: AI AUTO-LEARNS PATTERNS
# ============================================================
PATTERNS_FILE = os.path.join(DATA_DIR, "user_patterns.json")

def load_patterns():
    if os.path.exists(PATTERNS_FILE):
        try:
            with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "time_patterns": {},  # hour -> [commands]
        "command_frequency": {},  # command -> count
        "preferred_times": {},  # action -> best hour
        "learned_preferences": {},  # key -> value
    }

def save_patterns(data):
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def learn_pattern(command: str):
    """Learn from user command patterns."""
    patterns = load_patterns()
    hour = str(datetime.datetime.now().hour)
    
    # Track time patterns
    if hour not in patterns["time_patterns"]:
        patterns["time_patterns"][hour] = []
    cmd_clean = command.lower().strip()[:50]
    if cmd_clean not in patterns["time_patterns"][hour]:
        patterns["time_patterns"][hour].append(cmd_clean)
    patterns["time_patterns"][hour] = patterns["time_patterns"][hour][-20:]
    
    # Track command frequency
    patterns["command_frequency"][cmd_clean] = patterns["command_frequency"].get(cmd_clean, 0) + 1
    
    save_patterns(patterns)

def get_smart_suggestions() -> list:
    """Get smart suggestions based on learned patterns."""
    patterns = load_patterns()
    hour = str(datetime.datetime.now().hour)
    suggestions = []
    
    # Get commands常用 at this hour
    time_cmds = patterns["time_patterns"].get(hour, [])
    for cmd in time_cmds[:3]:
        suggestions.append({"text": cmd, "reason": f"常用 at {hour}:00"})
    
    # Get most frequent commands
    freq = sorted(patterns["command_frequency"].items(), key=lambda x: x[1], reverse=True)
    for cmd, count in freq[:3]:
        if cmd not in [s["text"] for s in suggestions]:
            suggestions.append({"text": cmd, "reason": f"Used {count} times"})
    
    return suggestions[:6]

@app.route("/api/patterns", methods=["GET"])
def api_patterns():
    """Get learned patterns."""
    patterns = load_patterns()
    suggestions = get_smart_suggestions()
    return jsonify({
        "patterns": patterns,
        "suggestions": suggestions,
        "total_commands": sum(patterns["command_frequency"].values()),
        "unique_commands": len(patterns["command_frequency"]),
    })

@app.route("/api/patterns/learn", methods=["POST"])
def api_patterns_learn():
    """Teach AI a new pattern."""
    data = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()
    if command:
        learn_pattern(command)
        return jsonify({"success": True})
    return jsonify({"error": "No command"}), 400

@app.route("/api/patterns/predict", methods=["GET"])
def api_patterns_predict():
    """Predict what user might want next."""
    suggestions = get_smart_suggestions()
    return jsonify({"predictions": suggestions})

# ============================================================
# Hook: Auto-learn from every command
# ============================================================
# This is integrated into process_command via try_plugins above

# ============================================================
# FEATURE 4: CUSTOM WAKE WORD UI ROUTES
# ============================================================
WAKEWORDS_FILE = os.path.join(DATA_DIR, "wakewords.json")

def load_wakewords():
    if os.path.exists(WAKEWORDS_FILE):
        try:
            with open(WAKEWORDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"words": ["Macha", "Vasanth"], "active": "Macha", "sensitivity": 0.7}

def save_wakewords(data):
    try:
        with open(WAKEWORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

@app.route("/api/wakewords", methods=["GET", "POST"])
def api_wakewords():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        ww = load_wakewords()
        if "words" in data:
            ww["words"] = data["words"]
        if "active" in data:
            ww["active"] = data["active"]
        if "sensitivity" in data:
            ww["sensitivity"] = float(data["sensitivity"])
        save_wakewords(ww)
        return jsonify({"success": True, "wakewords": ww})
    return jsonify(load_wakewords())

@app.route("/api/wakewords/add", methods=["POST"])
def api_wakewords_add():
    data = request.get_json(silent=True) or {}
    word = data.get("word", "").strip()
    if not word:
        return jsonify({"success": False, "error": "Empty word"})
    ww = load_wakewords()
    if word not in ww["words"]:
        ww["words"].append(word)
        save_wakewords(ww)
    return jsonify({"success": True, "wakewords": ww})

@app.route("/api/wakewords/remove", methods=["POST"])
def api_wakewords_remove():
    data = request.get_json(silent=True) or {}
    word = data.get("word", "").strip()
    ww = load_wakewords()
    if word in ww["words"] and len(ww["words"]) > 1:
        ww["words"].remove(word)
        if ww["active"] == word:
            ww["active"] = ww["words"][0] if ww["words"] else ""
        save_wakewords(ww)
    return jsonify({"success": True, "wakewords": ww})

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

@app.route("/stt", methods=["POST"])
def speech_to_text():
    """Offline Speech-to-Text using Whisper — unlimited, free."""
    if not WHISPER_READY or whisper_model is None:
        return jsonify({"success": False, "error": "Whisper not available"}), 503
    try:
        # Accept audio file upload or base64 data
        data = request.get_json(silent=True) or {}
        audio_data = data.get("audio", "")
        if not audio_data:
            # Try file upload
            if 'audio' in request.files:
                audio_file = request.files['audio']
                audio_data = base64.b64encode(audio_file.read()).decode()
        if not audio_data:
            return jsonify({"success": False, "error": "No audio data"}), 400
        # Decode and save temp file
        audio_bytes = base64.b64decode(audio_data)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        # Transcribe with Whisper
        result = whisper_model.transcribe(tmp_path, language='ta')
        os.unlink(tmp_path)
        text = result.get('text', '').strip()
        if text:
            print(f"🎙️ Whisper STT: {text[:80]}")
            return jsonify({"success": True, "text": text})
        return jsonify({"success": False, "error": "No speech detected"})
    except Exception as e:
        print(f"❌ STT error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/stt/status")
def stt_status():
    return jsonify({"whisper_ready": WHISPER_READY, "piper_ready": PIPER_READY})

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
    print(f"🎤 Voice profile: {prof['label']}")
    return jsonify({"success": True, "name": prof["label"]})

@app.route("/voice/on", methods=["POST"])
def voice_on():
    global VOICE_ENABLED
    VOICE_ENABLED = True
    print("🔊 Voice ON")
    return jsonify({"success": True})

@app.route("/voice/off", methods=["POST"])
def voice_off():
    global VOICE_ENABLED
    VOICE_ENABLED = False
    print("🔇 Voice OFF")
    return jsonify({"success": True})

@app.route("/voice/stop", methods=["POST"])
def voice_stop():
    try:
        ctypes.windll.winmm.mciSendStringW('stop vasanth_audio', None, 0, 0)
        ctypes.windll.winmm.mciSendStringW('close vasanth_audio', None, 0, 0)
        print("⏹️ Voice stopped (PC speaker)")
    except Exception as e:
        print(f"Voice stop error: {e}")
    return jsonify({"success": True})

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

@app.route("/api/stats")
def api_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        bat = psutil.sensors_battery()
        return jsonify({
            "cpu": cpu, "ram_pct": ram.percent,
            "ram_used": round(ram.used/1024**3,1), "ram_total": round(ram.total/1024**3,1),
            "disk_pct": round(disk.percent,1),
            "net_down": round(net.bytes_recv/1024**2,1), "net_up": round(net.bytes_sent/1024**2,1),
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
    except Exception:
        return jsonify({"temp": None, "hum": None, "wind": None, "rain": None})

@app.route("/api/theme", methods=["POST"])
def api_theme():
    data = request.get_json(silent=True) or {}
    desc = str(data.get("desc", "")).strip()
    if not desc:
        return jsonify({"success": False, "error": "no description"}), 400
    prompt = f"""You are a UI theme designer. Given a mood/description, return ONLY valid JSON with these exact keys, each a hex color:
{{"bg":"#...","card":"#...","line":"#...","pink":"#...","violet":"#...","pink2":"#...","blue":"#...","txt":"#...","mut":"#...","glass":"#..."}}
Rules: bg=very dark bg, card=dark panel, line=subtle border, pink/violet/pink2=vibrant accents, blue=secondary accent, txt=light text, mut=muted text, glass=light translucent.
Description: {desc}"""
    messages = [{"role":"system","content":"Return ONLY valid JSON."},{"role":"user","content":prompt}]
    reply = _groq_complete(messages)
    if not reply:
        return jsonify({"success": False, "error": "AI unavailable"}), 503
    m = re.search(r'\{[^}]+\}', reply)
    if not m:
        return jsonify({"success": False, "error": "bad JSON"}), 500
    try:
        colors = json.loads(m.group(0))
    except Exception:
        return jsonify({"success": False, "error": "bad JSON"}), 500
    return jsonify({"success": True, "colors": colors, "name": desc})

JARVIS_HTML = r"""
<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>VASANTH AI — QUANTUM 3D</title>
<link rel="icon" href="/logo.png" type="image/png">
<style>
:root{--cy:#7dd3fc;--pu:#c084fc;--pu2:#a855f7;--bg:#03040c;--panel:rgba(10,12,30,.66);--line:rgba(125,211,252,.22);--txt:#e8f6ff;--mut:#8fa8c9;--grn:#4ade80;}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent;}
body{background:radial-gradient(1000px 500px at 50% -10%,rgba(168,85,247,.12),transparent),radial-gradient(800px 400px at 90% 110%,rgba(56,189,248,.08),transparent),var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,Arial,"Noto Sans Tamil",sans-serif;min-height:100vh;}
.top{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line);background:rgba(3,4,12,.92);position:sticky;top:0;z-index:30;backdrop-filter:blur(12px);}
.tlogo{display:flex;align-items:center;gap:10px;min-width:0;}
.tlogo img{width:38px;height:38px;border-radius:50%;border:2px solid var(--pu);box-shadow:0 0 16px rgba(192,132,252,.6);flex:0 0 auto;}
.tlogo h1{font-size:15px;letter-spacing:3px;text-shadow:0 0 20px rgba(192,132,252,.8);white-space:nowrap;}
.tlogo small{display:block;font-size:7px;color:var(--mut);letter-spacing:2px;}
.tright{display:flex;gap:8px;align-items:center;}
.tclock{text-align:center;margin:0 auto;}
.tclock b{font-size:15px;letter-spacing:1px;}
.tclock small{display:block;font-size:9px;color:var(--mut);}
.tchips{display:flex;gap:8px;}
.tchip{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:5px 12px;font-size:8px;color:var(--mut);letter-spacing:1px;text-align:center;}
.tchip b{display:block;font-size:11px;color:var(--grn);letter-spacing:1px;}
.icobtn{width:36px;height:36px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--cy);font-size:14px;cursor:pointer;flex:0 0 auto;}
.wrap{display:grid;grid-template-columns:260px 1fr 290px;gap:12px;padding:12px;max-width:1600px;margin:0 auto;align-items:start;}
.col{display:flex;flex-direction:column;gap:12px;}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;backdrop-filter:blur(8px);}
.panel h3{font-size:9px;letter-spacing:2px;color:var(--cy);margin-bottom:10px;}
.ring{width:64px;height:64px;border-radius:50%;background:conic-gradient(var(--pu) var(--p,0%),rgba(192,132,252,.12) 0);display:grid;place-items:center;position:relative;flex:0 0 auto;}
.ring::before{content:"";position:absolute;inset:6px;border-radius:50%;background:#0a0c1e;}
.ring span{position:relative;font-size:12px;color:var(--pu);font-weight:700;}
.bar{margin:7px 0;}
.bar small{font-size:9px;color:var(--mut);display:flex;justify-content:space-between;}
.bar .tr{height:4px;border-radius:2px;background:rgba(192,132,252,.12);margin-top:3px;}
.bar .fl{height:4px;border-radius:2px;background:linear-gradient(90deg,var(--cy),var(--pu));box-shadow:0 0 8px rgba(192,132,252,.6);}
.row{display:flex;justify-content:space-between;font-size:10px;color:var(--mut);padding:4px 0;border-bottom:1px dashed rgba(125,211,252,.12);}
.row b{color:var(--txt);}
.center{display:flex;flex-direction:column;align-items:center;padding:4px 0;}
.ctitle{text-align:center;}
.ctitle h2{font-size:22px;letter-spacing:6px;text-shadow:0 0 30px rgba(192,132,252,.7);}
.ctitle small{font-size:8px;letter-spacing:3px;color:var(--mut);}
.ctitle .on{display:inline-block;margin-top:4px;font-size:9px;color:var(--grn);letter-spacing:2px;}
.stage{position:relative;width:100%;max-width:560px;height:400px;display:grid;place-items:center;overflow:hidden;border-radius:20px;}
#holo3d{position:absolute;inset:0;width:100%;height:100%;z-index:1;}
.stars{position:absolute;inset:0;pointer-events:none;z-index:0;}
.stars i{position:absolute;background:#e0f2fe;border-radius:50%;opacity:.7;animation:tw 3s infinite;}
@keyframes tw{50%{opacity:.1}}
.chiprow{position:absolute;top:10px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:3;padding:0 8px;}
.fchip{border:1px solid var(--line);background:rgba(10,12,30,.78);backdrop-filter:blur(8px);border-radius:12px;padding:7px 12px;font-size:10px;color:var(--txt);box-shadow:0 0 18px rgba(125,211,252,.12);animation:floaty 5s ease-in-out infinite;}
.fchip small{display:block;color:var(--mut);font-size:8px;}
.fchip.b{position:absolute;left:50%;transform:translateX(-50%);bottom:8px;animation-delay:2s;white-space:nowrap;}
@keyframes floaty{50%{margin-top:-6px}}
.bub{position:absolute;max-width:160px;background:rgba(10,12,30,.8);border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-size:10px;line-height:1.5;z-index:3;}
.bub.l{left:3%;bottom:18%;}
.bub.r{right:3%;bottom:24%;color:var(--cy);}
.dock{display:grid;grid-template-columns:repeat(8,54px);gap:8px;justify-content:center;margin-top:12px;}
.dbtn{width:54px;height:54px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--txt);font-size:17px;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;}
.dbtn small{font-size:7px;color:var(--mut);}
.cores{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:12px;}
.core{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:8px 12px;display:flex;align-items:center;gap:8px;font-size:8px;color:var(--mut);letter-spacing:1px;}
.core i{width:22px;height:22px;border-radius:50%;border:1px solid var(--pu);display:grid;place-items:center;font-size:10px;color:var(--pu);font-style:normal;}
.core b{display:block;color:var(--grn);font-size:7px;}
.cmdbar{display:flex;gap:8px;margin-top:14px;width:100%;max-width:620px;padding:0 10px;}
.cmdbar input{flex:1;min-width:0;background:rgba(3,4,12,.85);border:1px solid var(--line);border-radius:999px;color:var(--txt);padding:12px 16px;font-size:12px;outline:none;}
.cmdbar button{width:44px;height:44px;border-radius:50%;border:none;background:linear-gradient(135deg,var(--cy),var(--pu2));color:#012;font-size:15px;cursor:pointer;flex:0 0 auto;}
.act{display:flex;gap:8px;align-items:center;font-size:10px;color:var(--mut);padding:6px 0;border-bottom:1px dashed rgba(125,211,252,.12);}
.act i{font-style:normal;}
.tgl{display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--mut);padding:5px 0;}
.tgl b{color:var(--txt);font-size:9px;cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:2px 8px;}
.qact{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
.qa{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:8px;font-size:9px;color:var(--mut);cursor:pointer;display:flex;gap:6px;align-items:center;}
.foot{display:flex;justify-content:space-between;gap:10px;padding:8px 16px;border-top:1px solid var(--line);font-size:8px;letter-spacing:2px;color:var(--mut);background:rgba(3,4,12,.9);flex-wrap:wrap;}
.foot b{color:var(--pu);}
.wave{display:flex;gap:2px;height:20px;align-items:center;}
.wave i{width:2px;height:16px;background:var(--pu);border-radius:1px;transform:scaleY(.3);}
body.speaking .wave i{animation:wv .8s infinite;}
.wave i:nth-child(2){animation-delay:.1s}.wave i:nth-child(3){animation-delay:.2s}.wave i:nth-child(4){animation-delay:.3s}.wave i:nth-child(5){animation-delay:.4s}.wave i:nth-child(6){animation-delay:.5s}
@keyframes wv{0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1)}}
@media(max-width:1100px){.wrap{grid-template-columns:1fr 1fr;}.center{grid-column:1/-1;order:-1;}}
@media(max-width:700px){
.wrap{grid-template-columns:1fr;gap:10px;padding:10px;}
.tclock,.tchips{display:none;}
.top{padding:8px 10px;}
.tlogo img{width:34px;height:34px;}
.tlogo h1{font-size:13px;letter-spacing:2px;}
.ctitle h2{font-size:16px;letter-spacing:4px;}
.stage{height:340px;}
.bub{display:none;}
.fchip{padding:6px 10px;font-size:9px;}
.dock{grid-template-columns:repeat(4,1fr);width:100%;padding:0 10px;}
.dbtn{width:100%;height:56px;}
.cmdbar{position:sticky;bottom:8px;z-index:6;max-width:100%;}
.panel{padding:10px;}
.cores{gap:6px;}
.core{padding:6px 10px;}
}

/* === INTERACTIVE DOCK BUTTONS === */
.dock{display:grid;grid-template-columns:repeat(8,60px);gap:10px;justify-content:center;margin-top:14px;}
.dbtn{width:60px;height:60px;border-radius:16px;border:2px solid var(--line);background:var(--panel);color:var(--txt);font-size:20px;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;transition:all .25s cubic-bezier(.2,.9,.3,1.2);position:relative;overflow:hidden;}
.dbtn::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(125,211,252,.15),rgba(192,132,252,.1));opacity:0;transition:opacity .25s;}
.dbtn:hover::before{opacity:1;}
.dbtn:hover{transform:translateY(-4px) scale(1.08);border-color:rgba(125,211,252,.5);box-shadow:0 8px 24px rgba(125,211,252,.2),0 0 40px rgba(125,211,252,.1);}
.dbtn:active{transform:translateY(-1px) scale(1.02);}
.dbtn small{font-size:8px;color:var(--mut);font-weight:600;letter-spacing:.5px;}
.dbtn.active{border-color:var(--grn);box-shadow:0 0 20px rgba(74,222,128,.3);}
.dbtn.active::after{content:"";position:absolute;top:4px;right:4px;width:8px;height:8px;border-radius:50%;background:var(--grn);box-shadow:0 0 8px var(--grn);}

/* === VOICE WAVEFORM VISUALIZER === */
.waveform-container{position:absolute;bottom:80px;left:50%;transform:translateX(-50%);z-index:5;display:flex;align-items:flex-end;gap:3px;height:50px;padding:8px 16px;background:rgba(10,12,30,.8);border:1px solid var(--line);border-radius:14px;backdrop-filter:blur(10px);opacity:0;transition:all .3s ease;}
.waveform-container.active{opacity:1;}
.waveform-bar{width:4px;background:linear-gradient(180deg,var(--cy),var(--pu));border-radius:2px;transition:height .1s ease;min-height:4px;}
body.speaking .waveform-bar{animation:waveBar .6s infinite ease-in-out;}
.waveform-bar:nth-child(1){animation-delay:0s}.waveform-bar:nth-child(2){animation-delay:.05s}
.waveform-bar:nth-child(3){animation-delay:.1s}.waveform-bar:nth-child(4){animation-delay:.15s}
.waveform-bar:nth-child(5){animation-delay:.2s}.waveform-bar:nth-child(6){animation-delay:.25s}
.waveform-bar:nth-child(7){animation-delay:.3s}.waveform-bar:nth-child(8){animation-delay:.35s}
.waveform-bar:nth-child(9){animation-delay:.4s}.waveform-bar:nth-child(10){animation-delay:.45s}
.waveform-bar:nth-child(11){animation-delay:.5s}.waveform-bar:nth-child(12){animation-delay:.55s}
@keyframes waveBar{0%,100%{height:8px}50%{height:40px}}
.waveform-label{position:absolute;bottom:-20px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--cy);letter-spacing:1px;white-space:nowrap;}

/* === NOTIFICATION SYSTEM === */
.notif-container{position:fixed;top:20px;right:20px;z-index:1000;display:flex;flex-direction:column;gap:8px;max-width:320px;}
.notif{padding:12px 16px;background:rgba(10,12,30,.9);border:1px solid var(--line);border-radius:12px;backdrop-filter:blur(12px);display:flex;align-items:center;gap:10px;font-size:11px;color:var(--txt);animation:notifIn .3s cubic-bezier(.2,.9,.3,1.2);box-shadow:0 4px 20px rgba(0,0,0,.3);transition:all .3s;cursor:pointer;}
.notif:hover{transform:translateX(-4px);}
.notif.success{border-color:var(--grn);}.notif.success .notif-icon{color:var(--grn);}
.notif.info{border-color:var(--cy);}.notif.info .notif-icon{color:var(--cy);}
.notif.warn{border-color:#fbbf24;}.notif.warn .notif-icon{color:#fbbf24;}
.notif.error{border-color:#f87171;}.notif.error .notif-icon{color:#f87171;}
.notif-icon{font-size:16px;flex:0 0 auto;}
.notif-text{flex:1;line-height:1.4;}
.notif-close{cursor:pointer;opacity:.5;font-size:14px;transition:opacity .2s;}
.notif-close:hover{opacity:1;}
@keyframes notifIn{from{opacity:0;transform:translateX(40px) scale(.95)}to{opacity:1;transform:translateX(0) scale(1)}}
@keyframes notifOut{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(40px)}}

/* === SYSTEM ALERTS PANEL === */
.alerts-panel{position:relative;}
.alerts-panel .alert-badge{position:absolute;top:-4px;right:-4px;width:18px;height:18px;border-radius:50%;background:#f87171;color:#fff;font-size:9px;font-weight:700;display:grid;place-items:center;box-shadow:0 0 10px rgba(248,113,113,.5);animation:alertPulse 2s infinite;}
@keyframes alertPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
.alert-item{display:flex;gap:8px;align-items:flex-start;padding:8px 0;border-bottom:1px dashed rgba(125,211,252,.1);font-size:10px;}
.alert-item:last-child{border-bottom:none;}
.alert-dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;margin-top:3px;}
.alert-dot.critical{background:#f87171;box-shadow:0 0 8px rgba(248,113,113,.5);}
.alert-dot.warning{background:#fbbf24;box-shadow:0 0 8px rgba(251,191,36,.5);}
.alert-dot.info{background:var(--cy);box-shadow:0 0 8px rgba(125,211,252,.5);}
.alert-text{flex:1;color:var(--mut);line-height:1.4;}
.alert-time{font-size:8px;color:var(--mut);opacity:.6;white-space:nowrap;}

/* === QUICK COMMAND GRID === */
.cmd-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px;}
.cmd-tile{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:10px 8px;text-align:center;cursor:pointer;transition:all .25s cubic-bezier(.2,.9,.3,1.2);position:relative;overflow:hidden;}
.cmd-tile::before{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(125,211,252,.1),rgba(192,132,252,.06));opacity:0;transition:opacity .25s;}
.cmd-tile:hover::before{opacity:1;}

/* PARTICLE EXPLOSION EFFECTS */
.explosion-flash {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(0,255,200,0.8) 0%, rgba(255,45,149,0.4) 50%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
    z-index: 9998;
    animation: flashPulse 0.6s ease-out forwards;
}
@keyframes flashPulse {
    0% { transform: translate(-50%, -50%) scale(0.3); opacity: 1; }
    100% { transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
}
.sound-wave {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100px;
    height: 100px;
    border: 3px solid rgba(0,255,200,0.6);
    border-radius: 50%;
    pointer-events: none;
    z-index: 9997;
    animation: waveExpand 0.8s ease-out forwards;
}
@keyframes waveExpand {
    0% { transform: translate(-50%, -50%) scale(0.5); opacity: 1; border-width: 4px; }
    100% { transform: translate(-50%, -50%) scale(3); opacity: 0; border-width: 1px; }
}
.cmd-tile:hover{transform:translateY(-2px);border-color:rgba(125,211,252,.4);box-shadow:0 4px 16px rgba(125,211,252,.15);}
.cmd-tile:active{transform:scale(.95);}
.cmd-tile .cmd-icon{font-size:18px;margin-bottom:4px;}
.cmd-tile .cmd-name{font-size:8px;color:var(--mut);letter-spacing:.5px;font-weight:600;}


/* === MEMORY TIMELINE === */
.timeline-container{max-height:200px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(125,211,252,.2) transparent;}
.timeline-container::-webkit-scrollbar{width:4px;}
.timeline-container::-webkit-scrollbar-thumb{background:rgba(125,211,252,.2);border-radius:4px;}
.timeline-item{display:flex;gap:10px;padding:8px 0;border-left:2px solid var(--line);margin-left:8px;padding-left:12px;position:relative;}
.timeline-item::before{content:"";position:absolute;left:-5px;top:12px;width:8px;height:8px;border-radius:50%;background:var(--cy);box-shadow:0 0 8px rgba(125,211,252,.4);}
.timeline-item.memory::before{background:var(--pu);box-shadow:0 0 8px rgba(192,132,252,.4);}
.timeline-date{font-size:9px;color:var(--cy);font-weight:700;letter-spacing:1px;min-width:60px;}
.timeline-content{flex:1;}
.timeline-msg{font-size:10px;color:var(--mut);line-height:1.4;margin-bottom:2px;}
.timeline-msg b{color:var(--txt);font-size:9px;}
.timeline-stats{display:flex;gap:8px;margin-top:8px;}
.timeline-stat{padding:4px 10px;border-radius:8px;background:rgba(125,211,252,.08);border:1px solid rgba(125,211,252,.15);font-size:8px;color:var(--mut);}
.timeline-stat b{color:var(--cy);font-size:10px;}
.fact-tag{display:inline-block;padding:3px 8px;border-radius:6px;background:rgba(192,132,252,.08);border:1px solid rgba(192,132,252,.15);font-size:9px;color:var(--pu);margin:2px;cursor:pointer;transition:all .2s;}
.fact-tag:hover{background:rgba(192,132,252,.15);transform:scale(1.05);}

/* === LIVE CHAT IN JARVIS === */
.chat-panel{display:flex;flex-direction:column;height:100%;}
.chat-messages{flex:1;overflow-y:auto;padding:8px;scrollbar-width:thin;scrollbar-color:rgba(125,211,252,.2) transparent;min-height:150px;max-height:300px;}
.chat-messages::-webkit-scrollbar{width:4px;}
.chat-messages::-webkit-scrollbar-thumb{background:rgba(125,211,252,.2);border-radius:4px;}
.chat-msg{display:flex;gap:8px;margin:6px 0;animation:chatMsgIn .3s ease;}
.chat-msg.user{flex-direction:row-reverse;}
.chat-msg .chat-avatar{width:24px;height:24px;border-radius:8px;display:grid;place-items:center;font-size:11px;flex:0 0 auto;}
.chat-msg .chat-avatar.ai{background:linear-gradient(135deg,var(--cy),var(--pu));}
.chat-msg .chat-avatar.user{background:linear-gradient(135deg,#be185d,var(--pu2));}
.chat-msg .chat-bubble{max-width:80%;padding:8px 12px;border-radius:12px;font-size:10px;line-height:1.5;}
.chat-msg.user .chat-bubble{background:linear-gradient(135deg,rgba(192,132,252,.85),rgba(56,189,248,.85));color:#fff;border-bottom-right-radius:4px;}
.chat-msg.ai .chat-bubble{background:rgba(10,16,36,.6);border:1px solid rgba(125,211,252,.2);border-bottom-left-radius:4px;}
.chat-input-row{display:flex;gap:6px;padding:8px;border-top:1px solid var(--line);}
.chat-input{flex:1;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(3,4,12,.8);color:var(--txt);font-size:11px;outline:none;}
.chat-input:focus{border-color:rgba(125,211,252,.5);box-shadow:0 0 15px rgba(125,211,252,.15);}
.chat-send{width:32px;height:32px;border-radius:50%;border:none;background:linear-gradient(135deg,var(--cy),var(--pu2));color:#012;font-size:13px;cursor:pointer;}
.chat-typing{display:flex;gap:4px;align-items:center;padding:4px 8px;font-size:9px;color:var(--mut);}
.chat-typing span{width:5px;height:5px;border-radius:50%;background:var(--cy);animation:typingDot 1s infinite;}
.chat-typing span:nth-child(2){animation-delay:.2s}.chat-typing span:nth-child(3){animation-delay:.4s}
@keyframes typingDot{0%,60%,100%{opacity:.3}30%{opacity:1}}
@keyframes chatMsgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
/* === RESPONSIVE === */
@media(max-width:700px){
.wrap{grid-template-columns:1fr;gap:8px;padding:8px;}
.tclock,.tchips{display:none;}
.top{padding:6px 8px;flex-wrap:wrap;}
.tlogo img{width:30px;height:30px;}
.tlogo h1{font-size:12px;letter-spacing:2px;}
.tlogo small{font-size:6px;}
.icobtn{width:32px;height:32px;font-size:12px;border-radius:8px;}
.ctitle h2{font-size:14px;letter-spacing:3px;}
.ctitle small{font-size:7px;}
.stage{height:280px;border-radius:16px;}
.bub{display:none;}
.fchip{padding:5px 8px;font-size:8px;border-radius:8px;}
.fchip small{font-size:6px;}
.dock{grid-template-columns:repeat(4,1fr);gap:6px;padding:0 8px;}
.dbtn{width:100%;height:50px;border-radius:12px;font-size:16px;gap:2px;}
.dbtn small{font-size:7px;}
.cores{gap:4px;}
.core{padding:5px 8px;font-size:7px;gap:5px;}
.core i{width:18px;height:18px;font-size:9px;}
.cmdbar{position:fixed;bottom:0;left:0;right:0;z-index:50;padding:8px;background:rgba(3,4,12,.95);border-top:1px solid var(--line);backdrop-filter:blur(12px);}
.cmdbar input{padding:10px 14px;font-size:13px;}
.cmdbar button{width:40px;height:40px;font-size:13px;}
.panel{padding:8px;border-radius:10px;}
.panel h3{font-size:8px;margin-bottom:8px;}
.ring{width:50px;height:50px;}
.ring span{font-size:10px;}
.bar small{font-size:8px;}
.row{font-size:9px;padding:3px 0;}
.act{font-size:9px;padding:4px 0;}
.qact{grid-template-columns:1fr;gap:4px;}
.qa{padding:6px;font-size:8px;}
.tgl{font-size:9px;}
.foot{font-size:7px;padding:6px 10px;justify-content:center;text-align:center;}
.foot span{display:block;width:100%;}
.waveform-container{bottom:60px;}
.notif-container{top:10px;right:10px;max-width:calc(100% - 20px);}
.cmd-grid{grid-template-columns:repeat(2,1fr);}
}
@media(max-width:400px){
.top{padding:5px 6px;}
.tlogo img{width:26px;height:26px;}
.tlogo h1{font-size:11px;letter-spacing:1px;}
.icobtn{width:28px;height:28px;font-size:11px;}
.ctitle h2{font-size:12px;letter-spacing:2px;}
.stage{height:240px;}
.dock{grid-template-columns:repeat(4,1fr);gap:4px;}
.dbtn{height:44px;font-size:14px;}
.dbtn small{font-size:6px;}
.cmdbar input{padding:8px 12px;font-size:12px;}
.cmdbar button{width:36px;height:36px;}
}
@media(min-width:701px) and (max-width:1100px){
.wrap{grid-template-columns:1fr 1fr;}
.center{grid-column:1/-1;order:-1;}
.dock{grid-template-columns:repeat(6,56px);}
}
</style>
</head>
<body>
<div class="top">
<div class="tlogo"><img src="/logo.png"><div><h1>VASANTH AI</h1><small>QUANTUM CORE • 3D HOLOGRAM</small></div></div>
<div class="tclock"><b id="clock">--:--:--</b><small id="datestr">--</small></div>
<div class="tright">
<div class="tchips">
<div class="tchip">UPTIME<b id="uptime">--</b></div>
<div class="tchip">AI STATUS<b>ONLINE</b></div>
<div class="tchip">VOICE<b><span class="wave"><i></i><i></i><i></i><i></i><i></i><i></i></span> ACTIVE</b></div>
</div>
<button class="icobtn" onclick="startMic(false)" title="One-shot mic">🎤</button>
<button class="icobtn" id="vcBtn" onclick="toggleVoiceCmd()" title="Voice Command Mode">🎙️</button>
<button class="icobtn" onclick="location.reload()">⚙</button>
<button class="icobtn" onclick="location.href='/'">⏻</button>
</div>
</div>
<div class="wrap">
<div class="col">
<div class="panel">
<h3>SYSTEM OVERVIEW</h3>
<div style="display:flex;gap:12px;align-items:center">
<div class="ring" id="cpuRing"><span id="cpuTxt">0%</span></div>
<div style="flex:1">
<div class="bar"><small><span>RAM Usage</span><span id="ramPct">--%</span></small><div class="tr"><div class="fl" id="ramBar" style="width:0%"></div></div></div>
<div class="bar"><small><span>Disk Usage</span><span id="diskPct">--%</span></small><div class="tr"><div class="fl" id="diskBar" style="width:0%"></div></div></div>
<div class="bar"><small><span>Network</span><span id="netSp">--</span></small><div class="tr"><div class="fl" style="width:60%"></div></div></div>
</div>
</div>
</div>
<div class="panel">
<h3>LIVE INSIGHTS 📈</h3>
<canvas id="graph" width="240" height="90" style="width:100%;height:90px"></canvas>
<div style="display:flex;gap:12px;font-size:8px;color:var(--mut);margin-top:4px"><span style="color:#7dd3fc">— CPU</span><span style="color:#c084fc">— RAM</span></div>
</div>
<div class="panel">
<h3>AUTOMATION CENTER</h3>
<div class="tgl auto-tgl" data-key="morning_routine" onclick="toggleAuto(this)"><span>🌅 Morning Routine</span><b>ON</b></div>
<div class="tgl auto-tgl" data-key="work_mode" onclick="toggleAuto(this)"><span>💼 Work Mode (DND)</span><b>OFF</b></div>
<div class="tgl auto-tgl" data-key="night_routine" onclick="toggleAuto(this)"><span>🌙 Night Routine</span><b>OFF</b></div>
<div class="tgl auto-tgl" data-key="battery_saver" onclick="toggleAuto(this)"><span>🔋 Battery Saver</span><b>OFF</b></div>
<div class="tgl auto-tgl" data-key="auto_backup" onclick="toggleAuto(this)"><span>💾 Auto Backup</span><b>OFF</b></div>
</div>
<div class="panel">
<h3>NETWORK STATUS</h3>
<div class="row"><span>Download</span><b id="ndown">-- MB</b></div>
<div class="row"><span>Upload</span><b id="nup">-- MB</b></div>
<div class="row"><span>Status</span><b style="color:var(--grn)">CONNECTED</b></div>
</div>
<div class="panel">
<h3>🧠 AI MEMORY TIMELINE</h3>
<div class="timeline-stats" id="timelineStats"></div>
<div class="timeline-container" id="timelineContainer">
<div style="font-size:10px;color:var(--mut);text-align:center;padding:12px">Loading timeline...</div>
</div>
<div style="margin-top:8px">
<h3 style="font-size:9px;letter-spacing:2px;color:var(--cy);margin-bottom:6px">📦 STORED MEMORIES</h3>
<div id="factsContainer" style="max-height:100px;overflow-y:auto"></div>
</div>
</div>
<div class="panel">
<h3>WEATHER — CHENNAI</h3>
<div style="display:flex;gap:12px;align-items:center">
<div class="ring" id="wRing"><span id="wTemp">--</span></div>
<div><b id="wCond" style="font-size:12px">loading...</b><small style="color:var(--mut);font-size:9px">Chennai, India</small></div>
</div>
<div class="row"><span>Humidity</span><b id="wHum">--</b></div>
<div class="row"><span>Wind</span><b id="wWind">--</b></div>
<div class="row"><span>Rain</span><b id="wRain">--</b></div>
</div>
</div>
<div class="center">
<div class="ctitle"><h2>VASANTH AI</h2><small>YOUR PERSONAL AI ASSISTANT</small><br><span class="on">● ONLINE & ACTIVE</span></div>
<div class="stage" id="stage3d">
<canvas id="holo3d"></canvas>
<div class="stars" id="stars"></div>
<div class="rings"><i></i><i></i><i></i></div>
<div class="chiprow">
<div class="fchip" id="fWeather">☀ --°C<small>Humidity --%</small></div>
<div class="fchip" id="fStats">CPU --%<small>RAM --%</small></div>
</div>
<div class="chiprow">
<div class="fchip" id="fWeather">☀ --°C<small>Humidity --%</small></div>
<div class="fchip" id="fStats">CPU --%<small>RAM --%</small></div>
</div>
<div class="fchip b" id="fNet">⚡ Network: -- MB</div>
<div class="bub l">Hello Vasanth 👋<br>How can I help you?</div>
<div class="bub r">என்ன உதவி<br>செய்யலாம்?</div>
<div class="waveform-container" id="waveformVis">
<div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div>
<div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div>
<div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div>
<div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div>
<span class="waveform-label">🎙️ VOICE WAVEFORM</span>
</div>
</div>
<div class="dock">
<button class="dbtn" onclick="location.href='/'" title="Open Chat">💬<small>Chat</small></button>
<button class="dbtn" onclick="startMic(false)" title="Voice Command">🎤<small>Voice</small></button>
<button class="dbtn" onclick="cmd('open youtube')" title="Open YouTube">▶<small>YouTube</small></button>
<button class="dbtn" onclick="window.open('https://web.whatsapp.com')" title="WhatsApp">🟢<small>WhatsApp</small></button>
<button class="dbtn" onclick="cmd('open chrome')" title="Google Search">🔍<small>Google</small></button>
<button class="dbtn" onclick="window.open('https://mail.google.com')" title="Gmail">✉<small>Gmail</small></button>
<button class="dbtn" onclick="cmd('time')" title="Show Time">📅<small>Time</small></button>
<button class="dbtn" onclick="cmd('open notepad')" title="Notepad">📝<small>Notepad</small></button>
<button class="dbtn" onclick="cmd('screenshot')" title="Screenshot">📸<small>Screen</small></button>
<button class="dbtn" onclick="cmd('weather')" title="Weather">🌦️<small>Weather</small></button>
<button class="dbtn alerts-panel" onclick="toggleAlerts()" title="System Alerts">🔔<small>Alerts</small><span class="alert-badge" id="alertCount">3</span></button>
<button class="dbtn" onclick="showCmdGrid()" title="Quick Commands">⚡<small>Commands</small></button>
</div>
<div class="cores">
<div class="core"><i>🎤</i><div>SPEECH RECOGNITION<b>● Active</b></div></div>
<div class="core"><i>🧠</i><div>NLP ENGINE<b>● Active</b></div></div>
<div class="core"><i>🤖</i><div>AUTOMATION<b>● Active</b></div></div>
<div class="core"><i>🔮</i><div>QUANTUM 3D<b id="memCore">--</b></div></div>
</div>
<div class="cmdbar">
<input id="cin" placeholder="Type your command or ask anything..." onkeydown="if(event.key==='Enter')cmd()">
<button onclick="cmd()">➤</button>
<button onclick="startMic(false)">🎤</button>
</div>
</div>
<div class="col">
<div class="panel">
<h3>RECENT ACTIVITY</h3>
<div id="acts"><div class="act"><i>✅</i>System boot complete</div></div>
</div>
<div class="panel" style="display:flex;flex-direction:column">
<h3>💬 LIVE CHAT</h3>
<div class="chat-panel">
<div class="chat-messages" id="jarvisChat">
<div class="chat-msg ai"><div class="chat-avatar ai">🤖</div><div class="chat-bubble">Hey macha! Naan ready-ya irukken. Enna help pannanum? 🚀</div></div>
</div>
<div class="chat-input-row">
<input class="chat-input" id="jarvisChatInput" placeholder="Type or speak..." onkeydown="if(event.key==='Enter')sendJarvisChat()">
<button class="chat-send" onclick="sendJarvisChat()">➤</button>
<button class="chat-send" onclick="startJarvisMic()" style="background:linear-gradient(135deg,#16a34a,#059669)">🎤</button>
</div>
</div>
</div>
<div class="panel">
<h3>🎵 MUSIC PLAYER</h3>
<div id="npTitle" style="font-size:11px;color:var(--txt);border:1px solid var(--line);border-radius:10px;padding:8px;margin-bottom:8px">🎵 Nothing playing</div>
<div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin-bottom:8px">
<button class="qa" style="flex:1;justify-content:center" onclick="music('prev')">⏮</button>
<button class="qa" style="flex:1;justify-content:center" onclick="music('pause')">⏯</button>
<button class="qa" style="flex:1;justify-content:center" onclick="music('next')">⏭</button>
<button class="qa" style="flex:1;justify-content:center" onclick="music('stop')">⏹</button>
</div>
<div class="cmdbar" style="margin-top:0;max-width:100%;padding:0">
<input id="musIn" placeholder="Play AR Rahman..." style="padding:9px 12px;font-size:11px">
<button style="width:38px;height:38px" onclick="music('play')">▶</button>
</div>
</div>
<div class="panel">
<h3>📝 NOTES + TO-DO</h3>
<div id="notesBox"></div>
<div class="cmdbar" style="margin-top:8px;max-width:100%;padding:0">
<input id="noteIn" placeholder="Note / todo..." style="padding:9px 12px;font-size:11px">
<button style="width:38px;height:38px" onclick="addQuickNote()">➕</button>
</div>
</div>
<div class="panel">
<h3>VOICE INPUT</h3>
<div style="display:flex;gap:10px;align-items:center">
<button class="icobtn" style="width:44px;height:44px;border-radius:50%" onclick="startMic(false)">🎤</button>
<div class="wave"><i></i><i></i><i></i><i></i><i></i><i></i></div>
</div>
<div style="text-align:center;font-size:9px;color:var(--pu);margin-top:6px" id="micState">Listening...</div>
</div>
<div class="panel">
<h3>SYSTEM ALERTS</h3>
<div id="alertsList">
<div class="alert-item"><div class="alert-dot info"></div><div class="alert-text">System running normally</div><div class="alert-time">now</div></div>
<div class="alert-item"><div class="alert-dot warning"></div><div class="alert-text">Memory usage at 69%</div><div class="alert-time">2m ago</div></div>
<div class="alert-item"><div class="alert-dot info"></div><div class="alert-text">Auto-backup completed</div><div class="alert-time">5m ago</div></div>
</div>
</div>
<div class="panel">
<h3>QUICK COMMANDS</h3>
<div class="cmd-grid">
<div class="cmd-tile" onclick="cmd('lock')"><div class="cmd-icon">🔒</div><div class="cmd-name">Lock PC</div></div>
<div class="cmd-tile" onclick="cmd('screenshot')"><div class="cmd-icon">📸</div><div class="cmd-name">Screenshot</div></div>
<div class="cmd-tile" onclick="cmd('weather')"><div class="cmd-icon">🌦️</div><div class="cmd-name">Weather</div></div>
<div class="cmd-tile" onclick="cmd('play music')"><div class="cmd-icon">🎵</div><div class="cmd-name">Music</div></div>
<div class="cmd-tile" onclick="cmd('battery')"><div class="cmd-icon">🔋</div><div class="cmd-name">Battery</div></div>
<div class="cmd-tile" onclick="cmd('open camera')"><div class="cmd-icon">📷</div><div class="cmd-name">Camera</div></div>
</div>
</div>
</div>
</div>
<div class="foot"><span><b>VASANTH AI</b> — 100% TAMIL • தமிழ்</span><span><b>VOICE</b> | <b>AI</b> | <b>AUTOMATION</b> | <b>QUANTUM 3D</b></span></div>
<script>
function $(id){return document.getElementById(id);}
let voiceEnabled = localStorage.getItem("jarvisVoice") !== "off";
const cpuHist=[],ramHist=[];
function drawGraph(){const c=document.getElementById("graph");if(!c)return;const x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.strokeStyle="rgba(125,211,252,.15)";x.lineWidth=1;for(let i=1;i<4;i++){x.beginPath();x.moveTo(0,c.height*i/4);x.lineTo(c.width,c.height*i/4);x.stroke();}function ln(h,col){if(h.length<2)return;x.strokeStyle=col;x.lineWidth=2;x.beginPath();h.forEach((v,i)=>{const px=(i/59)*c.width;const py=c.height-(v/100)*c.height;i?x.lineTo(px,py):x.moveTo(px,py);});x.stroke();}ln(cpuHist,"#7dd3fc");ln(ramHist,"#c084fc");}
(function(){const s=$("stars");if(!s)return;for(let i=0;i<70;i++){const d=document.createElement("i");d.style.left=Math.random()*100+"%";d.style.top=Math.random()*100+"%";const sz=(Math.random()*2+1).toFixed(1);d.style.width=sz+"px";d.style.height=sz+"px";d.style.animationDelay=(Math.random()*4).toFixed(1)+"s";s.appendChild(d);}})();
// ===== 4D HOLOGRAM ENGINE — PREMIUM MOTION =====
(function(){
const cv=document.getElementById("holo3d");if(!cv)return;
const ctx=cv.getContext("2d");
let W=0,H=0;const DPR=Math.min(2,window.devicePixelRatio||1);
function rs(){W=cv.width=cv.offsetWidth*DPR;H=cv.height=cv.offsetHeight*DPR;}
rs();addEventListener("resize",rs);

const N=280,pts=[];
for(let i=0;i<N;i++){const phi=Math.acos(1-2*(i+0.5)/N);const th=Math.PI*(1+Math.sqrt(5))*i;
pts.push({x:Math.sin(phi)*Math.cos(th),y:Math.cos(phi),z:Math.sin(phi)*Math.sin(th),
hue:180+Math.random()*60,speed:0.3+Math.random()*0.4,phase:Math.random()*Math.PI*2});}

const edges=[];
for(let i=0;i<N;i++)for(let j=i+1;j<N;j++){
const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y,dz=pts[i].z-pts[j].z;
if(dx*dx+dy*dy+dz*dz<0.1)edges.push([i,j]);}

const rings=[
{r:1.4,tilt:0.5,sp:0.015,col:"0,255,200",w:1.5},
{r:1.7,tilt:-0.4,sp:-0.012,col:"255,45,149",w:1.2},
{r:2.0,tilt:0.3,sp:0.008,col:"100,200,255",w:1.0},
{r:2.3,tilt:-0.2,sp:-0.006,col:"168,85,247",w:0.8},
{r:2.6,tilt:0.15,sp:0.004,col:"0,200,255",w:0.6}
];

const beam=[];for(let i=0;i<80;i++)beam.push({
a:Math.random()*Math.PI*2,r:Math.random()*0.6,y:Math.random(),
s:0.003+Math.random()*0.007,hue:180+Math.random()*90});

const trails=[];for(let i=0;i<40;i++)trails.push({
x:Math.random()*2-1,y:Math.random()*2-1,z:Math.random()*2-1,
vx:(Math.random()-0.5)*0.02,vy:(Math.random()-0.5)*0.02,vz:(Math.random()-0.5)*0.02,
life:Math.random(),maxLife:0.5+Math.random()*0.5});

let ry=0,rx=0,mx=0,my=0,tmx=0,tmy=0,boost=0,t=0;
let clickPulse=0,autoRotate=true;

const stage=document.getElementById("stage3d")||cv.parentElement;
if(stage){
stage.addEventListener("mousemove",e=>{
const r=stage.getBoundingClientRect();
tmx=((e.clientX-r.left)/r.width*2-1)*0.8;
tmy=((e.clientY-r.top)/r.height*2-1)*0.5;
autoRotate=false;
});
stage.addEventListener("mouseleave",()=>{tmx=0;tmy=0;autoRotate=true;});
stage.addEventListener("click",()=>{clickPulse=1;});
}

function proj(x,y,z,cx,cy,s,RY,RX,RZ){
const cy1=Math.cos(RY),sy1=Math.sin(RY);
let x1=x*cy1+z*sy1,z1=-x*sy1+z*cy1;
const cx1=Math.cos(RX),sx1=Math.sin(RX);
let y1=y*cx1-z1*sx1,z2=y*sx1+z1*cx1;
const cz1=Math.cos(RZ),sz1=Math.sin(RZ);
let x2=x1*cz1-y1*sz1,y2=x1*sz1+y1*cz1;
const p=2.8/(2.8+z2);
return[cx+x2*s*p,cy+y2*s*p,p,z2];
}

function frame(){
t++;
const speaking=document.body.classList.contains("speaking");
if(speaking)boost=Math.min(1,boost+0.1);else boost=Math.max(0,boost-0.04);
clickPulse*=0.92;
if(autoRotate)ry+=0.008+boost*0.015;
rx+=0.003;
mx+=(tmx-mx)*0.04;my+=(tmy-my)*0.04;
const RY=ry+mx,RX=0.3+my,RZ=t*0.002;
const cx=W/2,cy=H*0.44,s=Math.min(W,H)*0.28;
ctx.clearRect(0,0,W,H);

const bgGrad=ctx.createRadialGradient(cx,cy,0,cx,cy,s*1.2);
bgGrad.addColorStop(0,"rgba(0,255,200,"+(0.03+boost*0.08+clickPulse*0.05).toFixed(3)+")");
bgGrad.addColorStop(0.5,"rgba(255,45,149,"+(0.02+boost*0.04).toFixed(3)+")");
bgGrad.addColorStop(1,"rgba(0,0,0,0)");
ctx.fillStyle=bgGrad;ctx.beginPath();ctx.arc(cx,cy,s*1.2,0,7);ctx.fill();

ctx.save();ctx.globalCompositeOperation="lighter";
for(const tr of trails){
tr.x+=tr.vx;tr.y+=tr.vy;tr.z+=tr.vz;
tr.life-=0.008;
if(tr.life<=0){tr.x=Math.random()*2-1;tr.y=Math.random()*2-1;tr.z=Math.random()*2-1;tr.life=tr.maxLife;}
const p=proj(tr.x,tr.y,tr.z,cx,cy,s*0.8,RY,RX,RZ);
const alpha=tr.life*0.4*(0.5+boost*0.5);
const hue=180+tr.x*60;
ctx.fillStyle="hsla("+hue+",80%,65%,"+alpha.toFixed(2)+")";
ctx.beginPath();ctx.arc(p[0],p[1],(1+boost*2)*DPR,0,7);ctx.fill();
}
ctx.restore();

ctx.save();ctx.globalCompositeOperation="lighter";
for(const b of beam){
b.y-=b.s*(1+boost*3);if(b.y<0){b.y=1;b.a=Math.random()*Math.PI*2;}
const rr=b.r*(0.3+b.y*0.8);
const px=cx+Math.cos(b.a+t*0.008)*rr*s;
const py=cy+(b.y-0.5)*s*2.4;
const alpha=((1-b.y)*0.4+boost*0.4+clickPulse*0.2);
ctx.fillStyle="hsla("+b.hue+",75%,65%,"+alpha.toFixed(2)+")";
ctx.fillRect(px,py,(1+boost)*DPR*1.5,(1+boost)*DPR*1.5);
}
ctx.restore();

for(const R of rings){
ctx.beginPath();
for(let i=0;i<=90;i++){
const a=i/90*Math.PI*2+t*R.sp;
const x=Math.cos(a)*R.r;
const z=Math.sin(a)*R.r;
const y=Math.sin(a+t*R.sp*2)*R.tilt*0.35;
const p=proj(x,y,z,cx,cy,s,RY,RX,RZ);
if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);
}
const glow=0.3+boost*0.4+clickPulse*0.3;
ctx.strokeStyle="rgba("+R.col+","+glow.toFixed(2)+")";
ctx.lineWidth=R.w*DPR;
ctx.shadowBlur=8*DPR;ctx.shadowColor="rgba("+R.col+",0.3)";
ctx.stroke();ctx.shadowBlur=0;
}

ctx.lineWidth=0.6*DPR;
for(const e of edges){
const a=proj(pts[e[0]].x,pts[e[0]].y,pts[e[0]].z,cx,cy,s,RY,RX,RZ);
const b=proj(pts[e[1]].x,pts[e[1]].y,pts[e[1]].z,cx,cy,s,RY,RX,RZ);
const avgZ=(a[3]+b[3])/2;
const depth=Math.max(0,Math.min(1,(2-avgZ)/2));
const hue=pts[e[0]].hue+depth*40;
const alpha=depth*(0.2+boost*0.3+clickPulse*0.2);
ctx.strokeStyle="hsla("+hue+",70%,65%,"+alpha.toFixed(2)+")";
ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
}

for(const pt of pts){
const wobble=Math.sin(t*0.02+pt.phase)*0.05*(1+boost);
const px=pt.x+wobble,py=pt.y+wobble*0.5,pz=pt.z+wobble*0.3;
const q=proj(px,py,pz,cx,cy,s,RY,RX,RZ);
const depth=Math.max(0.05,Math.min(1,(1-q[3])/2));
const size=(0.8+q[2]*0.6+boost*0.8+clickPulse*0.5)*DPR;
const alpha=depth*(0.6+boost*0.4);
ctx.fillStyle="hsla("+pt.hue+",75%,70%,"+alpha.toFixed(2)+")";
ctx.beginPath();ctx.arc(q[0],q[1],size,0,7);ctx.fill();
if(depth>0.6){
ctx.shadowBlur=6*DPR;ctx.shadowColor="hsla("+pt.hue+",80%,65%,0.3)";
ctx.fill();ctx.shadowBlur=0;
}
}

const coreSize=s*(0.15+boost*0.1+clickPulse*0.15);
const coreGrad=ctx.createRadialGradient(cx,cy,0,cx,cy,coreSize);
coreGrad.addColorStop(0,"rgba(255,255,255,"+(0.6+boost*0.3)+")");
coreGrad.addColorStop(0.3,"rgba(0,255,200,"+(0.3+boost*0.2)+")");
coreGrad.addColorStop(0.6,"rgba(255,45,149,"+(0.15+boost*0.1)+")");
coreGrad.addColorStop(1,"rgba(0,0,0,0)");
ctx.fillStyle=coreGrad;ctx.beginPath();ctx.arc(cx,cy,coreSize,0,7);ctx.fill();

for(let d=0;d<3;d++){
const dimR=s*(0.8+d*0.15);
const dimAngle=t*0.005*(d%2?1:-1)+d*Math.PI*2/3;
ctx.beginPath();
for(let i=0;i<=60;i++){
const a=i/60*Math.PI*2;
const x=Math.cos(a)*dimR*Math.cos(dimAngle);
const y=Math.sin(a)*dimR*0.3;
const z=Math.cos(a)*dimR*Math.sin(dimAngle);
const p=proj(x,y,z,cx,cy,s,RY,RX,RZ);
if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);
}
ctx.strokeStyle="rgba(0,255,200,"+(0.1+boost*0.15+clickPulse*0.1).toFixed(2)+")";
ctx.lineWidth=0.5*DPR;ctx.stroke();
}

requestAnimationFrame(frame);
}
frame();
})();


// ===== PARTICLE EXPLOSION ENGINE =====
(function(){
const cv=document.getElementById("particleExplosion");
if(!cv)return;
const ctx=cv.getContext("2d");
let W=0,H=0;
function rs(){W=cv.width=window.innerWidth;H=cv.height=window.innerHeight;}
rs();addEventListener("resize",rs);

const particles=[];

function createExplosion(x,y,count,color){
for(let i=0;i<count;i++){
const angle=Math.random()*Math.PI*2;
const speed=2+Math.random()*6;
particles.push({
x:x,y:y,
vx:Math.cos(angle)*speed,
vy:Math.sin(angle)*speed,
life:1,
decay:0.015+Math.random()*0.02,
size:2+Math.random()*4,
color:color||`hsl(${160+Math.random()*60},100%,${60+Math.random()*20}%)`
});
}
}

function animate(){
ctx.clearRect(0,0,W,H);
for(let i=particles.length-1;i>=0;i--){
const p=particles[i];
p.x+=p.vx;
p.y+=p.vy;
p.vy+=0.1;
p.life-=p.decay;
if(p.life<=0){particles.splice(i,1);continue;}
ctx.globalAlpha=p.life;
ctx.fillStyle=p.color;
ctx.beginPath();
ctx.arc(p.x,p.y,p.size*p.life,0,7);
ctx.fill();
ctx.globalAlpha=1;
}
requestAnimationFrame(animate);
}
animate();

// Expose to global
window.triggerExplosion=function(x,y,count,color){
createExplosion(x||W/2,y||H/2,count||40,color);
// Add flash effect
const flash=document.createElement("div");
flash.className="explosion-flash";
document.body.appendChild(flash);
setTimeout(()=>flash.remove(),700);
// Add wave effect
const wave=document.createElement("div");
wave.className="sound-wave";
document.body.appendChild(wave);
setTimeout(()=>wave.remove(),900);
};
})();

// ===== SOUND FEEDBACK ENGINE =====
(function(){
const AudioCtx=window.AudioContext||window.webkitAudioContext;
let audioCtx=null;

function initAudio(){
if(!audioCtx)audioCtx=new AudioCtx();
return audioCtx;
}

function playClick(freq,dur,vol){
try{
const ctx=initAudio();
const osc=ctx.createOscillator();
const gain=ctx.createGain();
osc.connect(gain);
gain.connect(ctx.destination);
osc.frequency.value=freq||800;
osc.type="sine";
gain.gain.setValueAtTime(vol||0.1,ctx.currentTime);
gain.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+(dur||0.1));
osc.start(ctx.currentTime);
osc.stop(ctx.currentTime+(dur||0.1));
}catch(e){}
}

function playSuccess(){
playClick(523,0.1,0.12);
setTimeout(()=>playClick(659,0.1,0.12),100);
setTimeout(()=>playClick(784,0.15,0.1),200);
}

function playCommand(){
playClick(440,0.08,0.15);
setTimeout(()=>playClick(880,0.12,0.1),80);
}

// Add click sounds to all dock buttons
document.addEventListener("click",function(e){
const tile=e.target.closest(".cmd-tile,.dock-btn,.act-btn");
if(tile){
playClick(600+Math.random()*400,0.08,0.08);
// Also trigger mini explosion
if(window.triggerExplosion){
const r=tile.getBoundingClientRect();
window.triggerExplosion(r.left+r.width/2,r.top+r.height/2,15);
}
}
});

// Export for use
window.playClick=playClick;
window.playSuccess=playSuccess;
window.playCommand=playCommand;
})();

// Touch support for mobile
document.addEventListener("touchstart",function(e){
const tile=e.target.closest(".cmd-tile,.dock-btn,.act-btn,.dbtn");
if(tile){
playClick(600+Math.random()*400,0.08,0.08);
if(window.triggerExplosion){
const r=tile.getBoundingClientRect();
window.triggerExplosion(r.left+r.width/2,r.top+r.height/2,12);
}
}
},{passive:true});


function toggleVoice(){voiceEnabled=!voiceEnabled;localStorage.setItem("jarvisVoice",voiceEnabled?"on":"off");document.title=voiceEnabled?"VASANTH AI — QUANTUM 🔊":"VASANTH AI — QUANTUM 🔇";}
function playTTS(text){if(!voiceEnabled||!text)return;fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:text})}).then(r=>r.blob()).then(b=>{if(!b.size)return;const u=URL.createObjectURL(b),a=new Audio(u);document.body.classList.add("speaking");const off=()=>{document.body.classList.remove("speaking");URL.revokeObjectURL(u);};a.onended=off;a.onerror=off;a.play().catch(off);}).catch(()=>{});}
setInterval(()=>{const d=new Date();const c=$("clock");if(c)c.textContent=d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});const ds=$("datestr");if(ds)ds.textContent=d.toLocaleDateString("en-IN",{weekday:"long",day:"2-digit",month:"long",year:"numeric"});},1000);
function fmtUp(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h>0?h+"h "+m+"m":m+"m "+(s%60)+"s";}
setInterval(async()=>{try{const r=await fetch("/api/stats");const d=await r.json();$("cpuRing").style.setProperty("--p",d.cpu+"%");$("cpuTxt").textContent=Math.round(d.cpu)+"%";$("ramPct").textContent=Math.round(d.ram_pct)+"%";$("ramBar").style.width=d.ram_pct+"%";$("diskPct").textContent=d.disk_pct+"%";$("diskBar").style.width=d.disk_pct+"%";$("netSp").textContent=d.net_down+" MB";$("ndown").textContent=d.net_down+" MB";$("nup").textContent=d.net_up+" MB";$("uptime").textContent=fmtUp(d.uptime);$("memCore").textContent="● "+d.messages+" Stored";$("fStats").innerHTML="CPU "+Math.round(d.cpu)+"%<small>RAM "+Math.round(d.ram_pct)+"%</small>";$("fNet").textContent="⚡ Network: "+d.net_down+" MB";cpuHist.push(d.cpu);ramHist.push(d.ram_pct);if(cpuHist.length>60)cpuHist.shift();if(ramHist.length>60)ramHist.shift();drawGraph();}catch(e){}},2000);
fetch("/api/weather").then(r=>r.json()).then(d=>{if(d.temp==null){$("wCond").textContent="No internet";return;}$("wTemp").textContent=d.temp+"°";$("wRing").style.setProperty("--p",Math.min(d.temp*2,100)+"%");$("wCond").textContent=d.temp>=30?"Hot & Humid":"Pleasant";$("wHum").textContent=d.hum+"%";$("wWind").textContent=d.wind+" km/h";$("wRain").textContent=d.rain+"%";$("fWeather").innerHTML="☀ "+d.temp+"°C<small>Humidity "+d.hum+"%</small>";$("smartW").innerHTML="🌤 <b>"+d.temp+"°C</b> | "+(d.temp>=30?"Partly Cloudy":"Pleasant")+"<br>Humidity: "+d.hum+"% • Wind: "+d.wind+" km/h<br>Rain: "+d.rain+"%";}).catch(()=>{$("wCond").textContent="Offline";});
fetch("/history").then(r=>r.json()).then(d=>{const box=$("acts");box.innerHTML="";(d.history||[]).slice(-5).reverse().forEach(h=>{const t=String(h.text||"");const ic=t.toLowerCase().includes("youtube")?"▶":t.toLowerCase().includes("screenshot")?"📸":h.role==="user"?"👤":"🤖";const div=document.createElement("div");div.className="act";div.innerHTML="<i>"+ic+"</i>"+t.replace(/[<>&]/g,"").slice(0,32);box.appendChild(div);});}).catch(()=>{});
function updMusic(m){const t=$("npTitle");if(t)t.innerHTML=(m.playing?"🎵 ":" ")+(m.title||"Nothing playing");}
setInterval(()=>{fetch("/api/music").then(r=>r.json()).then(updMusic).catch(()=>{});},3000);
function music(act){const q=($("musIn")||{}).value||"";fetch("/api/music",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:act,query:q})}).then(r=>r.json()).then(d=>{updMusic(d.music);}).catch(()=>{});}
function loadNotes(){fetch("/api/notes").then(r=>r.json()).then(d=>{const box=$("notesBox");if(!box)return;box.innerHTML="";(d.notes||[]).slice(-3).reverse().forEach(n=>{const div=document.createElement("div");div.className="act";div.innerHTML="<i>📝</i>"+String(n.text).replace(/[<>&]/g,"").slice(0,24);box.appendChild(div);});(d.todos||[]).map((t,idx)=>({t:t,idx:idx})).slice(-4).forEach(o=>{const div=document.createElement("div");div.className="act";div.style.cursor="pointer";div.innerHTML="<i>"+(o.t.done?"✅":"☐")+"</i>"+String(o.t.text).replace(/[<>&]/g,"").slice(0,22);div.onclick=function(){fetch("/api/notes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"toggle_todo",index:o.idx})}).then(loadNotes);};box.appendChild(div);});if(!(d.notes||[]).length&&!(d.todos||[]).length)box.innerHTML="<div class='act'><i>📝</i>No notes yet</div>";}).catch(()=>{});}
setInterval(loadNotes,5000);loadNotes();
function addQuickNote(){const v=($("noteIn")||{}).value.trim();if(!v)return;$("noteIn").value="";const act=v.toLowerCase().startsWith("todo")?"add_todo":"add_note";const txt=act==="add_todo"?v.replace(/^todo[: ]*/i,""):v;fetch("/api/notes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:act,text:txt})}).then(loadNotes);}
function toggleAuto(el){const k=el.getAttribute("data-key");const b=el.querySelector("b");const on=b.textContent==="ON";b.textContent=!on?"ON":"OFF";b.style.color=!on?"var(--grn)":"var(--mut)";fetch("/api/automation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,value:!on})});}
fetch("/api/automation").then(r=>r.json()).then(d=>{document.querySelectorAll(".auto-tgl").forEach(el=>{const k=el.getAttribute("data-key");const b=el.querySelector("b");b.textContent=d[k]?"ON":"OFF";b.style.color=d[k]?"var(--grn)":"var(--mut)";});}).catch(()=>{});
async function cmd(t){const q=t||$("cin").value.trim();if(!q)return;if(window.playCommand)window.playCommand();$("cin").value="";try{const r=await fetch("/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:q})});const d=await r.json();playTTS(String(d.reply||""));}catch(e){}}
function startMic(cont){
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!SR){const ms=$("micState");if(ms)ms.textContent="Chrome மட்டும் தான்";return;}
if(!window.isSecureContext){const ms=$("micState");if(ms)ms.textContent="localhost-ல மட்டும்";return;}
const r=new SR();r.lang="ta-IN";r.continuous=cont;r.interimResults=false;
const ms=$("micState");if(ms)ms.textContent="🎧 Listening...";
r.onresult=(e)=>{const t=e.results[e.results.length-1][0].transcript;if(window.triggerExplosion)window.triggerExplosion(window.innerWidth/2,window.innerHeight/2,60,"hsl(170,100%,65%)");if(window.playSuccess)window.playSuccess();cmd(t);};
r.onerror=(e)=>{const ms=$("micState");if(ms)ms.textContent="⚠️ "+e.error;};
r.onend=()=>{if(cont)startMic(true);else{const ms=$("micState");if(ms)ms.textContent="Listening...";}};
try{r.start();}catch(e){}
}
async function loadTimeline(){
    try{
        const r=await fetch("/api/timeline");
        const d=await r.json();
        
        // Stats
        const stats=document.getElementById("timelineStats");
        if(stats){
            stats.innerHTML='<div class="timeline-stat">Total: <b>'+d.total_messages+'</b></div>'+
            '<div class="timeline-stat">Memories: <b>'+d.total_facts+'</b></div>'+
            '<div class="timeline-stat">Days: <b>'+d.timeline.length+'</b></div>';
        }
        
        // Timeline
        const container=document.getElementById("timelineContainer");
        if(container && d.timeline.length){
            container.innerHTML=d.timeline.map(day=>{
                const msgs=day.messages.slice(0,3).map(m=>
                    '<div class="timeline-msg"><b>'+(m.role==="user"?"You":"AI")+'</b>: '+m.text.replace(/[<>]/g,"").slice(0,80)+'</div>'
                ).join("");
                return '<div class="timeline-item"><div class="timeline-date">'+day.date+'</div><div class="timeline-content">'+msgs+'</div></div>';
            }).join("");
        }
        
        // Facts
        const facts=document.getElementById("factsContainer");
        if(facts && d.facts.length){
            facts.innerHTML=d.facts.slice(-10).reverse().map(f=>
                '<span class="fact-tag">'+f.replace(/[<>]/g,"").slice(0,40)+'</span>'
            ).join("");
        }
    }catch(e){console.log("Timeline error:",e);}
}
loadTimeline();
setInterval(loadTimeline,30000);

// === LIVE CHAT IN JARVIS ===
async function sendJarvisChat(){
    const input=document.getElementById("jarvisChatInput");
    const chat=document.getElementById("jarvisChat");
    if(!input||!chat)return;
    const text=input.value.trim();
    if(!text)return;
    input.value="";
    
    // Add user message
    chat.innerHTML+='<div class="chat-msg user"><div class="chat-avatar user">👤</div><div class="chat-bubble">'+text.replace(/[<>]/g,"")+'</div></div>';
    chat.scrollTop=chat.scrollHeight;
    
    // Show typing
    const typing=document.createElement("div");
    typing.className="chat-msg ai";typing.id="chatTyping";
    typing.innerHTML='<div class="chat-avatar ai">🤖</div><div class="chat-bubble"><div class="chat-typing"><span></span><span></span><span></span> Thinking...</div></div>';
    chat.appendChild(typing);chat.scrollTop=chat.scrollHeight;
    
    try{
        const r=await fetch("/api/jarvis/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
        const d=await r.json();
        const t=document.getElementById("chatTyping");if(t)t.remove();
        chat.innerHTML+='<div class="chat-msg ai"><div class="chat-avatar ai">🤖</div><div class="chat-bubble">'+(d.reply||"Error").replace(/[<>]/g,"").replace(/\*\*(.*?)\*\*/g,"<b>$1</b")+'</div></div>';
        chat.scrollTop=chat.scrollHeight;
    }catch(e){
        const t=document.getElementById("chatTyping");if(t)t.remove();
        chat.innerHTML+='<div class="chat-msg ai"><div class="chat-avatar ai">🤖</div><div class="chat-bubble">Error: '+e.message+'</div></div>';
    }
}

function startJarvisMic(){
    const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
    if(!SR){notify("Chrome use pannu macha","warn");return;}
    const r=new SR();r.lang="ta-IN";r.continuous=false;r.interimResults=false;
    r.onresult=(e)=>{
        const text=e.results[0][0].transcript;
        document.getElementById("jarvisChatInput").value=text;
        sendJarvisChat();
    };
    r.onerror=()=>notify("Mic error","error");
    try{r.start();}catch(e){}
}
</script>

<!-- PARTICLE EXPLOSION CANVAS -->
<canvas id="particleExplosion" style="position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999;"></canvas>

</body>
</html>
"""

@app.route("/jarvis")
def jarvis_page():
    return render_template_string(JARVIS_HTML)

@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "Vasanth AI",
        "short_name": "Vasanth AI",
        "description": "AI assistant with genius brain + smart memory + SDXL gallery + music player",
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
    load_music()
    threading.Thread(target=reminder_checker_thread, daemon=True).start()
    threading.Thread(target=telegram_bot_thread, daemon=True).start()
    threading.Thread(target=proactive_thread, daemon=True).start()
    threading.Thread(target=automation_thread, daemon=True).start()
    print("\n" + "=" * 60)
    print("    VASANTH AI - ULTIMATE EDITION 🚀 (FREE & UNLIMITED)")
    print("=" * 60)
    print(f"Groq:     {'READY ✅' if GROQ_API_KEY else 'MISSING ❌'}")
    print(f"AWS:      {'READY ✅' if AWS_READY else 'Not configured'}")
    print(f"Ollama:   {'READY ✅ (' + str(len(OLLAMA_AVAILABLE_MODELS)) + ' models)' if OLLAMA_READY else 'Not running'}")
    print(f"Whisper:  {'🎙️ STT READY (offline)' if WHISPER_READY else 'Not installed'}")
    print(f"Piper:    {'🔊 TTS READY (offline)' if PIPER_READY else 'Not installed'}")
    print(f"Telegram: {'READY ✅' if (TELEGRAM_AVAILABLE and TELEGRAM_BOT_TOKEN) else 'Not configured'}")
    print(f"Gemini:   {'🥇 NATURAL VOICE READY' if GEMINI_API_KEY else 'NOT SET (fallback)'}")
    print(f"JARVIS:   🤖 /jarvis + AUTOMATION + MUSIC + LIVE GRAPHS")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, use_reloader=False)
