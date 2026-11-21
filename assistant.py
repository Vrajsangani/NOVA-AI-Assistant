# AetherAI - Core assistant logic
import numpy as np
import platform
import subprocess
import webbrowser
import wikipedia
import requests
import speech_recognition as sr
import pyttsx3
from datetime import datetime
from urllib.parse import quote_plus
import re
import threading
import noisereduce as nr
import os
import glob
import psutil
import time
import pyautogui
import ctypes
from ctypes import wintypes
import win32gui
import win32con
import win32process
import win32api
import smtplib
import json
import random
import calendar
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import PyPDF2
import textwrap
import wikipedia
from bs4 import BeautifulSoup
import noisereduce as nr

class Assistant:
    def _respond(self, text, speak=True, update_ui=True):
        """Unified method to send messages and optionally speak them."""
        if update_ui and hasattr(self, "on_reply") and self.on_reply:
            self.on_reply(text)
        if speak and getattr(self, "voice_enabled", True):
            try:
                self.speak(text)
            except Exception as e:
                print("Speech error:", e)
        return text

    def __init__(self, voice_rate: int = 175, voice_enabled: bool = True):
        self.voice_enabled = voice_enabled
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", voice_rate)
        # Prefer a neutral/en voice if present
        for v in self.engine.getProperty("voices"):
            if "en" in v.languages[0].decode("utf-8").lower() if isinstance(v.languages[0], bytes) else "en" in str(v.languages).lower():
                self.engine.setProperty("voice", v.id)
                break

        # quick intents map (no manual links needed)
        self.quick_sites = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "maps": "https://maps.google.com",
            "whatsapp": "https://web.whatsapp.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://x.com",
            "x": "https://x.",
            "github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "news": "https://news.google.com",
            "netflix": "https://www.netflix.com",
            "spotify": "https://open.spotify.com",
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "linkedin": "https://www.linkedin.com",
            "amazon": "https://www.amazon.com",
            "wikipedia": "https://www.wikipedia.org",
            "translate": "https://translate.google.com",
            "weather": "https://weather.com",
        }

        # Wake word configuration
        self.wake_word = "nova"
        self._wake_listening = False
        self._wake_thread = None
        self._wake_stop = None  # stop function from listen_in_background
        self._mic_device_index = None  # allow selecting a specific microphone
        # Optional UI reply callback to reflect responses on screen
        self.on_reply = None
        # Follow-up capture window after wake word
        self._awaiting_followup_until = 0.0
        # Serialize TTS to avoid conflicts across threads
        self._speech_lock = threading.Lock()

    def set_reply_handler(self, handler):
        """Register a callback to receive textual replies for UI updates."""
        self.on_reply = handler

    # ---------- Speech ----------
    def speak(self, text: str):
        if not text or not self.voice_enabled:
            return

        def _run():
            try:
                # Prevent rapid duplicate speeches of identical text
                now_ts = time.time()
                last = getattr(self, "_last_spoken", ("", 0.0))
                if text == last[0] and (now_ts - last[1]) < 2.0:
                    return
                self._last_spoken = (text, now_ts)
                with self._speech_lock:
                    self.engine.say(text)
                    self.engine.runAndWait()
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()


    def listen(self, phrase_time_limit: int = 6) -> str:
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.pause_threshold = 0.8
            r.adjust_for_ambient_noise(source, duration=1)
            audio = r.listen(source, phrase_time_limit=phrase_time_limit)

        # Convert to numpy array
        audio_data = np.frombuffer(audio.get_raw_data(), np.int16)

        # Apply noise reduction
        reduced_noise = nr.reduce_noise(y=audio_data, sr=16000)

        # Rebuild AudioData for speech_recognition
        clean_audio = sr.AudioData(reduced_noise.tobytes(), 16000, 2)

        try:
            query = r.recognize_google(clean_audio, language="en-IN")
            return query.strip()
        except Exception:
            return ""

    # ---------- Wake word (hands-free) ----------
    def start_wake_word(self):
        """Begin background listening for the wake word 'Aris' using a non-blocking callback."""
        if self._wake_listening:
            return
        self._wake_listening = True

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 250  # initial baseline; auto-adjusts

        # Share recognizer across callback
        def _callback(recognizer_cb, audio: sr.AudioData):
            if not self._wake_listening:
                return
            try:
                text = recognizer_cb.recognize_google(audio, language="en-IN").strip()
                if not text:
                    return
                print(f"Wake heard: {text}")
                low = text.lower()
                # If we're awaiting a follow-up command (user already said wake word recently)
                if time.time() < self._awaiting_followup_until and self.wake_word not in low:
                    try:
                        response = self.process_command(low)
                        print(f"WakeWord→followup: {low} → {response}")
                        if response:
                            self.speak(response)
                            if self.on_reply:
                                self.on_reply(response)
                    except Exception:
                        pass
                    finally:
                        self._awaiting_followup_until = 0.0
                    return
                if self.wake_word in low or low.startswith("hello "+self.wake_word):
                    after = low
                    for token in ("hello "+self.wake_word, self.wake_word+",", self.wake_word+" "):
                        if after.startswith(token):
                            after = after[len(token):].strip()
                            break
                    if after and after != self.wake_word:
                        try:
                            response = self.process_command(after)
                            print(f"WakeWord→cmd: {after} → {response}")
                            if response:
                                self.speak(response)
                                if self.on_reply:
                                    self.on_reply(response)
                        except Exception:
                            pass
                        return
                    # If only wake word detected → prompt and capture next phrase as command
                    # Speak once from wake thread; UI will show text
                    self.speak("Yes?")
                    self._awaiting_followup_until = time.time() + 6.0
            except Exception:
                return

        try:
            mic_kwargs = {}
            if self._mic_device_index is not None:
                mic_kwargs["device_index"] = self._mic_device_index
            self._wake_mic = sr.Microphone(**mic_kwargs)
            with self._wake_mic as source:
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=0.6)
                except Exception:
                    pass
            # Start non-blocking listener
            self._wake_stop = recognizer.listen_in_background(self._wake_mic, _callback, phrase_time_limit=4)
            self._wake_recognizer = recognizer
        except Exception as e:
            print(f"Wake word failed to start: {e}")
            self._wake_listening = False

    def stop_wake_word(self):
        """Stop background wake word listening."""
        self._wake_listening = False
        try:
            if self._wake_stop is not None:
                self._wake_stop(wait_for_stop=False)
                self._wake_stop = None
        except Exception:
            pass
        try:
            self._wake_mic = None
            self._wake_recognizer = None
        except Exception:
            pass

    def list_microphones(self) -> list:
        """Return available microphone device names for selection."""
        try:
            return sr.Microphone.list_microphone_names()
        except Exception:
            return []

    def select_microphone(self, device_index: int = None, device_name_contains: str = None) -> bool:
        """Select a microphone by index or by partial name match for wake word and listening."""
        try:
            if device_index is not None:
                self._mic_device_index = device_index
                return True
            if device_name_contains:
                names = sr.Microphone.list_microphone_names()
                for idx, name in enumerate(names):
                    if device_name_contains.lower() in str(name).lower():
                        self._mic_device_index = idx
                        return True
            return False
        except Exception:
            return False

    # ---------- Helpers ----------
    def search_wikipedia(query):
        try:
            page = wikipedia.page(query)
            soup = BeautifulSoup(page.html(), features="html.parser")  # Add features arg
            return page.summary
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _open_search(self, engine: str, query: str):
        q = quote_plus(query)
        if engine == "google":
            url = f"https://www.google.com/search?q={q}"
        elif engine == "youtube":
            url = f"https://www.youtube.com/results?search_query={q}"
        elif engine == "maps":
            url = f"https://www.google.com/maps/search/{q}"
        else:
            url = f"https://www.google.com/search?q={q}"
        
        try:
            webbrowser.open_new_tab(url)
            return True
        except Exception as e:
            print(f"Error opening search URL: {e}")
            return False

    def _open_quick(self, key: str):
        if key in self.quick_sites:
            webbrowser.open_new_tab(self.quick_sites[key])
            return True
        return False

    def _system_open(self, app: str) -> bool:
        osname = platform.system().lower()
        try:
            if app == "calculator":
                if "windows" in osname:
                    subprocess.Popen(["calc"])
                elif "darwin" in osname:  # macOS
                    subprocess.Popen(["open", "-a", "Calculator"])
                else:
                    subprocess.Popen(["gnome-calculator"])
            elif app in ("notepad", "notes"):
                if "windows" in osname:
                    subprocess.Popen(["notepad"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "TextEdit"])
                else:
                    subprocess.Popen(["gedit"])
            elif app == "control panel":
                if "windows" in osname:
                    subprocess.Popen(["control"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "System Preferences"])
                else:
                    subprocess.Popen(["gnome-control-center"])
            elif app == "command prompt" or app == "cmd":
                if "windows" in osname:
                    subprocess.Popen(["cmd"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Terminal"])
                else:
                    subprocess.Popen(["gnome-terminal"])
            elif app == "powershell":
                if "windows" in osname:
                    subprocess.Popen(["powershell"])
                else:
                    return False
            elif app == "task manager":
                if "windows" in osname:
                    subprocess.Popen(["taskmgr"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Activity Monitor"])
                else:
                    subprocess.Popen(["gnome-system-monitor"])
            elif app == "device manager":
                if "windows" in osname:
                    subprocess.Popen(["devmgmt.msc"])
                else:
                    return False
            elif app == "registry editor":
                if "windows" in osname:
                    subprocess.Popen(["regedit"])
                else:
                    return False
            elif app == "services":
                if "windows" in osname:
                    subprocess.Popen(["services.msc"])
                else:
                    return False
            elif app == "word":
                if "windows" in osname:
                    subprocess.Popen(["winword"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Microsoft Word"])
                else:
                    subprocess.Popen(["libreoffice", "--writer"])
            elif app == "excel":
                if "windows" in osname:
                    subprocess.Popen(["excel"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Microsoft Excel"])
                else:
                    subprocess.Popen(["libreoffice", "--calc"])
            elif app == "powerpoint":
                if "windows" in osname:
                    subprocess.Popen(["powerpnt"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Microsoft PowerPoint"])
                else:
                    subprocess.Popen(["libreoffice", "--impress"])
            elif app == "paint":
                if "windows" in osname:
                    subprocess.Popen(["mspaint"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Preview"])
                else:
                    subprocess.Popen(["gimp"])
            elif app == "media player":
                if "windows" in osname:
                    subprocess.Popen(["wmplayer"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "QuickTime Player"])
                else:
                    subprocess.Popen(["vlc"])
            elif app == "browser":
                if "windows" in osname:
                    subprocess.Popen(["start", "chrome"])
                elif "darwin" in osname:
                    subprocess.Popen(["open", "-a", "Safari"])
                else:
                    subprocess.Popen(["firefox"])
            else:
                return False
            return True
        except Exception:
            return False

    def _open_file(self, filepath: str) -> bool:
        """Open a file with the default application"""
        try:
            osname = platform.system().lower()
            if "windows" in osname:
                os.startfile(filepath)
            elif "darwin" in osname:  # macOS
                subprocess.Popen(["open", filepath])
            else:  # Linux
                subprocess.Popen(["xdg-open", filepath])
            return True
        except Exception:
            return False

    def _open_folder(self, folderpath: str) -> bool:
        """Open a folder in file explorer"""
        try:
            osname = platform.system().lower()
            if "windows" in osname:
                subprocess.Popen(["explorer", folderpath])
            elif "darwin" in osname:  # macOS
                subprocess.Popen(["open", folderpath])
            else:  # Linux
                subprocess.Popen(["xdg-open", folderpath])
            return True
        except Exception:
            return False

    def _open_drive(self, drive: str) -> bool:
        """Open a drive (Windows) or mount point (Linux/macOS)"""
        try:
            osname = platform.system().lower()
            if "windows" in osname:
                # Handle drive letters like C:, D:, etc.
                if len(drive) == 1:
                    drive = drive.upper() + ":"
                elif drive.endswith(":") and len(drive) == 2:
                    drive = drive.upper()
                subprocess.Popen(["explorer", drive + "\\"])
            elif "darwin" in osname:  # macOS
                subprocess.Popen(["open", "/Volumes/" + drive])
            else:  # Linux
                subprocess.Popen(["xdg-open", "/media/" + drive])
            return True
        except Exception:
            return False

    def _find_file(self, filename: str) -> str:
        """Search for a file in common locations"""
        common_paths = [
            os.path.expanduser("~"),  # Home directory
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Pictures"),
            os.path.expanduser("~/Music"),
            os.path.expanduser("~/Videos"),
        ]
        
        # Search for exact filename
        for path in common_paths:
            if os.path.exists(os.path.join(path, filename)):
                return os.path.join(path, filename)
        
        # Search for files containing the filename
        for path in common_paths:
            try:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if filename.lower() in file.lower():
                            return os.path.join(root, file)
            except Exception:
                continue
        
        return None

    def _send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email using Gmail SMTP"""
        try:
            # Note: You need to configure Gmail app password for this to work
            # For now, this opens Gmail compose
            gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={quote_plus(subject)}&body={quote_plus(body)}"
            webbrowser.open_new_tab(gmail_url)
            return True
        except Exception:
            return False

    def _get_news(self, topic: str = "general") -> str:
        """Get latest news"""
        try:
            if topic == "general":
                url = "https://newsapi.org/v2/top-headlines?country=us&apiKey=demo"
            else:
                url = f"https://newsapi.org/v2/everything?q={quote_plus(topic)}&apiKey=demo"
            
            # For demo purposes, return sample news
            news_items = [
                "Breaking: Technology advances in AI continue to shape the future.",
                "Latest: Scientists make breakthrough in renewable energy research.",
                "Update: Global markets show positive trends in technology sector.",
                "News: New space exploration mission launched successfully.",
                "Report: Climate change initiatives gain international support."
            ]
            return random.choice(news_items)
        except Exception:
            return "Could not fetch news at this time."

    def _get_calendar_info(self) -> str:
        """Get calendar information"""
        try:
            now = datetime.now()
            day_name = now.strftime("%A")
            date_str = now.strftime("%B %d, %Y")
            time_str = now.strftime("%I:%M %p")
            
            # Get day of year
            day_of_year = now.timetuple().tm_yday
            
            # Get week number
            week_number = now.isocalendar()[1]
            
            return f"Today is {day_name}, {date_str}. Current time is {time_str}. It's day {day_of_year} of the year, week {week_number}."
        except Exception:
            return "Could not get calendar information."

    def _translate_text(self, text: str, target_lang: str = "es") -> str:
        """Translate text using Google Translate"""
        try:
            # Open Google Translate with the text
            translate_url = f"https://translate.google.com/?sl=auto&tl={target_lang}&text={quote_plus(text)}"
            webbrowser.open_new_tab(translate_url)
            return f"Opening Google Translate for: {text}"
        except Exception:
            return "Could not open translation service."

    def _tell_joke(self) -> str:
        """Tell a random joke"""
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? He was outstanding in his field!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a fake noodle? An impasta!",
            "Why did the math book look so sad? Because it had too many problems!",
            "What do you call a bear with no teeth? A gummy bear!",
            "Why don't skeletons fight each other? They don't have the guts!",
            "What do you call a dinosaur that crashes his car? Tyrannosaurus Wrecks!",
            "Why did the coffee file a police report? It got mugged!",
            "What do you call a fish wearing a bowtie? So-fish-ticated!"
        ]
        return random.choice(jokes)

    def _tell_fun_fact(self) -> str:
        """Tell a random fun fact"""
        facts = [
            "A group of flamingos is called a 'flamboyance'.",
            "Honey never spoils. Archaeologists have found pots of honey in ancient Egyptian tombs that are over 3000 years old and still perfectly edible.",
            "A jiffy is an actual unit of time. It's 1/100th of a second.",
            "The shortest war in history was between Britain and Zanzibar on August 27, 1896. Zanzibar surrendered after 38 minutes.",
            "A group of owls is called a 'parliament'.",
            "The human brain contains approximately 86 billion neurons.",
            "There are more possible games of chess than there are atoms in the observable universe.",
            "A group of crows is called a 'murder'.",
            "The Great Wall of China is not visible from space with the naked eye.",
            "Octopuses have three hearts and blue blood."
        ]
        return random.choice(facts)

    def _read_pdf(self, filename: str) -> str:
        """Read PDF file aloud"""
        try:
            if not filename.lower().endswith('.pdf'):
                return "Please provide a PDF file."
            
            if not os.path.exists(filename):
                # Try to find the file
                found_file = self._find_file(filename)
                if found_file:
                    filename = found_file
                else:
                    return f"Could not find PDF file: {filename}"
            
            with open(filename, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                
                if text.strip():
                    # Limit text length for speech
                    text = text[:500] + "..." if len(text) > 500 else text
                    self.speak(text)
                    return f"Reading PDF: {os.path.basename(filename)}"
                else:
                    return "Could not extract text from PDF."
        except Exception:
            return "Could not read PDF file."

    def _get_general_knowledge(self, question: str) -> str:
        """Get general knowledge answer"""
        try:
            # For now, use Wikipedia as a fallback
            wikipedia.set_lang("en")
            summary = wikipedia.summary(question, sentences=2, auto_suggest=True, redirect=True)
            self.speak(summary)
            return summary
        except Exception:
            return f"I don't have information about {question}. Try asking something else."

    def _play_music_from_youtube(self, query: str) -> str:
        """Play music from YouTube"""
        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(query + ' music')}"
            webbrowser.open_new_tab(url)
            return f"Searching YouTube for music: {query}"
        except Exception:
            return "Could not search for music on YouTube."

    def _close_youtube_tabs(self) -> bool:
        """Close active YouTube tabs by sending Ctrl+W to matching browser windows on Windows."""
        try:
            closed_any = False

            def enum_handler(hwnd, _):
                nonlocal closed_any
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return
                if "youtube" in title.lower():
                    try:
                        # Bring the window to foreground
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.05)
                        # Send Ctrl+W to close the current tab
                        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                        win32api.keybd_event(ord('W'), 0, 0, 0)
                        time.sleep(0.02)
                        win32api.keybd_event(ord('W'), 0, win32con.KEYEVENTF_KEYUP, 0)
                        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                        closed_any = True
                    except Exception:
                        pass

            win32gui.EnumWindows(enum_handler, None)
            return closed_any
        except Exception:
            return False

    def _close_application(self, app_name: str) -> bool:
        """Close an application by name"""
        try:
            # Map common app names to process names
            app_mapping = {
                "youtube": "chrome.exe",
                "google": "chrome.exe", 
                "gmail": "chrome.exe",
                "facebook": "chrome.exe",
                "instagram": "chrome.exe",
                "linkedin": "chrome.exe",
                "netflix": "chrome.exe",
                "spotify": "spotify.exe",
                "whatsapp": "whatsapp.exe",
                "word": "winword.exe",
                "excel": "excel.exe",
                "powerpoint": "powerpnt.exe",
                "notepad": "notepad.exe",
                "calculator": "calculator.exe",
                "paint": "mspaint.exe",
                "chrome": "chrome.exe",
                "firefox": "firefox.exe",
                "edge": "msedge.exe",
                "explorer": "explorer.exe",
                "control panel": "control.exe",
                "cmd": "cmd.exe",
                "powershell": "powershell.exe"
            }
            
            # Get the actual process name
            process_name = app_mapping.get(app_name.lower(), app_name.lower() + ".exe")
            
            print(f"Looking for process: {process_name}")
            closed_any = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info['name'].lower()
                    if process_name.lower() == proc_name or process_name.lower() in proc_name:
                        proc.terminate()
                        closed_any = True
                        print(f"Closed process: {proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return closed_any
        except Exception as e:
            print(f"Error closing application: {e}")
            return False

    def _close_windows_by_title(self, title_substring: str) -> bool:
        """Close visible top-level windows whose title contains the given substring."""
        try:
            title_substring = (title_substring or "").lower().strip()
            if not title_substring:
                return False
            closed_any = False

            def enum_handler(hwnd, _):
                nonlocal closed_any
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd)
                if title and title_substring in title.lower():
                    try:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed_any = True
                    except Exception:
                        pass

            win32gui.EnumWindows(enum_handler, None)
            return closed_any
        except Exception:
            return False

    def _close_explorer_drive(self, drive_letter: str) -> bool:
        """Close File Explorer windows open on a specific drive (Windows)."""
        try:
            if not drive_letter:
                return False
            d = drive_letter.strip().rstrip(":").upper()
            patterns = [f"({d}:)", f"{d}:"]
            closed_any = False

            def enum_handler(hwnd, _):
                nonlocal closed_any
                if not win32gui.IsWindowVisible(hwnd):
                    return
                try:
                    cls = win32gui.GetClassName(hwnd)
                except Exception:
                    cls = ""
                if cls not in ("CabinetWClass", "ExploreWClass"):
                    return
                title = win32gui.GetWindowText(hwnd) or ""
                low = title.lower()
                for p in patterns:
                    if p.lower() in low:
                        try:
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            closed_any = True
                        except Exception:
                            pass
                        break

            win32gui.EnumWindows(enum_handler, None)
            return closed_any
        except Exception:
            return False

    def _get_running_apps(self) -> list:
        """Get list of running applications"""
        try:
            apps = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    if proc.info['name'] and proc.info['cpu_percent'] is not None:
                        apps.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return apps[:20]  # Return top 20 apps
        except Exception:
            return []

    def _kill_process(self, process_name: str) -> bool:
        """Kill a specific process"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                if process_name.lower() in proc.info['name'].lower():
                    proc.kill()
                    return True
            return False
        except Exception:
            return False

    def _control_volume(self, action: str, value: int = 10) -> bool:
        """Control system volume"""
        try:
            if action == "mute":
                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)  # Volume Mute
            elif action == "unmute":
                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)  # Volume Mute (toggle)
            elif action == "increase":
                for _ in range(value // 2):
                    ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)  # Volume Up
            elif action == "decrease":
                for _ in range(value // 2):
                    ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)  # Volume Down
            return True
        except Exception:
            return False

    def _control_brightness(self, action: str, value: int = 10) -> bool:
        """Control screen brightness"""
        try:
            if action == "increase":
                # Increase brightness
                ctypes.windll.user32.keybd_event(0x88, 0, 0, 0)  # Brightness Up
            elif action == "decrease":
                # Decrease brightness
                ctypes.windll.user32.keybd_event(0x87, 0, 0, 0)  # Brightness Down
            return True
        except Exception:
            return False

    def _system_action(self, action: str) -> bool:
        """Perform system actions like shutdown, restart, etc."""
        try:
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", "0"])
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", "0"])
            elif action == "lock":
                ctypes.windll.user32.LockWorkStation()
            elif action == "logoff":
                subprocess.run(["shutdown", "/l"])
            elif action == "sleep":
                ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
            return True
        except Exception:
            return False

    def _take_screenshot(self) -> bool:
        """Take a screenshot"""
        try:
            # Method 1: Try pyautogui
            screenshot = pyautogui.screenshot()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            screenshot.save(filename)
            print(f"Screenshot saved as: {filename}")
            return True
        except Exception as e:
            print(f"PyAutoGUI screenshot failed: {e}")
            try:
                # Method 2: Try Windows Snipping Tool
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"
                subprocess.Popen(["snippingtool", "/clip"], shell=True)
                time.sleep(2)  # Wait for snipping tool to open
                return True
            except Exception as e2:
                print(f"Snipping tool method failed: {e2}")
                try:
                    # Method 3: Try Windows Print Screen simulation
                    ctypes.windll.user32.keybd_event(0x2C, 0, 0, 0)  # Print Screen key
                    ctypes.windll.user32.keybd_event(0x2C, 0, 2, 0)  # Release Print Screen key
                    print("Screenshot copied to clipboard (Print Screen)")
                    return True
                except Exception as e3:
                    print(f"Print Screen method failed: {e3}")
                    return False

    def _play_media_file(self, filename: str) -> bool:
        """Play a media file"""
        try:
            if filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv')):
                # Video files
                subprocess.Popen(["start", filename], shell=True)
            elif filename.lower().endswith(('.mp3', '.wav', '.flac', '.aac', '.ogg')):
                # Audio files
                subprocess.Popen(["start", filename], shell=True)
            else:
                # Other files
                subprocess.Popen(["start", filename], shell=True)
            return True
        except Exception:
            return False

    def _voice_to_text_app(self, app_name: str) -> str:
        """Open an app and start voice-to-text mode"""
        try:
            if self._system_open(app_name):
                # Give the app a moment to launch and become active
                time.sleep(1.5)
                self._focus_app_window(app_name)
                try:
                    pyautogui.click()
                except Exception:
                    pass
                self.speak(f"Opening {app_name}. Say 'stop typing' to finish.", speak=True)
                dictation_result = self._dictate_to_active_window()
                return dictation_result
            else:
                return f"I couldn't open {app_name}."
        except Exception:
            return f"I couldn't open {app_name}."

    def _start_voice_typing(self) -> str:
        """Start voice typing mode - listen for text input"""
        try:
            self.speak("Voice typing started. Say 'stop typing' to finish.")
            return self._dictate_to_active_window()
        except Exception:
            return "Voice typing failed. Please try again."

    def _dictation_post_process(self, text: str) -> str:
        """Convert simple spoken punctuation commands to characters."""
        try:
            t = text.strip()
            # Inline control phrases
            inline_map = {
                " new line ": "\n",
                " newline ": "\n",
                " next line ": "\n",
            }
            padded = f" {t} "
            for k, v in inline_map.items():
                padded = padded.replace(k, f"{v}")
            t = padded.strip()

            # Punctuation at end or inline
            punctuation_map = {
                " period": ".",
                " full stop": ".",
                " comma": ",",
                " question mark": "?",
                " exclamation mark": "!",
                " exclamation point": "!",
                " colon": ":",
                " semicolon": ";",
            }
            for src, dst in punctuation_map.items():
                if t.endswith(src):
                    t = t[: -len(src)] + dst
            return t
        except Exception:
            return text

    def _insert_text_via_clipboard(self, text: str) -> bool:
        """Paste text into the current focused window using the clipboard (Windows)."""
        try:
            import win32clipboard
            import win32con as _wcon
            # Set clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(_wcon.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            # Ensure focus and paste (try twice)
            try:
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.05)
                if text and not text.endswith("\n"):
                    # small space to keep words separated
                    pyautogui.typewrite(" ")
            except Exception:
                # Fallback to low-level key events
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord('V'), 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception:
            try:
                pyautogui.typewrite(text + (" " if not text.endswith("\n") else ""))
                return True
            except Exception:
                return False

    def _dictate_to_active_window(self) -> str:
        """Continuously listen and type into the active window until 'stop typing' is heard."""
        try:
            pyautogui.FAILSAFE = False
            while True:
                said = self.listen(phrase_time_limit=10).strip()
                if not said:
                    continue
                low = said.lower()
                print(f"Dictation heard: {said}")
                if "stop typing" in low or "stop dictation" in low or "that's it" in low:
                    self.speak("Stopped typing.")
                    return "Stopped typing."
                if low in ("enter",):
                    pyautogui.press("enter")
                    continue
                if low in ("tab", "press tab"):
                    pyautogui.press("tab")
                    continue
                if low in ("backspace", "delete last", "undo"):
                    pyautogui.press("backspace")
                    continue
                # Post-process punctuation suffixes
                out = self._dictation_post_process(said)
                # Use clipboard paste for robustness; preserve line breaks
                to_insert = out + (" " if not out.endswith("\n") else "")
                self._insert_text_via_clipboard(to_insert)
        except Exception:
            return "Dictation ended."

    def _focus_app_window(self, app_name: str) -> bool:
        """Attempt to bring the target application's window to the foreground."""
        try:
            target_classes = []
            title_keywords = []
            a = (app_name or "").lower()
            if a == "notepad" or a == "notes":
                target_classes = ["Notepad"]
                title_keywords = ["notepad"]
            elif a == "word":
                title_keywords = ["word", "document"]
            else:
                title_keywords = [a]

            focused = False

            def enum_handler(hwnd, _):
                nonlocal focused
                if focused:
                    return
                if not win32gui.IsWindowVisible(hwnd):
                    return
                try:
                    cls = win32gui.GetClassName(hwnd)
                except Exception:
                    cls = ""
                title = win32gui.GetWindowText(hwnd) or ""
                low_title = title.lower()
                class_ok = (not target_classes) or (cls in target_classes)
                title_ok = any(k in low_title for k in title_keywords if k)
                if class_ok and title_ok:
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        # Hack to allow foreground change
                        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                        win32gui.SetForegroundWindow(hwnd)
                        focused = True
                    except Exception:
                        pass

            win32gui.EnumWindows(enum_handler, None)
            if not focused:
                # As a last resort, click at current mouse to ensure some focus
                try:
                    pyautogui.click()
                except Exception:
                    pass
            return focused
        except Exception:
            return False

    # ---------- Core NLU-lite ----------
    def process_command(self, raw: str) -> str:
        if not raw or not raw.strip():
            return "I didn't catch that. Try again."

        command = raw.lower().strip()
        
        # Debug output
        print(f"Processing command: '{command}'")


        # Greetings
        if re.search(r"\b(hello|hey|hi|namaste|hello nova|hey nova|hi nova)\b", command):
            msg = "Hello! I’m Nova. What can I do for you?"
            return msg


        # Toggle voice
        if "mute" in command or "stop speaking" in command:
            self.voice_enabled = False
            return "Voice disabled."
        if "unmute" in command or "speak" in command and "don't" not in command:
            self.voice_enabled = True
            self.speak("Voice enabled.")
            return "Voice enabled."

        # Date / Time
        if "time" in command:
            now = datetime.now().strftime("%I:%M %p")
            msg = f"The time is {now}."
            return msg
        if "date" in command or "day" in command:
            today = datetime.now().strftime("%A, %d %B %Y")
            msg = f"Today is {today}."
            return msg

        # Wake-word inline: if user typed/says leading 'nova', strip it
        if command.startswith("nova "):
            command = command[5:].strip()

        # Wake word controls
        if command in ("start nova", "start wake word", "enable nova", "start listening"):
            self.start_wake_word()
            return "Nova is now listening."
        if command in ("stop nova", "stop wake word", "disable nova", "stop listening"):
            self.stop_wake_word()
            return "Nova stopped listening."

        # YouTube search - check this BEFORE quick opens
        if command.startswith("youtube ") or command.startswith("play on youtube "):
            q = raw.split(" ", 1)[1]
            self._open_search("youtube", q)
            msg = f"Searching YouTube for {q}."
            self.speak(msg)
            return msg
        
        # YouTube search with "open youtube and search" pattern
        if "open youtube and search" in command:
            q = raw.split("open youtube and search", 1)[1].strip()
            if q:
                result = self._open_search("youtube", q)
                if result:
                    msg = f"Searching YouTube for {q}."
                else:
                    msg = f"Failed to search YouTube for {q}."
                self.speak(msg)
                return msg
            else:
                return "What would you like to search on YouTube?"
        
        # YouTube search with "search on youtube" pattern
        if "search on youtube" in command:
            q = raw.split("search on youtube", 1)[1].strip()
            if q:
                self._open_search("youtube", q)
                msg = f"Searching YouTube for {q}."
                self.speak(msg)
                return msg
            else:
                return "What would you like to search on YouTube?"
        
        # YouTube search with "youtube search" pattern
        if "youtube search" in command:
            q = raw.split("youtube search", 1)[1].strip()
            if q:
                self._open_search("youtube", q)
                msg = f"Searching YouTube for {q}."
                self.speak(msg)
                return msg
            else:
                return "What would you like to search on YouTube?"

        # Quick opens (no manual links) - check this AFTER YouTube search
        for key in self.quick_sites.keys():
            if f"open {key}" in command or command.strip() == key:
                self._open_quick(key)
                msg = f"Opening {key}."
                self.speak(msg)
                return msg

        # Web search
        if command.startswith("search ") or command.startswith("google "):
            q = raw.split(" ", 1)[1]
            self._open_search("google", q)
            msg = f"Here’s what I found for {q}."
            self.speak(msg)
            return msg

        # Maps
        if command.startswith("maps ") or "directions to" in command or "navigate to" in command:
            q = raw.replace("maps", "").replace("directions to", "").replace("navigate to", "").strip()
            if not q:
                return "Where do you want to go?"
            self._open_search("maps", q)
            msg = f"Opening map results for {q}."
            self.speak(msg)
            return msg

        # Wikipedia
        if "wikipedia" in command or command.startswith("who is") or command.startswith("what is"):
            topic = raw.replace("wikipedia", "").replace("who is", "").replace("what is", "").strip()
            if not topic:
                return "Tell me a topic to look up on Wikipedia."
            try:
                wikipedia.set_lang("en")
                summary = wikipedia.summary(topic, sentences=2, auto_suggest=True, redirect=True)
                self.speak(summary)
                return summary
            except Exception:
                msg = f"I couldn’t find a concise Wikipedia summary for “{topic}”."
                return msg

        # Weather (free, no API key) -> wttr.in
        if "weather" in command:
            city = raw.replace("weather", "").replace("in", "").strip()
            city = city if city else "your city"
            try:
                url = f"https://wttr.in/{quote_plus(city)}?format=3"
                res = requests.get(url, timeout=6)
                text = res.text if res.ok else f"Weather lookup failed for {city}."
                self.speak(text)
                return text
            except Exception:
                msg = "I couldn’t fetch the weather right now."
                return msg

        # System apps and utilities
        system_apps = {
            "calculator": "Calculator",
            "notepad": "Notepad",
            "notes": "Notes",
            "control panel": "Control Panel",
            "command prompt": "Command Prompt",
            "cmd": "Command Prompt",
            "powershell": "PowerShell",
            "task manager": "Task Manager",
            "device manager": "Device Manager",
            "registry editor": "Registry Editor",
            "services": "Services",
            "word": "Microsoft Word",
            "excel": "Microsoft Excel",
            "powerpoint": "Microsoft PowerPoint",
            "paint": "Paint",
            "media player": "Media Player",
            "browser": "Default Browser"
        }
        
        for app_key, app_name in system_apps.items():
            if f"open {app_key}" in command:
                if self._system_open(app_key):
                    self.speak(f"Opening {app_name}.")
                    return f"Opening {app_name}."
                else:
                    return f"I couldn't open {app_name}."

        # Voice-to-text functionality
        if "open notepad for typing" in command or "open word for typing" in command:
            app = "notepad" if "notepad" in command else "word"
            return self._voice_to_text_app(app)
        if command in ("start", "start typing", "voice typing", "start dictation", "dictation mode"):
            return self._start_voice_typing()
        
        # (moved up) explicit dictation triggers handled above

        # Application Control
        if command in ("close youtube", "close the youtube", "close youtube tab", "close youtube tabs", "close youtube video"):
            if self._close_youtube_tabs():
                self.speak("Closing YouTube tabs.")
                return "Closing YouTube tabs."
            # Fallback: close the browser entirely
            for browser in ("chrome", "edge", "firefox"):
                if self._close_application(browser):
                    self.speak(f"Closing {browser}.")
                    return f"Closing {browser}."
            return "Could not close YouTube."

        # Close drive windows in Explorer
        close_drive_patterns = [
            r"close drive ([a-z])",
            r"close ([a-z]) drive",
            r"close ([a-z]):",
            r"close drive ([a-z]):",
            r"close ([a-z]) disk",
        ]
        for pattern in close_drive_patterns:
            m = re.search(pattern, command)
            if m:
                drive = m.group(1).upper()
                if self._close_explorer_drive(drive):
                    self.speak(f"Closing {drive}: drive windows.")
                    return f"Closing {drive}: drive windows."
                else:
                    return f"No open windows found for {drive}: drive."

        if command.startswith("close "):
            app_name = command.split("close ", 1)[1].strip()
            if app_name == "youtube":
                if self._close_youtube_tabs():
                    self.speak("Closing YouTube tabs.")
                    return "Closing YouTube tabs."
                for browser in ("chrome", "edge", "firefox"):
                    if self._close_application(browser):
                        self.speak(f"Closing {browser}.")
                        return f"Closing {browser}."
                return "Could not close YouTube."
            # Normalize aliases for common apps
            alias_map = {
                "control panel": "control panel",
                "command prompt": "cmd",
                "cmd": "cmd",
                "file explorer": "explorer",
                "whatsapp": "whatsapp",
                "powershell": "powershell",
                "chrome": "chrome",
                "edge": "edge",
                "firefox": "firefox",
                "notepad": "notepad",
                "word": "word",
                "excel": "excel",
                "powerpoint": "powerpoint",
                "paint": "paint",
                "calculator": "calculator",
                "explorer": "explorer",
            }
            norm_name = alias_map.get(app_name, app_name)
            # Close a file by matching its name in window titles
            if norm_name.startswith("file "):
                filename = norm_name.replace("file ", "").strip()
                candidates = [filename]
                try:
                    name_only = os.path.splitext(filename)[0]
                    if name_only and name_only != filename:
                        candidates.append(name_only)
                except Exception:
                    pass
                for key in candidates:
                    if key and self._close_windows_by_title(key):
                        self.speak(f"Closing file window for {filename}.")
                        return f"Closing file window for {filename}."
                return f"Could not find a window for {filename}."
            # Try process-based close with normalized name
            if self._close_application(norm_name):
                self.speak(f"Closing {norm_name}.")
                return f"Closing {norm_name}."
            # Fallback: attempt by window title
            if self._close_windows_by_title(app_name):
                self.speak(f"Closing {app_name}.")
                return f"Closing {app_name}."
            return f"Could not find or close {app_name}."

        # Close File (if it's a file)
        if command.startswith("close file "):
            filename = command.split("close file ", 1)[1].strip()
            # For files, we can't really "close" them programmatically
            # But we can try to close the application that might be using them
            return f"Cannot close file {filename} directly. Try closing the application that opened it."

        # Close Folder (if it's a folder)
        if command.startswith("close folder "):
            foldername = command.split("close folder ", 1)[1].strip()
            return f"Cannot close folder {foldername} directly. Close the File Explorer window instead."

        # Close Browser Tabs/Windows
        if "close browser" in command or "close chrome" in command or "close firefox" in command:
            browser = "chrome" if "chrome" in command else "firefox" if "firefox" in command else "browser"
            if self._close_application(browser):
                self.speak(f"Closing {browser}.")
                return f"Closing {browser}."
            else:
                return f"Could not close {browser}."

        # Close All Windows of an App
        if "close all" in command:
            app_name = command.replace("close all", "").strip()
            if app_name:
                if self._close_application(app_name):
                    self.speak(f"Closing all {app_name} windows.")
                    return f"Closing all {app_name} windows."
                else:
                    return f"Could not close {app_name}."
            else:
                return "Please specify which application to close."

        # Volume Control
        if "mute" in command and "volume" in command:
            if self._control_volume("mute"):
                self.speak("Volume muted.")
                return "Volume muted."
            else:
                return "Could not mute volume."
        elif "unmute" in command and "volume" in command:
            if self._control_volume("unmute"):
                self.speak("Volume unmuted.")
                return "Volume unmuted."
            else:
                return "Could not unmute volume."
        elif "increase volume" in command or "volume up" in command:
            if self._control_volume("increase", 20):
                self.speak("Volume increased.")
                return "Volume increased."
            else:
                return "Could not increase volume."
        elif "decrease volume" in command or "volume down" in command:
            if self._control_volume("decrease", 20):
                self.speak("Volume decreased.")
                return "Volume decreased."
            else:
                return "Could not decrease volume."

        # Brightness Control
        if "increase brightness" in command or "brightness up" in command:
            if self._control_brightness("increase"):
                self.speak("Brightness increased.")
                return "Brightness increased."
            else:
                return "Could not increase brightness."
        elif "decrease brightness" in command or "brightness down" in command:
            if self._control_brightness("decrease"):
                self.speak("Brightness decreased.")
                return "Brightness decreased."
            else:
                return "Could not decrease brightness."

        # System Actions
        if "shutdown" in command or "shut down" in command:
            if self._system_action("shutdown"):
                self.speak("Shutting down the system.")
                return "Shutting down the system."
            else:
                return "Could not shutdown the system."
        elif "restart" in command:
            if self._system_action("restart"):
                self.speak("Restarting the system.")
                return "Restarting the system."
            else:
                return "Could not restart the system."
        elif "lock" in command and "computer" in command:
            if self._system_action("lock"):
                self.speak("Locking the computer.")
                return "Locking the computer."
            else:
                return "Could not lock the computer."
        elif "log off" in command or "logout" in command:
            if self._system_action("logoff"):
                self.speak("Logging off.")
                return "Logging off."
            else:
                return "Could not log off."
        elif "sleep" in command and "computer" in command:
            if self._system_action("sleep"):
                self.speak("Putting computer to sleep.")
                return "Putting computer to sleep."
            else:
                return "Could not put computer to sleep."

        # Screenshot
        if "screenshot" in command or "take screenshot" in command:
            if self._take_screenshot():
                self.speak("Screenshot taken.")
                return "Screenshot taken and saved. Check the console for details."
            else:
                return "Could not take screenshot. Please try again."

        # Task Manager Functions
        if "list running apps" in command or "show running apps" in command:
            apps = self._get_running_apps()
            if apps:
                app_list = "\n".join(apps[:10])  # Show top 10
                self.speak("Here are the running applications.")
                return f"Running applications:\n{app_list}"
            else:
                return "Could not get list of running applications."

        if command.startswith("kill ") or command.startswith("end "):
            process_name = command.split(" ", 1)[1].strip()
            if self._kill_process(process_name):
                self.speak(f"Killed {process_name}.")
                return f"Killed {process_name}."
            else:
                return f"Could not kill {process_name}."

        # Media File Playback
        if command.startswith("play "):
            filename = command.split("play ", 1)[1].strip()
            if self._play_media_file(filename):
                self.speak(f"Playing {filename}.")
                return f"Playing {filename}."
            else:
                return f"Could not play {filename}."

        # Email and Messaging
        if "send email" in command:
            # Extract email details from command
            if "to" in command and "subject" in command:
                parts = command.split("to")[1].split("subject")
                to_email = parts[0].strip()
                subject_part = parts[1].split("body")[0].strip() if "body" in parts[1] else parts[1].strip()
                body = parts[1].split("body")[1].strip() if "body" in parts[1] else "Hello!"
                
                if self._send_email(to_email, subject_part, body):
                    self.speak(f"Sending email to {to_email}.")
                    return f"Sending email to {to_email} with subject: {subject_part}"
                else:
                    return "Could not send email."
            else:
                return "Please specify: send email to [email] subject [subject] body [message]"

        # News and Updates
        if "news" in command:
            topic = command.replace("news", "").replace("get", "").replace("show", "").strip()
            if not topic:
                topic = "general"
            news = self._get_news(topic)
            self.speak(news)
            return news

        # Calendar and Date Information
        if "calendar" in command or "schedule" in command:
            calendar_info = self._get_calendar_info()
            self.speak(calendar_info)
            return calendar_info

        # Translation
        if "translate" in command:
            if "to" in command:
                parts = command.split("translate")[1].split("to")
                text = parts[0].strip()
                target_lang = parts[1].strip()
                
                # Map common language names to codes
                lang_map = {
                    "spanish": "es", "french": "fr", "german": "de", "italian": "it",
                    "portuguese": "pt", "russian": "ru", "chinese": "zh", "japanese": "ja",
                    "korean": "ko", "arabic": "ar", "hindi": "hi", "english": "en"
                }
                target_lang = lang_map.get(target_lang.lower(), target_lang)
                
                result = self._translate_text(text, target_lang)
                return result
            else:
                return "Please specify: translate [text] to [language]"

        # Entertainment Features
        if "tell me a joke" in command or "joke" in command:
            joke = self._tell_joke()
            self.speak(joke)
            return joke

        if "fun fact" in command or "tell me a fact" in command:
            fact = self._tell_fun_fact()
            self.speak(fact)
            return fact

        if "read pdf" in command:
            filename = command.split("read pdf")[1].strip()
            result = self._read_pdf(filename)
            return result

        if "play music" in command:
            query = command.replace("play music", "").strip()
            if query:
                result = self._play_music_from_youtube(query)
                return result
            else:
                return "What music would you like to play?"

        # General Knowledge Questions
        if command.startswith("what is") or command.startswith("who is") or command.startswith("how does") or command.startswith("why"):
            question = raw.strip()
            result = self._get_general_knowledge(question)
            return result

        # File and folder operations
        if command.startswith("open file "):
            filename = raw.split("open file ", 1)[1].strip()
            if os.path.exists(filename):
                if self._open_file(filename):
                    self.speak(f"Opening file {filename}.")
                    return f"Opening file {filename}."
                else:
                    return f"I couldn't open the file {filename}."
            else:
                # Try to find the file
                found_file = self._find_file(filename)
                if found_file:
                    if self._open_file(found_file):
                        self.speak(f"Found and opening {found_file}.")
                        return f"Found and opening {found_file}."
                    else:
                        return f"I found {found_file} but couldn't open it."
                else:
                    return f"I couldn't find the file {filename}."

        if command.startswith("open folder ") or command.startswith("open directory "):
            folderpath = raw.split("open folder ", 1)[1].strip() if "open folder" in command else raw.split("open directory ", 1)[1].strip()
            if os.path.exists(folderpath) and os.path.isdir(folderpath):
                if self._open_folder(folderpath):
                    self.speak(f"Opening folder {folderpath}.")
                    return f"Opening folder {folderpath}."
                else:
                    return f"I couldn't open the folder {folderpath}."
            else:
                return f"The folder {folderpath} doesn't exist."

        # Common folder shortcuts - use direct Windows commands
        if command == "open downloads" or command == "open download":
            # Use Windows shell command for Downloads
            try:
                subprocess.Popen(["explorer", "shell:Downloads"])
                self.speak("Opening Downloads folder.")
                return "Opening Downloads folder."
            except:
                # Fallback to standard path
                downloads_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Downloads')
                if self._open_folder(downloads_path):
                    self.speak("Opening Downloads folder.")
                    return "Opening Downloads folder."
                else:
                    return "I couldn't open the Downloads folder."
        elif command == "open documents" or command == "open document":
            # Use Windows shell command for Documents
            try:
                subprocess.Popen(["explorer", "shell:Documents"])
                self.speak("Opening Documents folder.")
                return "Opening Documents folder."
            except:
                # Fallback to standard path
                documents_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Documents')
                if self._open_folder(documents_path):
                    self.speak("Opening Documents folder.")
                    return "Opening Documents folder."
                else:
                    return "I couldn't open the Documents folder."
        elif command == "open desktop":
            # Use Windows shell command for Desktop
            try:
                subprocess.Popen(["explorer", "shell:Desktop"])
                self.speak("Opening Desktop folder.")
                return "Opening Desktop folder."
            except:
                # Fallback to standard path
                desktop_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
                if self._open_folder(desktop_path):
                    self.speak("Opening Desktop folder.")
                    return "Opening Desktop folder."
                else:
                    return "I couldn't open the Desktop folder."
        elif command == "open pictures" or command == "open picture":
            # Use Windows shell command for Pictures
            try:
                subprocess.Popen(["explorer", "shell:Pictures"])
                self.speak("Opening Pictures folder.")
                return "Opening Pictures folder."
            except:
                # Fallback to standard path
                pictures_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Pictures')
                if self._open_folder(pictures_path):
                    self.speak("Opening Pictures folder.")
                    return "Opening Pictures folder."
                else:
                    return "I couldn't open the Pictures folder."
        elif command == "open music":
            # Use Windows shell command for Music
            try:
                subprocess.Popen(["explorer", "shell:Music"])
                self.speak("Opening Music folder.")
                return "Opening Music folder."
            except:
                # Fallback to standard path
                music_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Music')
                if self._open_folder(music_path):
                    self.speak("Opening Music folder.")
                    return "Opening Music folder."
                else:
                    return "I couldn't open the Music folder."
        elif command == "open videos" or command == "open video":
            # Use Windows shell command for Videos
            try:
                subprocess.Popen(["explorer", "shell:Videos"])
                self.speak("Opening Videos folder.")
                return "Opening Videos folder."
            except:
                # Fallback to standard path
                videos_path = os.path.join(os.environ.get('USERPROFILE', ''), 'Videos')
                if self._open_folder(videos_path):
                    self.speak("Opening Videos folder.")
                    return "Opening Videos folder."
                else:
                    return "I couldn't open the Videos folder."
        elif command == "open home":
            # Use direct Windows user profile path
            home_path = os.environ.get('USERPROFILE', '')
            if self._open_folder(home_path):
                self.speak("Opening Home folder.")
                return "Opening Home folder."
            else:
                return "I couldn't open the Home folder."

        # Drive operations (Windows)
        # Handle various drive command patterns
        drive_patterns = [
            r"open drive ([a-z])",
            r"open disk ([a-z])", 
            r"open ([a-z]) drive",
            r"open ([a-z]) disk",
            r"open ([a-z]):",
            r"open drive ([a-z]):",
            r"open disk ([a-z]):"
        ]
        
        for pattern in drive_patterns:
            match = re.search(pattern, command)
            if match:
                drive = match.group(1).upper()
                if self._open_drive(drive):
                    self.speak(f"Opening drive {drive}.")
                    return f"Opening drive {drive}."
                else:
                    return f"I couldn't open drive {drive}."

        # File explorer
        if "open file explorer" in command or "open explorer" in command:
            if self._open_folder(os.path.expanduser("~")):
                self.speak("Opening File Explorer.")
                return "Opening File Explorer."
            else:
                return "I couldn't open File Explorer."

        # File type specific commands
        file_types = {
            "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"],
            "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
            "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
            "document": [".pdf", ".doc", ".docx", ".txt", ".rtf"],
            "spreadsheet": [".xls", ".xlsx", ".csv"],
            "presentation": [".ppt", ".pptx"]
        }
        
        for file_type, extensions in file_types.items():
            if f"open {file_type}" in command:
                # Try to find files of this type in common locations
                found_files = []
                for ext in extensions:
                    for root, dirs, files in os.walk(os.path.expanduser("~/Downloads")):
                        for file in files:
                            if file.lower().endswith(ext):
                                found_files.append(os.path.join(root, file))
                                if len(found_files) >= 5:  # Limit to 5 files
                                    break
                        if len(found_files) >= 5:
                            break
                    if len(found_files) >= 5:
                        break
                
                if found_files:
                    # Open the most recent file
                    latest_file = max(found_files, key=os.path.getmtime)
                    if self._open_file(latest_file):
                        self.speak(f"Opening {file_type} file.")
                        return f"Opening {file_type} file: {os.path.basename(latest_file)}"
                    else:
                        return f"I found {file_type} files but couldn't open them."
                else:
                    return f"No {file_type} files found in Downloads folder."

        # Fallback → do a web search
        try:
            wikipedia.set_lang("en")
            summary = wikipedia.summary(raw, sentences=2, auto_suggest=True, redirect=True)
            self.speak(summary)
            return summary
        except Exception:
            msg = f"Sorry, I couldn’t find a clear answer for “{raw}”."
            return msg
