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
const CACHE = 'vasanth-ai-v26';
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

def _score_fact(fact, query):
    q = set(re.findall(r'[a-z0-9஀-௿]+', (query or "").lower()))
    f = set(re.findall(r'[a-z0-9஀-]+', fact.lower()))
    if not q: return 0
    return len(q & f)

def get_memory_context(query=""):
    mem = load_long_memory()
    facts = mem["facts"]
    if not facts: return ""
    if query:
        ranked = sorted(facts, key=lambda f: _score_fact(f, query), reverse=True)
        top = [f for f in ranked[:6] if _score_fact(f, query) > 0]
        recent = facts[-8:]
        chosen = list(dict.fromkeys(top + recent))
    else:
        chosen = facts[-12:]
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

def generate_tts(text):
    try:
        cleaned_text = clean_text_for_tts(text)
        if not cleaned_text or len(cleaned_text) < 3:
            return None, "No speakable text", "audio/mpeg"
        if len(cleaned_text) < 300:
            buf = google_tts(cleaned_text)
            if buf:
                print(f"⚡ Fast Google TTS ({len(cleaned_text)} chars)")
                return buf, None, "audio/mpeg"
        result = gemini_tts(cleaned_text)
        if result:
            buf, mime = result
            return buf, None, mime
        buf = google_tts(cleaned_text)
        if buf:
            return buf, None, "audio/mpeg"
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

    yt_link = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)[^\s]+)', original_text)
    if yt_link:
        reply = summarize_youtube(yt_link.group(1)); add_to_memory("user", original_text); add_to_memory("model", reply); return reply

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
:root{--bg:#0d0721;--card:rgba(28,14,58,.55);--line:rgba(232,121,249,.22);--pink:#e879f9;--violet:#8b5cf6;--pink2:#ec4899;--blue:#38bdf8;--txt:#f5f0ff;--mut:#a795c9;--glass:rgba(255,255,255,.05);}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,Arial,"Noto Sans Tamil",sans-serif;display:flex;justify-content:center;align-items:center;padding:20px;overflow-x:hidden;transition:background .5s;}
.aurora{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none;}
.aurora i{position:absolute;width:50vw;height:50vw;border-radius:50%;filter:blur(110px);opacity:.28;animation:float 16s ease-in-out infinite;}
.aurora i:nth-child(1){background:var(--pink);top:-15%;left:-12%;}
.aurora i:nth-child(2){background:var(--violet);bottom:-18%;right:-10%;animation-delay:-6s;}
.aurora i:nth-child(3){background:var(--pink2);top:35%;left:55%;animation-delay:-10s;}
.aurora i:nth-child(4){background:var(--blue);top:60%;left:-15%;animation-delay:-13s;opacity:.15;}
@keyframes float{0%,100%{transform:translate(0,0) scale(1);}50%{transform:translate(60px,-50px) scale(1.15);}}
#particles{position:fixed;inset:0;z-index:0;pointer-events:none;}
.app{position:relative;z-index:1;width:min(1150px,100%);height:min(920px,94vh);min-height:600px;background:var(--card);border:1px solid var(--line);border-radius:30px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 0 90px rgba(139,92,246,.25),0 40px 100px rgba(0,0,0,.65),inset 0 1px 0 rgba(255,255,255,.08);backdrop-filter:blur(30px);}
.header{padding:14px 22px;background:rgba(18,9,40,.5);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:14px;}
.brand{display:flex;align-items:center;gap:13px;min-width:0;}
.logo-img{width:48px;height:48px;border-radius:16px;object-fit:cover;border:2px solid rgba(232,121,249,.5);box-shadow:0 0 26px rgba(232,121,249,.55);flex:0 0 auto;animation:logoPulse 3s ease-in-out infinite;}
body.speaking .logo-img{box-shadow:0 0 46px rgba(232,121,249,.95);animation:logoGlow .8s ease-in-out infinite;}
@keyframes logoPulse{0%,100%{box-shadow:0 0 20px rgba(232,121,249,.4);}50%{box-shadow:0 0 36px rgba(236,72,153,.7);}}
@keyframes logoGlow{0%,100%{transform:scale(1);}50%{transform:scale(1.07);}}
.title{font-size:19px;font-weight:800;letter-spacing:.5px;background:linear-gradient(90deg,#f0abfc,#e879f9,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;display:flex;align-items:center;gap:8px;}
.ver{font-size:9px;font-weight:700;color:#0d0721;background:linear-gradient(90deg,#f0abfc,#e879f9);padding:2px 7px;border-radius:6px;letter-spacing:1px;-webkit-text-fill-color:#0d0721;}
.online{display:inline-flex;align-items:center;gap:6px;color:#4ade80;font-size:11px;margin-top:2px;}
.dot{width:7px;height:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 12px #22c55e;animation:pulse 1.8s infinite;}
@keyframes pulse{50%{opacity:.4;transform:scale(.8);}}
.mood-badge{font-size:15px;-webkit-text-fill-color:initial;}
.settings-btn{width:42px;height:42px;border-radius:14px;border:1px solid var(--line);background:var(--glass);color:var(--txt);font-size:18px;cursor:pointer;transition:all .3s;display:grid;place-items:center;backdrop-filter:blur(10px);}
.settings-btn:hover{background:rgba(232,121,249,.15);transform:rotate(90deg);}
.settings-panel{max-height:0;overflow:hidden;transition:max-height .35s ease;background:rgba(18,9,40,.7);}
.settings-panel.open{max-height:400px;border-bottom:1px solid var(--line);}
.settings-grid{display:flex;flex-wrap:wrap;gap:8px;padding:14px 18px;justify-content:center;}
.small-btn{border:1px solid var(--line);background:var(--glass);color:var(--txt);padding:9px 14px;border-radius:12px;cursor:pointer;font-size:12px;transition:all .2s;backdrop-filter:blur(8px);}
.small-btn:hover{background:rgba(232,121,249,.14);transform:translateY(-1px);}
.small-btn.active{background:rgba(232,121,249,.2);border-color:var(--pink);}
.small-btn.live-on{background:rgba(236,72,153,.28);border-color:var(--pink2);color:#f0abfc;}
.voice-select{border:1px solid var(--line);background:var(--glass);color:var(--txt);padding:9px 12px;border-radius:12px;cursor:pointer;font-size:12px;outline:none;}
.voice-select option{background:#1e1b4b;}
.theme-row{display:flex;align-items:center;gap:8px;padding:2px 16px 14px;justify-content:center;flex-wrap:wrap;}
.theme-label{font-size:11px;color:var(--mut);}
.theme-dot{width:28px;height:28px;border-radius:50%;border:2px solid rgba(255,255,255,.3);cursor:pointer;transition:transform .2s,box-shadow .2s;}
.theme-dot:hover{transform:scale(1.15);}
.theme-dot.active{box-shadow:0 0 0 2px var(--pink),0 0 16px var(--pink);}
#chat{flex:1;padding:22px;overflow-y:auto;scroll-behavior:smooth;}
.message-row{display:flex;margin:16px 0;gap:10px;align-items:flex-start;animation:messageIn .35s cubic-bezier(.2,.9,.3,1.2);}
.message-row.user-row{justify-content:flex-end;}
.message-row.proactive-row{justify-content:center;}
.message-row.proactive-row .message{background:rgba(236,72,153,.12);border:1px dashed rgba(236,72,153,.45);font-style:italic;max-width:70%;}
@keyframes messageIn{from{opacity:0;transform:translateY(14px) scale(.96);}to{opacity:1;transform:translateY(0) scale(1);}}
.avatar{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;font-size:16px;flex:0 0 auto;margin-top:2px;overflow:hidden;}
.avatar.ai{background:linear-gradient(135deg,var(--pink),var(--violet));box-shadow:0 0 18px rgba(139,92,246,.5);}
.avatar.user{background:linear-gradient(135deg,#be185d,var(--pink2));}
.avatar img{width:100%;height:100%;object-fit:cover;}
.message{max-width:min(75%,740px);padding:14px 18px;border-radius:20px;line-height:1.65;word-wrap:break-word;backdrop-filter:blur(12px);}
.message .msg-text{white-space:pre-wrap;}
.message .msg-text b{color:#f5d0fe;}
.message .msg-text code{background:rgba(232,121,249,.14);border:1px solid rgba(232,121,249,.35);padding:1px 6px;border-radius:6px;font-family:Consolas,monospace;font-size:.9em;color:#f0abfc;}
.message img.msg-img{max-width:260px;border-radius:14px;margin-top:8px;display:block;border:1px solid var(--line);cursor:pointer;}
.ai{background:rgba(255,255,255,.07);border:1px solid rgba(167,139,250,.28);border-top-left-radius:6px;box-shadow:0 8px 28px rgba(0,0,0,.3);}
.user{background:linear-gradient(135deg,var(--pink2),var(--violet));border-top-right-radius:6px;box-shadow:0 8px 30px rgba(168,85,247,.45);}
.meta{font-size:10px;opacity:.55;margin-top:7px;display:flex;align-items:center;gap:6px;}
.brain-badge{display:inline-block;padding:1px 8px;border-radius:10px;background:rgba(232,121,249,.16);border:1px solid rgba(232,121,249,.38);font-size:10px;color:#f0abfc;}
.copy-btn{cursor:pointer;opacity:.6;margin-left:auto;}
.thinking{display:flex;align-items:center;gap:7px;color:#f5d0fe;font-style:italic;}
.thinking span{width:7px;height:7px;border-radius:50%;background:var(--pink);animation:bounce 1.1s infinite;}
.thinking span:nth-child(2){animation-delay:.15s;}.thinking span:nth-child(3){animation-delay:.3s;}
@keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:.4;}30%{transform:translateY(-6px);opacity:1;}}
.gallery-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;max-width:440px;}
.gallery-item{position:relative;border-radius:14px;overflow:hidden;border:1px solid var(--line);cursor:pointer;aspect-ratio:1;background:rgba(0,0,0,.35);transition:all .3s;}
.gallery-item:hover{transform:scale(1.03);box-shadow:0 0 26px rgba(232,121,249,.45);}
.gallery-item img{width:100%;height:100%;object-fit:cover;display:block;}
.gallery-item .gi-overlay{position:absolute;inset:0;background:linear-gradient(transparent 60%,rgba(0,0,0,.6));opacity:0;transition:opacity .3s;display:flex;align-items:flex-end;justify-content:center;padding:8px;}
.gallery-item:hover .gi-overlay{opacity:1;}
.gi-overlay span{color:#fff;font-size:18px;}
.img-loading{display:flex;align-items:center;justify-content:center;height:100%;color:var(--mut);font-size:11px;animation:pulse 1.5s infinite;}
.lightbox{position:fixed;inset:0;background:rgba(5,2,12,.93);backdrop-filter:blur(12px);z-index:200;display:none;align-items:center;justify-content:center;flex-direction:column;gap:14px;padding:20px;}
.lightbox.show{display:flex;}
.lightbox img{max-width:90vw;max-height:72vh;border-radius:18px;box-shadow:0 0 70px rgba(232,121,249,.45);border:1px solid var(--line);}
.lightbox-actions{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;}
.lb-btn{padding:11px 22px;border-radius:14px;border:1px solid var(--line);background:var(--glass);color:var(--txt);cursor:pointer;font-size:13px;transition:all .2s;backdrop-filter:blur(10px);text-decoration:none;}
.lb-btn:hover{background:rgba(232,121,249,.2);transform:translateY(-2px);}
.lb-close{position:absolute;top:20px;right:20px;width:46px;height:46px;border-radius:50%;border:1px solid var(--line);background:var(--glass);color:var(--txt);font-size:20px;cursor:pointer;display:grid;place-items:center;}
.bottom{padding:14px 16px calc(14px + env(safe-area-inset-bottom));background:rgba(18,9,40,.7);border-top:1px solid var(--line);}
.status-row{display:flex;align-items:center;gap:10px;margin:0 4px 10px;flex-wrap:wrap;}
.voice-status{min-height:18px;color:#4ade80;font-size:12px;flex:1;min-width:150px;}
#waveform{display:none;align-items:center;gap:3px;height:20px;cursor:pointer;}
body.speaking #waveform{display:flex;}
#waveform span{width:4px;height:18px;background:linear-gradient(180deg,var(--pink),var(--violet));border-radius:2px;animation:wv .9s infinite ease-in-out;}
#waveform span:nth-child(2){animation-delay:.15s;}#waveform span:nth-child(3){animation-delay:.3s;}#waveform span:nth-child(4){animation-delay:.45s;}#waveform span:nth-child(5){animation-delay:.6s;}
@keyframes wv{0%,100%{transform:scaleY(.25);}50%{transform:scaleY(1);}}
.quick-actions{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;}
.quick-btn{padding:7px 14px;border-radius:999px;border:1px solid var(--line);background:var(--glass);color:var(--txt);font-size:11px;cursor:pointer;transition:all .2s;backdrop-filter:blur(8px);}
.quick-btn:hover{background:rgba(232,121,249,.16);transform:translateY(-1px);border-color:var(--pink);}
.composer{display:flex;gap:8px;align-items:center;}
input{flex:1;min-width:0;padding:14px 18px;border:1px solid var(--line);border-radius:999px;outline:none;background:rgba(13,7,33,.6);color:#fff;font-size:14px;transition:all .3s;backdrop-filter:blur(10px);}
input:focus{border-color:rgba(232,121,249,.65);box-shadow:0 0 28px rgba(232,121,249,.2);}
input::placeholder{color:var(--mut);}
.action-btn{width:48px;height:48px;border:none;border-radius:16px;cursor:pointer;font-size:19px;color:white;transition:all .2s;flex:0 0 auto;}
.action-btn:hover{transform:translateY(-2px) scale(1.05);}
.mic{background:linear-gradient(135deg,#16a34a,#059669);}
.cam{background:linear-gradient(135deg,#f59e0b,#d97706);}
.scr{background:linear-gradient(135deg,var(--violet),#6d28d9);}
.send{background:linear-gradient(135deg,var(--pink),var(--pink2),var(--violet));}
.fab{display:none;width:48px;height:48px;border:none;border-radius:16px;background:linear-gradient(135deg,var(--pink),var(--pink2));color:#fff;font-size:20px;cursor:pointer;transition:transform .3s;flex:0 0 auto;}
.fab.spin{transform:rotate(45deg);}
.footer-note{margin-top:8px;text-align:center;color:var(--mut);font-size:9px;letter-spacing:1px;}
.sheet-backdrop{position:fixed;inset:0;background:rgba(5,2,12,.65);backdrop-filter:blur(5px);opacity:0;pointer-events:none;transition:opacity .3s;z-index:90;}
.sheet-backdrop.show{opacity:1;pointer-events:auto;}
.sheet{position:fixed;left:50%;transform:translate(-50%,105%);bottom:0;width:min(560px,100%);background:rgba(28,14,58,.97);border:1px solid var(--line);border-bottom:none;border-radius:28px 28px 0 0;padding:14px 18px calc(20px + env(safe-area-inset-bottom));transition:transform .35s cubic-bezier(.2,.9,.3,1.1);z-index:95;box-shadow:0 -20px 70px rgba(139,92,246,.3);}
.sheet.open{transform:translate(-50%,0);}
.sheet-handle{width:44px;height:5px;border-radius:99px;background:rgba(232,121,249,.4);margin:0 auto 12px;}
.sheet-title{font-size:12px;letter-spacing:2px;color:var(--mut);text-transform:uppercase;margin-bottom:12px;text-align:center;}
.sheet-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}
.tile{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 8px;border-radius:18px;border:1px solid var(--line);background:var(--glass);cursor:pointer;transition:all .2s;color:var(--txt);}
.tile:active{transform:scale(.94);}
.tile .ti{font-size:24px;}
.tile .tl{font-size:11px;font-weight:600;}
.tile:hover{background:rgba(232,121,249,.14);border-color:var(--pink);}
.wake-word-indicator{position:fixed;top:20px;right:20px;display:flex;align-items:center;gap:10px;padding:10px 18px;background:rgba(232,121,249,.16);border:1px solid rgba(232,121,249,.4);border-radius:30px;backdrop-filter:blur(10px);opacity:0;transform:translateY(-20px);transition:all .3s ease;z-index:1000;}
.wake-word-indicator.active{opacity:1;transform:translateY(0);}
.wake-word-indicator.listening{background:rgba(34,197,94,.2);border-color:rgba(34,197,94,.5);}
.wake-word-indicator.speaking{background:rgba(236,72,153,.28);border-color:rgba(236,72,153,.55);}
.wake-word-orb{width:14px;height:14px;border-radius:50%;background:var(--pink);animation:orbPulse 1.5s ease-in-out infinite;}
.wake-word-indicator.listening .wake-word-orb{background:#22c55e;}
.wake-word-indicator.speaking .wake-word-orb{background:#f0abfc;}
@keyframes orbPulse{0%,100%{transform:scale(1);}50%{transform:scale(1.3);}}
.wake-word-text{color:#fff;font-size:12px;font-weight:600;}
body[data-theme="ocean"]{--bg:#03102b;--card:rgba(4,26,56,.6);--line:rgba(56,189,248,.25);--pink:#22d3ee;--violet:#3b82f6;--pink2:#2dd4bf;--blue:#60a5fa;--txt:#eaf7ff;--mut:#8fb3d1;}
body[data-theme="ocean"] .title{background-image:linear-gradient(90deg,#a5f3fc,#22d3ee,#60a5fa);}
body[data-theme="ocean"] .ver{background:linear-gradient(90deg,#a5f3fc,#22d3ee);}
body[data-theme="ocean"] .logo-img{border-color:rgba(34,211,238,.55);box-shadow:0 0 26px rgba(34,211,238,.5);}
body[data-theme="ocean"] .message .msg-text b{color:#bae6fd;}
body[data-theme="ocean"] .avatar.user{background:linear-gradient(135deg,#0369a1,#2dd4bf);}
body[data-theme="ocean"] .ai{border-color:rgba(59,130,246,.3);}
body[data-theme="sunset"]{--bg:#170a12;--card:rgba(46,16,28,.6);--line:rgba(251,146,60,.28);--pink:#fb923c;--violet:#f472b6;--pink2:#f97316;--blue:#fbbf24;--txt:#fff3e8;--mut:#cfa093;}
body[data-theme="sunset"] .title{background-image:linear-gradient(90deg,#fed7aa,#fb923c,#f472b6);}
body[data-theme="sunset"] .ver{background:linear-gradient(90deg,#fed7aa,#fb923c);}
body[data-theme="sunset"] .logo-img{border-color:rgba(251,146,60,.55);box-shadow:0 0 26px rgba(251,146,60,.5);}
body[data-theme="sunset"] .message .msg-text b{color:#ffedd5;}
body[data-theme="sunset"] .avatar.user{background:linear-gradient(135deg,#9a3412,#f472b6);}
body[data-theme="sunset"] .ai{border-color:rgba(244,114,182,.3);}
body[data-theme="mint"]{--bg:#041712;--card:rgba(6,40,32,.6);--line:rgba(52,211,153,.25);--pink:#34d399;--violet:#059669;--pink2:#2dd4bf;--blue:#4ade80;--txt:#eafff5;--mut:#93c2ae;}
body[data-theme="mint"] .title{background-image:linear-gradient(90deg,#a7f3d0,#34d399,#4ade80);}
body[data-theme="mint"] .ver{background:linear-gradient(90deg,#a7f3d0,#34d399);}
body[data-theme="mint"] .logo-img{border-color:rgba(52,211,153,.55);box-shadow:0 0 26px rgba(52,211,153,.5);}
body[data-theme="mint"] .message .msg-text b{color:#d1fae5;}
body[data-theme="mint"] .avatar.user{background:linear-gradient(135deg,#065f46,#2dd4bf);}
body[data-theme="mint"] .ai{border-color:rgba(16,185,129,.3);}
body[data-theme="stealth"]{--bg:#0e1116;--card:rgba(20,24,32,.7);--line:rgba(59,130,246,.25);--pink:#3b82f6;--violet:#2563eb;--pink2:#06b6d4;--blue:#3b82f6;--txt:#e8ecf4;--mut:#98a2b3;}
body[data-theme="stealth"] .title{background-image:linear-gradient(90deg,#93c5fd,#3b82f6,#06b6d4);}
body[data-theme="stealth"] .ver{background:linear-gradient(90deg,#93c5fd,#3b82f6);}
body[data-theme="stealth"] .logo-img{border-color:rgba(59,130,246,.55);box-shadow:0 0 26px rgba(59,130,246,.5);}
body[data-theme="stealth"] .message .msg-text b{color:#bfdbfe;}
body[data-theme="stealth"] .avatar.user{background:linear-gradient(135deg,#1d4ed8,#06b6d4);}
body[data-theme="stealth"] .ai{border-color:rgba(37,99,235,.35);}
body[data-theme="ivory"]{--bg:#eef1f8;--card:rgba(255,255,255,.85);--line:rgba(99,102,241,.25);--pink:#6366f1;--violet:#8b5cf6;--pink2:#ec4899;--blue:#06b6d4;--txt:#232a3a;--mut:#69718a;--glass:rgba(255,255,255,.7);}
body[data-theme="ivory"] .title{background-image:linear-gradient(90deg,#4f46e5,#7c3aed,#db2777);}
body[data-theme="ivory"] .ver{background:linear-gradient(90deg,#818cf8,#6366f1);}
body[data-theme="ivory"] .logo-img{border-color:rgba(99,102,241,.5);box-shadow:0 0 22px rgba(99,102,241,.35);}
body[data-theme="ivory"] .ai{background:rgba(255,255,255,.92);border-color:rgba(99,102,241,.25);box-shadow:0 8px 24px rgba(99,102,241,.12);}
body[data-theme="ivory"] .message .msg-text b{color:#4338ca;}
body[data-theme="ivory"] .message .msg-text code{color:#6d28d9;background:rgba(139,92,246,.08);}
body[data-theme="ivory"] input{background:#fff;color:#232a3a;}
body[data-theme="ivory"] .small-btn,body[data-theme="ivory"] .settings-btn,body[data-theme="ivory"] .quick-btn,body[data-theme="ivory"] .voice-select{background:#fff;color:#3a4156;}
body[data-theme="ivory"] .voice-select option{background:#fff;}
body[data-theme="ivory"] .sheet{background:#fdfdff;}
body[data-theme="ivory"] .tile{background:#f2f3fa;color:#232a3a;}
body[data-theme="ivory"] .online,body[data-theme="ivory"] .voice-status{color:#059669;}
body[data-theme="ivory"] .avatar.user{background:linear-gradient(135deg,#4f46e5,#06b6d4);}
body[data-theme="ivory"] .theme-dot{border-color:rgba(0,0,0,.2);}
@media (max-width:700px){
body{padding:0;}
.app{width:100%;height:100vh;height:100dvh;min-height:0;border-radius:0;border:none;}
.header{padding:10px 14px;}
.logo-img{width:40px;height:40px;border-radius:13px;}
.title{font-size:16px;}
#chat{padding:14px 12px;}
.message{max-width:86%;}
.quick-actions{display:none;}
.fab{display:block;}
.cam{display:none;}
.scr{display:none;}
.action-btn{width:44px;height:44px;border-radius:14px;}
input{font-size:14px;padding:13px 16px;}
.avatar{width:30px;height:30px;border-radius:10px;font-size:13px;}
.footer-note{display:none;}
.gallery-grid{max-width:100%;gap:6px;}
}
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
<img src="/logo.png" alt="Vasanth AI" class="logo-img">
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
<button class="small-btn" onclick="setCustomWake()">🗣️ Wake Word</button>
<button class="small-btn" onclick="clearChat()">🗑️ Clear</button>
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
</div>
<div class="composer">
<input id="message" type="text" placeholder="Say 'Macha' or type..." autocomplete="off">
<button class="action-btn scr" onclick="quickSend('Take screenshot')" title="Screenshot">📸</button>
<button class="action-btn cam" onclick="pickImage()" title="Photo">📷</button>
<button class="action-btn mic" onclick="startVoice()" title="Voice">🎤</button>
<button class="action-btn send" onclick="sendMessage()" title="Send">➤</button>
<button class="fab" id="fabBtn" onclick="toggleSheet()" title="Quick Actions">✨</button>
</div>
<div class="footer-note">VASANTH AI • 💎 PREMIUM EDITION</div>
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
document.body.setAttribute("data-theme",t);
localStorage.setItem("vaTheme",t);
document.getElementById("verBadge").textContent=label;
document.querySelectorAll(".theme-dot").forEach(d=>{ d.classList.toggle("active",d.getAttribute("data-theme")===t); });
setVoiceStatus("🎨 Theme: "+label);
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
document.body.setAttribute("data-theme",t);
document.getElementById("verBadge").textContent=THEME_LABELS[t]||"ROYAL";
document.querySelectorAll(".theme-dot").forEach(d=>{ d.classList.toggle("active",d.getAttribute("data-theme")===t); });
})();
</script>
<script>
const cv=document.getElementById("particles"),cx=cv.getContext("2d");
let P=[];
function rsz(){cv.width=innerWidth;cv.height=innerHeight;}
rsz();addEventListener("resize",rsz);
for(let i=0;i<50;i++)P.push({x:Math.random()*innerWidth,y:Math.random()*innerHeight,vx:(Math.random()-.5)*.5,vy:(Math.random()-.5)*.5,r:Math.random()*2+.8});
function drawP(){cx.clearRect(0,0,cv.width,cv.height);
for(const p of P){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>cv.width)p.vx*=-1;if(p.y<0||p.y>cv.height)p.vy*=-1;cx.beginPath();cx.arc(p.x,p.y,p.r,0,7);cx.fillStyle="rgba(232,121,249,.35)";cx.fill();}
for(let i=0;i<P.length;i++)for(let j=i+1;j<P.length;j++){const dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d=dx*dx+dy*dy;if(d<13000){cx.strokeStyle="rgba(167,139,250,"+(0.14*(1-d/13000))+")";cx.beginPath();cx.moveTo(P[i].x,P[i].y);cx.lineTo(P[j].x,P[j].y);cx.stroke();}}
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
function startWake(){if(!wakeWordEnabled||busy||wakeActive||liveMode)return;const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return;try{wakeRecognition=new SR();}catch(e){return;}wakeRecognition.lang="ta-IN";wakeRecognition.continuous=true;wakeRecognition.interimResults=true;wakeRecognition.onstart=()=>{wakeActive=true;showIndicator("active",'Listening "'+(customWake||"Macha")+'"...');};wakeRecognition.onresult=(e)=>{if(busy)return;let t="";for(let i=e.resultIndex;i<e.results.length;i++)t+=e.results[i][0].transcript;if(!t)return;console.log("🎤 wake heard:",t);const a=detectWake(t);if(a!==null){playWakeBeep();stopWake();busy=true;if(a.length>=2){input.value=a;sendMessage();}else{setVoiceStatus("🗣️ Sollu macha...");if(voiceEnabled){playTTS("Sollu macha! Enna sollanum?").then(()=>startCommandRecognition());}else{startCommandRecognition();}}}};wakeRecognition.onerror=(e)=>{console.log("wake error:",e.error);setVoiceStatus("🎤 Mic: "+e.error);};wakeRecognition.onend=()=>{wakeActive=false;if(wakeWordEnabled&&!busy&&!liveMode)setTimeout(startWake,500);};try{wakeRecognition.start();}catch(e){}}
function startCommandRecognition(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){finishCycle();return;}commandRecognition=new SR();commandRecognition.lang="ta-IN";commandRecognition.continuous=false;commandRecognition.interimResults=false;let got=false;commandRecognition.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};commandRecognition.onend=()=>{if(!got)finishCycle();};setTimeout(()=>{try{commandRecognition.start();}catch(e){finishCycle();}},400);}
function toggleWakeWord(){wakeWordEnabled=!wakeWordEnabled;const b=document.getElementById("wakeBtn");if(wakeWordEnabled){b.textContent="🎙️ Wake: ON";b.classList.add("active");startWake();}else{b.textContent="🎙️ Wake: OFF";b.classList.remove("active");stopWake();busy=false;showIndicator("","");}}
function startVoice(){
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!SR){setVoiceStatus("⚠️ Chrome use பண்ணுங்க");return;}
if(!window.isSecureContext){setVoiceStatus("🔒 Mic localhost-ல மட்டும் தான்");return;}
busy=true;stopWake();
const r=new SR();r.lang="ta-IN";r.continuous=false;r.interimResults=false;let got=false;
setVoiceStatus("🎤 Speaking...");
r.onresult=(e)=>{got=true;input.value=e.results[0][0].transcript;sendMessage();};
r.onerror=(e)=>{setVoiceStatus(e.error==="not-allowed"?"🚫 Mic Allow பண்ணுங்க":e.error==="no-speech"?"🤫 மறுபடி பேசு":"⚠️ Mic: "+e.error);};
r.onend=()=>{if(!got)finishCycle();};
try{r.start();}catch(e){finishCycle();}
}
let deferredPrompt=null;
window.addEventListener("beforeinstallprompt",(e)=>{e.preventDefault();deferredPrompt=e;const b=document.getElementById("installBtn");if(b)b.style.display="inline-block";});
function installApp(){if(!deferredPrompt)return;deferredPrompt.prompt();deferredPrompt.userChoice.then(r=>{if(r.outcome==="accepted")document.getElementById("installBtn").style.display="none";deferredPrompt=null;});}
if("serviceWorker" in navigator){window.addEventListener("load",()=>{navigator.serviceWorker.register("/sw.js").catch(e=>{});});}
input.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();sendMessage();}});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){stopSpeaking();closeLightbox();toggleSheet(false);}});
document.getElementById("lightbox").addEventListener("click",function(e){if(e.target===this)closeLightbox();});
loadHistory();setTimeout(startWake,1000);
</script>
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

JARVIS_HTML = r"""
<!DOCTYPE html>
<html lang="ta">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>VASANTH AI — QUANTUM</title>
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
.icobtn:hover{box-shadow:0 0 14px rgba(125,211,252,.4);}
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
.stage{position:relative;width:100%;max-width:560px;height:380px;display:grid;place-items:center;overflow:hidden;border-radius:20px;}
.stars{position:absolute;inset:0;pointer-events:none;}
.stars i{position:absolute;background:#e0f2fe;border-radius:50%;opacity:.7;animation:tw 3s infinite;}
@keyframes tw{50%{opacity:.1}}
.rings{position:absolute;inset:0;pointer-events:none;}
.rings i{position:absolute;left:50%;top:62%;border:1.5px solid rgba(192,132,252,.5);border-radius:50%;animation:ripple 3.2s ease-out infinite;}
.rings i:nth-child(1){width:230px;height:58px;margin:-29px 0 0 -115px;}
.rings i:nth-child(2){width:300px;height:76px;margin:-38px 0 0 -150px;animation-delay:.8s;border-color:rgba(125,211,252,.4);}
.rings i:nth-child(3){width:380px;height:96px;margin:-48px 0 0 -190px;animation-delay:1.6s;border-color:rgba(192,132,252,.25);}
@keyframes ripple{0%{opacity:.9;transform:scale(.85)}100%{opacity:0;transform:scale(1.15)}}
.chiprow{position:absolute;top:10px;left:0;right:0;display:flex;justify-content:center;gap:8px;z-index:3;padding:0 8px;}
.fchip{border:1px solid var(--line);background:rgba(10,12,30,.78);backdrop-filter:blur(8px);border-radius:12px;padding:7px 12px;font-size:10px;color:var(--txt);box-shadow:0 0 18px rgba(125,211,252,.12);animation:floaty 5s ease-in-out infinite;}
.fchip small{display:block;color:var(--mut);font-size:8px;}
.fchip.b{position:absolute;left:50%;transform:translateX(-50%);bottom:8px;animation-delay:2s;white-space:nowrap;}
@keyframes floaty{50%{margin-top:-6px}}
.orb{position:relative;width:190px;height:190px;border-radius:50%;z-index:2;
background:radial-gradient(circle at 50% 42%,rgba(240,249,255,.95),rgba(125,211,252,.55) 28%,rgba(168,85,247,.4) 58%,rgba(2,4,12,0) 78%),
radial-gradient(circle at 32% 32%,rgba(56,189,248,.5),transparent 60%),
radial-gradient(circle at 68% 62%,rgba(192,132,252,.55),transparent 60%);
filter:drop-shadow(0 0 34px rgba(168,85,247,.65));animation:orbPulse 3s ease-in-out infinite;}
.orb::before{content:"";position:absolute;inset:-10px;border-radius:50%;background:conic-gradient(from 0deg,transparent 0 40deg,rgba(125,211,252,.55) 70deg,transparent 100deg,transparent 180deg,rgba(192,132,252,.55) 230deg,transparent 270deg);filter:blur(7px);animation:swirl 6s linear infinite;}
.orb::after{content:"";position:absolute;inset:20px;border-radius:50%;background:radial-gradient(circle at 50% 50%,#f0f9ff 0%,#7dd3fc 32%,rgba(168,85,247,.65) 62%,transparent 78%);filter:blur(2px);animation:corePulse 2s ease-in-out infinite;}
@keyframes swirl{to{transform:rotate(360deg)}}
@keyframes orbPulse{50%{transform:scale(1.05)}}
@keyframes corePulse{50%{transform:scale(1.12);filter:blur(3px)}}
body.speaking .orb{animation-duration:.9s;filter:drop-shadow(0 0 60px rgba(192,132,252,.95));}
body.speaking .orb::after{animation-duration:.5s;}
.bub{position:absolute;max-width:160px;background:rgba(10,12,30,.8);border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-size:10px;line-height:1.5;z-index:3;}
.bub.l{left:3%;bottom:18%;}
.bub.r{right:3%;bottom:24%;color:var(--cy);}
.dock{display:grid;grid-template-columns:repeat(8,54px);gap:8px;justify-content:center;margin-top:12px;}
.dbtn{width:54px;height:54px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--txt);font-size:17px;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;}
.dbtn small{font-size:7px;color:var(--mut);}
.dbtn:hover{border-color:var(--pu);box-shadow:0 0 16px rgba(192,132,252,.4);}
.cores{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:12px;}
.core{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:8px 12px;display:flex;align-items:center;gap:8px;font-size:8px;color:var(--mut);letter-spacing:1px;}
.core i{width:22px;height:22px;border-radius:50%;border:1px solid var(--pu);display:grid;place-items:center;font-size:10px;color:var(--pu);font-style:normal;}
.core b{display:block;color:var(--grn);font-size:7px;}
.cmdbar{display:flex;gap:8px;margin-top:14px;width:100%;max-width:620px;padding:0 10px;}
.cmdbar input{flex:1;min-width:0;background:rgba(3,4,12,.85);border:1px solid var(--line);border-radius:999px;color:var(--txt);padding:12px 16px;font-size:12px;outline:none;}
.cmdbar input:focus{border-color:var(--pu);box-shadow:0 0 20px rgba(192,132,252,.3);}
.cmdbar button{width:44px;height:44px;border-radius:50%;border:none;background:linear-gradient(135deg,var(--cy),var(--pu2));color:#012;font-size:15px;cursor:pointer;flex:0 0 auto;}
.act{display:flex;gap:8px;align-items:center;font-size:10px;color:var(--mut);padding:6px 0;border-bottom:1px dashed rgba(125,211,252,.12);}
.act i{font-style:normal;}
.tgl{display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--mut);padding:5px 0;}
.tgl b{color:var(--txt);font-size:9px;cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:2px 8px;}
.qact{display:grid;grid-template-columns:1fr 1fr;gap:6px;}
.qa{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:8px;font-size:9px;color:var(--mut);cursor:pointer;display:flex;gap:6px;align-items:center;}
.qa:hover{border-color:var(--pu);color:var(--txt);}
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
.ctitle small{font-size:7px;}
.stage{height:330px;}
.orb{width:150px;height:150px;}
.rings i:nth-child(3){display:none;}
.rings i:nth-child(1){width:180px;height:46px;margin:-23px 0 0 -90px;}
.rings i:nth-child(2){width:240px;height:60px;margin:-30px 0 0 -120px;}
.bub{display:none;}
.fchip{padding:6px 10px;font-size:9px;}
.dock{grid-template-columns:repeat(4,1fr);width:100%;padding:0 10px;}
.dbtn{width:100%;height:56px;}
.cmdbar{position:sticky;bottom:8px;z-index:6;max-width:100%;}
.panel{padding:10px;}
.cores{gap:6px;}
.core{padding:6px 10px;}
}
</style>
</head>
<body>
<div class="top">
<div class="tlogo"><img src="/logo.png"><div><h1>VASANTH AI</h1><small>QUANTUM CORE • v3.0</small></div></div>
<div class="tclock"><b id="clock">--:--:--</b><small id="datestr">--</small></div>
<div class="tright">
<div class="tchips">
<div class="tchip">UPTIME<b id="uptime">--</b></div>
<div class="tchip">AI STATUS<b>ONLINE</b></div>
<div class="tchip">VOICE<b><span class="wave"><i></i><i></i><i></i><i></i><i></i><i></i></span> ACTIVE</b></div>
</div>
<button class="icobtn" onclick="startMic(false)">🎤</button>
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
<h3>WEATHER — CHENNAI</h3>
<div style="display:flex;gap:12px;align-items:center">
<div class="ring" id="wRing"><span id="wTemp">--</span></div>
<div><b id="wCond" style="font-size:12px">loading...</b><small style="color:var(--mut);font-size:9px">Chennai, India</small></div>
</div>
<div class="row"><span>Humidity</span><b id="wHum">--</b></div>
<div class="row"><span>Wind</span><b id="wWind">--</b></div>
<div class="row"><span>Rain</span><b id="wRain">--</b></div>
</div>
<div class="panel">
<h3>AI INSIGHTS</h3>
<div class="row"><span>Productivity</span><b style="color:var(--grn)">85%</b></div>
<div class="row"><span>Efficiency</span><b style="color:var(--cy)">92%</b></div>
<div class="row"><span>Active Time</span><b id="uptime2">--</b></div>
</div>
</div>
<div class="center">
<div class="ctitle"><h2>VASANTH AI</h2><small>YOUR PERSONAL AI ASSISTANT</small><br><span class="on">● ONLINE & ACTIVE</span></div>
<div class="stage">
<div class="stars" id="stars"></div>
<div class="rings"><i></i><i></i><i></i></div>
<div class="chiprow">
<div class="fchip" id="fWeather">☀ --°C<small>Humidity --%</small></div>
<div class="fchip" id="fStats">CPU --%<small>RAM --%</small></div>
</div>
<div class="orb"></div>
<div class="fchip b" id="fNet">⚡ Network: -- MB</div>
<div class="bub l">Hello Vasanth 👋<br>How can I help you?</div>
<div class="bub r">என்ன உதவி<br>செய்யலாம்?</div>
</div>
<div class="dock">
<button class="dbtn" onclick="location.href='/'">💬<small>Chat</small></button>
<button class="dbtn" onclick="startMic(false)">🎤<small>Voice</small></button>
<button class="dbtn" onclick="cmd('open youtube')">▶<small>YouTube</small></button>
<button class="dbtn" onclick="window.open('https://web.whatsapp.com')">🟢<small>WhatsApp</small></button>
<button class="dbtn" onclick="cmd('open chrome')">🔍<small>Google</small></button>
<button class="dbtn" onclick="window.open('https://mail.google.com')">✉<small>Gmail</small></button>
<button class="dbtn" onclick="cmd('time')">📅<small>Time</small></button>
<button class="dbtn" onclick="cmd('open notepad')">📝<small>Notepad</small></button>
</div>
<div class="cores">
<div class="core"><i>🎤</i><div>SPEECH RECOGNITION<b>● Active</b></div></div>
<div class="core"><i>🧠</i><div>NLP ENGINE<b>● Active</b></div></div>
<div class="core"><i>🤖</i><div>AUTOMATION<b>● Active</b></div></div>
<div class="core"><i>🔮</i><div>QUANTUM CORE<b id="memCore">--</b></div></div>
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
<div class="panel">
<h3>SMART RESPONSE</h3>
<div style="border:1px solid var(--line);border-radius:10px;padding:8px;font-size:10px;color:var(--cy);margin-bottom:8px">வெளியில் நிலவரம் என்ன?</div>
<div id="smartW" style="font-size:10px;color:var(--mut);line-height:1.7">loading...</div>
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
<h3>SYSTEM CONTROL</h3>
<div style="display:flex;justify-content:center;margin-bottom:8px"><div class="ring" style="--p:50%"><span>50%</span></div></div>
<div class="tgl"><span>📶 Wi-Fi</span><b>Connected</b></div>
<div class="tgl"><span>🔵 Bluetooth</span><b>On</b></div>
<div class="tgl"><span>🌙 Night Mode</span><b onclick="this.textContent=this.textContent==='On'?'Off':'On'">Off</b></div>
<div class="tgl"><span>🔕 Do Not Disturb</span><b onclick="this.textContent=this.textContent==='On'?'Off':'On'">Off</b></div>
<div class="tgl"><span>⚡ Performance</span><b>Balanced</b></div>
</div>
<div class="panel">
<h3>QUICK ACTIONS</h3>
<div class="qact">
<div class="qa" onclick="cmd('lock')">🔒 Lock System</div>
<div class="qa" onclick="cmd('take screenshot')">📸 Screenshot</div>
<div class="qa" onclick="cmd('open camera')">📷 Open Camera</div>
<div class="qa" onclick="cmd('open calculator')">🧮 Calculator</div>
<div class="qa" onclick="cmd('play music')">🎵 Play Music</div>
<div class="qa" onclick="cmd('battery')">🔋 System Info</div>
</div>
</div>
<div class="panel">
<h3>COMMAND SHORTCUTS</h3>
<div class="qact">
<div class="qa" onclick="cmd('open chrome')">🌐 Open Chrome</div>
<div class="qa" onclick="window.open('https://web.whatsapp.com')">🟢 WhatsApp</div>
<div class="qa" onclick="cmd('shutdown')">⏻ Shutdown PC</div>
<div class="qa" onclick="cmd('weather')">🌦 Weather</div>
</div>
</div>
</div>
</div>
<div class="foot"><span><b>VASANTH AI</b> — 100% TAMIL • தமிழ்</span><span><b>VOICE</b> | <b>AI</b> | <b>AUTOMATION</b> | <b>QUANTUM CORE</b></span></div>
<script>
function $(id){return document.getElementById(id);}
let voiceEnabled = localStorage.getItem("jarvisVoice") !== "off";
const cpuHist=[],ramHist=[];
function drawGraph(){const c=document.getElementById("graph");if(!c)return;const x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.strokeStyle="rgba(125,211,252,.15)";x.lineWidth=1;for(let i=1;i<4;i++){x.beginPath();x.moveTo(0,c.height*i/4);x.lineTo(c.width,c.height*i/4);x.stroke();}function ln(h,col){if(h.length<2)return;x.strokeStyle=col;x.lineWidth=2;x.beginPath();h.forEach((v,i)=>{const px=(i/59)*c.width;const py=c.height-(v/100)*c.height;i?x.lineTo(px,py):x.moveTo(px,py);});x.stroke();}ln(cpuHist,"#7dd3fc");ln(ramHist,"#c084fc");}
(function(){const s=$("stars");if(!s)return;for(let i=0;i<70;i++){const d=document.createElement("i");d.style.left=Math.random()*100+"%";d.style.top=Math.random()*100+"%";const sz=(Math.random()*2+1).toFixed(1);d.style.width=sz+"px";d.style.height=sz+"px";d.style.animationDelay=(Math.random()*4).toFixed(1)+"s";s.appendChild(d);}})();
function toggleVoice(){
voiceEnabled=!voiceEnabled;
localStorage.setItem("jarvisVoice",voiceEnabled?"on":"off");
setVoiceState();
}
function setVoiceState(){
document.title = voiceEnabled ? "VASANTH AI — QUANTUM 🔊" : "VASANTH AI — QUANTUM 🔇";
}
function playTTS(text){
if(!voiceEnabled||!text)return;
fetch("/tts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:text})})
.then(r=>r.blob()).then(b=>{
if(!b.size)return;
const u=URL.createObjectURL(b),a=new Audio(u);
document.body.classList.add("speaking");
const off=()=>{document.body.classList.remove("speaking");URL.revokeObjectURL(u);};
a.onended=off;a.onerror=off;
a.play().catch(off);
}).catch(()=>{});
}
setInterval(()=>{const d=new Date();const c=$("clock");if(c)c.textContent=d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});const ds=$("datestr");if(ds)ds.textContent=d.toLocaleDateString("en-IN",{weekday:"long",day:"2-digit",month:"long",year:"numeric"});},1000);
function fmtUp(s){const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h>0?h+"h "+m+"m":m+"m "+(s%60)+"s";}
setInterval(async()=>{
try{
const r=await fetch("/api/stats");const d=await r.json();
$("cpuRing").style.setProperty("--p",d.cpu+"%");$("cpuTxt").textContent=Math.round(d.cpu)+"%";
$("ramPct").textContent=Math.round(d.ram_pct)+"%";$("ramBar").style.width=d.ram_pct+"%";
$("diskPct").textContent=d.disk_pct+"%";$("diskBar").style.width=d.disk_pct+"%";
$("netSp").textContent=d.net_down+" MB";
$("ndown").textContent=d.net_down+" MB";$("nup").textContent=d.net_up+" MB";
$("uptime").textContent=fmtUp(d.uptime);$("uptime2").textContent=fmtUp(d.uptime);
$("memCore").textContent="● "+d.messages+" Stored";
$("fStats").innerHTML="CPU "+Math.round(d.cpu)+"%<small>RAM "+Math.round(d.ram_pct)+"%</small>";
$("fNet").textContent="⚡ Network: "+d.net_down+" MB";
cpuHist.push(d.cpu);ramHist.push(d.ram_pct);
if(cpuHist.length>60)cpuHist.shift();if(ramHist.length>60)ramHist.shift();
drawGraph();
}catch(e){}
},2000);
fetch("/api/weather").then(r=>r.json()).then(d=>{
if(d.temp==null){$("wCond").textContent="No internet";return;}
$("wTemp").textContent=d.temp+"°";$("wRing").style.setProperty("--p",Math.min(d.temp*2,100)+"%");
$("wCond").textContent=d.temp>=30?"Hot & Humid":"Pleasant";
$("wHum").textContent=d.hum+"%";$("wWind").textContent=d.wind+" km/h";$("wRain").textContent=d.rain+"%";
$("fWeather").innerHTML="☀ "+d.temp+"°C<small>Humidity "+d.hum+"%</small>";
$("smartW").innerHTML="🌤 <b>"+d.temp+"°C</b> | "+(d.temp>=30?"Partly Cloudy":"Pleasant")+"<br>Humidity: "+d.hum+"% • Wind: "+d.wind+" km/h<br>Rain chance: "+d.rain+"% — "+(d.rain>=50?"குடை எடுத்து வா! ☂":"பரவாயில்லை! ☀");
}).catch(()=>{$("wCond").textContent="Offline";});
fetch("/history").then(r=>r.json()).then(d=>{
const box=$("acts");box.innerHTML="";
(d.history||[]).slice(-5).reverse().forEach(h=>{
const t=String(h.text||"");
const ic=t.toLowerCase().includes("youtube")?"▶":t.toLowerCase().includes("screenshot")?"📸":h.role==="user"?"👤":"";
const div=document.createElement("div");div.className="act";
div.innerHTML="<i>"+ic+"</i>"+t.replace(/[<>&]/g,"").slice(0,32);
box.appendChild(div);
});
}).catch(()=>{});
function updMusic(m){ if(m){const t=$("npTitle"); if(t)t.innerHTML=(m.playing?"🎵 ":"⏸ ")+(m.title||"Nothing playing");} }
setInterval(()=>{fetch("/api/music").then(r=>r.json()).then(updMusic).catch(()=>{});},3000);
function music(act){
const q=(document.getElementById("musIn")||{}).value||"";
fetch("/api/music",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:act,query:q})}).then(r=>r.json()).then(d=>{updMusic(d.music);});
}
function startMic(cont){
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!SR){const ms=$("micState");if(ms)ms.textContent="Chrome மட்டும் தான்";return;}
if(!window.isSecureContext){const ms=$("micState");if(ms)ms.textContent="localhost-ல மட்டும்";return;}
const r=new SR();r.lang="ta-IN";r.continuous=cont;r.interimResults=false;
const ms=$("micState");if(ms)ms.textContent="🎧 Listening...";
r.onresult=(e)=>{const t=e.results[e.results.length-1][0].transcript;cmd(t);};
r.onerror=(e)=>{const ms=$("micState");if(ms)ms.textContent="⚠️ "+e.error;};
r.onend=()=>{if(cont)startMic(true);else{const ms=$("micState");if(ms)ms.textContent="Listening...";}};
try{r.start();}catch(e){}
}
const cpuHist=[],ramHist=[];
function drawGraph(){const c=document.getElementById("graph");if(!c)return;const x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.strokeStyle="rgba(125,211,252,.15)";x.lineWidth=1;for(let i=1;i<4;i++){x.beginPath();x.moveTo(0,c.height*i/4);x.lineTo(c.width,c.height*i/4);x.stroke();}function ln(h,col){if(h.length<2)return;x.strokeStyle=col;x.lineWidth=2;x.beginPath();h.forEach((v,i)=>{const px=(i/59)*c.width;const py=c.height-(v/100)*c.height;i?x.lineTo(px,py):x.moveTo(px,py);});x.stroke();}ln(cpuHist,"#7dd3fc");ln(ramHist,"#c084fc");}
</script>
fetch("/api/notes").then(r=>r.json()).then(d=>{
const box=$("notesBox");if(!box)return;
box.innerHTML="";
(d.notes||[]).slice(-3).reverse().forEach(function(n,i){
const div=document.createElement("div");div.className="act";
div.innerHTML="<i>📝</i>"+String(n.text).replace(/[<>&]/g,"").slice(0,26);
box.appendChild(div);
});
(d.todos||[]).map(function(t,idx){return {t:t,idx:idx};}).slice(-4).forEach(function(o){
const div=document.createElement("div");div.className="act";div.style.cursor="pointer";
div.innerHTML="<i>"+(o.t.done?"✅":"☐")+"</i>"+String(o.t.text).replace(/[<>&]/g,"").slice(0,24);
div.onclick=function(){fetch("/api/notes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"toggle_todo",index:o.idx})}).then(loadNotes);};
box.appendChild(div);
});
if(!(d.notes||[]).length && !(d.todos||[]).length) box.innerHTML="<div class='act'><i>📝</i>No notes yet</div>";
}).catch(()=>{});
}
setInterval(loadNotes,5000);
function addQuickNote(){
const v=$("noteIn")?$("noteIn").value.trim():"";if(!v)return;$("noteIn").value="";
const act=v.toLowerCase().startsWith("todo")?"add_todo":"add_note";
const txt=act==="add_todo"?v.replace(/^todo[: ]*/i,""):v;
fetch("/api/notes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:act,text:txt})}).then(loadNotes);
}
function toggleAuto(el){
const k=el.getAttribute("data-key");
const b=el.querySelector("b");
const on=b.textContent==="ON";
b.textContent=!on?"ON":"OFF";
b.style.color=!on?"var(--grn)":"var(--mut)";
fetch("/api/automation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k,value:!on})});
}
fetch("/api/automation").then(r=>r.json()).then(d=>{
document.querySelectorAll(".auto-tgl").forEach(el=>{
const k=el.getAttribute("data-key");
const b=el.querySelector("b");
b.textContent=d[k]?"ON":"OFF";
b.style.color=d[k]?"var(--grn)":"var(--mut)";
});
}).catch(()=>{});
async function cmd(t){
const q=t||$("cin").value.trim();if(!q)return;$("cin").value="";
try{
const r=await fetch("/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:q})});
const d=await r.json();
const txt=String(d.reply||"Done");
playTTS(txt);
}catch(e){}
}
const cpuHist=[],ramHist=[];
function drawGraph(){const c=document.getElementById("graph");if(!c)return;const x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.strokeStyle="rgba(125,211,252,.15)";x.lineWidth=1;for(let i=1;i<4;i++){x.beginPath();x.moveTo(0,c.height*i/4);x.lineTo(c.width,c.height*i/4);x.stroke();}function ln(h,col){if(h.length<2)return;x.strokeStyle=col;x.lineWidth=2;x.beginPath();h.forEach((v,i)=>{const px=(i/59)*c.width;const py=c.height-(v/100)*c.height;i?x.lineTo(px,py):x.moveTo(px,py);});x.stroke();}ln(cpuHist,"#7dd3fc");ln(ramHist,"#c084fc");}
function startMic(cont){
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(!SR){const ms=$("micState");if(ms)ms.textContent="Chrome மட்டும் தான்";return;}
if(!window.isSecureContext){const ms=$("micState");if(ms)ms.textContent="localhost-ல மட்டும்";return;}
const r=new SR();r.lang="ta-IN";r.continuous=cont;r.interimResults=false;
const ms=$("micState");if(ms)ms.textContent="🎧 Listening...";
r.onresult=(e)=>{const t=e.results[e.results.length-1][0].transcript;cmd(t);};
r.onerror=(e)=>{const ms=$("micState");if(ms)ms.textContent="⚠️ "+e.error;};
r.onend=()=>{if(cont)startMic(true);else{const ms=$("micState");if(ms)ms.textContent="Listening...";}};
try{r.start();}catch(e){}
}
</script>
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
    print("    VASANTH AI - PREMIUM EDITION 💎 (FINAL)")
    print("=" * 60)
    print(f"Groq:     {'READY ✅' if GROQ_API_KEY else 'MISSING ❌'}")
    print(f"AWS:      {'READY ✅' if AWS_READY else 'Not configured'}")
    print(f"Ollama:   {'READY ✅ (OFFLINE!)' if OLLAMA_READY else 'Not running'}")
    print(f"Telegram: {'READY ✅' if (TELEGRAM_AVAILABLE and TELEGRAM_BOT_TOKEN) else 'Not configured'}")
    print(f"Gemini:   {'🥇 NATURAL VOICE READY' if GEMINI_API_KEY else 'NOT SET (fallback)'}")
    print(f"HF Token: {'🎨 Image Backup READY' if HF_TOKEN.startswith('hf_') else 'NOT SET'}")
    print(f"Lameenc:  {'✅ MP3 encoder' if LAMEENC_READY else '❌ pip install lameenc'}")
    print(f"Themes:   🎨 6 themes | 🎭 4 personalities | 🗣️ custom wake")
    print(f"JARVIS:   🤖 /jarvis + AUTOMATION + MUSIC + LIVE GRAPHS")
    print(f"Brain:    🧠 Genius Mode + Screen Vision")
    print(f"Voice:    🔊 Gemini + Google + Edge (multi-provider)")
    print("=" * 60 + "\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, use_reloader=False)
