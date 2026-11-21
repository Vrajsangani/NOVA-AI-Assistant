# NOVA AI Assistant

A Python-based desktop voice assistant that listens to spoken commands, responds with text and speech, opens websites and applications, and performs selected desktop, file, and system operations.

> **Project status:** Personal/educational project. The uploaded source contains the assistant's core logic (`Assistant` class). A separate application entry point or GUI file was not included in the supplied code, so the launch instructions below assume you will add/use your own `main.py` or UI integration.

## Features

### Voice interaction
- Speech recognition using `SpeechRecognition` and Google's online recognition service.
- Text-to-speech responses using `pyttsx3`.
- Configurable wake word (`nova`) with background listening.
- Optional microphone selection.
- Basic ambient-noise adjustment and noise reduction with `noisereduce`.
- Voice enable/disable controls.

### Web and information
- Opens frequently used websites such as Google, YouTube, Gmail, Maps, GitHub, Wikipedia, and others.
- Performs Google, YouTube, and Maps searches.
- Retrieves short Wikipedia summaries.
- Requests weather information from `wttr.in`.
- Opens Google Translate with supplied text.
- Includes calendar/date/time responses, jokes, and fun facts.

### Desktop and system control
- Opens supported applications and system utilities.
- Opens files, folders, common user folders, and drives.
- Searches common user folders for files.
- Takes screenshots.
- Lists running processes and can terminate selected processes.
- Controls volume and supported brightness keys.
- Supports shutdown, restart, lock, logoff, and sleep commands.
- Supports voice dictation into the active application, including basic spoken punctuation.

### Documents and media
- Extracts text from PDF files and reads a short excerpt aloud.
- Opens local audio/video files with the system's default application.
- Searches YouTube for music.

## Technology stack

- **Language:** Python
- **Speech recognition:** SpeechRecognition
- **Text-to-speech:** pyttsx3
- **Audio processing:** NumPy, noisereduce, PyAudio (microphone backend)
- **Desktop automation:** PyAutoGUI, psutil
- **Windows integration:** pywin32, ctypes
- **Web and parsing:** requests, wikipedia, BeautifulSoup
- **PDF processing:** PyPDF2

## Project structure

A suggested repository layout:

```text
NOVA-AI-Assistant/
├── main.py                 # Application entry point
├── assistant.py            # Core Assistant class from the supplied source
├── requirements.txt        # Python dependencies
├── README.md
├── .gitignore
└── assets/                 # Optional screenshots, icons, or demo media
```

## Requirements

- Python 3.10 is a sensible starting point; use the Python version with which you have tested the project.
- A working microphone and speakers/headphones.
- Internet connection for online speech recognition, Wikipedia, weather lookup, and web services.
- Windows is the most complete target environment for the supplied implementation. Some application-opening branches include macOS/Linux alternatives, but several features rely on Windows APIs and will not work cross-platform as written.

Install the Python packages:

```bash
python -m pip install numpy SpeechRecognition pyttsx3 requests wikipedia noisereduce psutil PyAutoGUI pywin32 PyPDF2 beautifulsoup4
```

Install a working PyAudio build for your Python version and operating system if `SpeechRecognition` cannot access the microphone:

```bash
python -m pip install PyAudio
```

If PyAudio installation fails on Windows, use a compatible wheel/build for your exact Python version and architecture, or follow the current PyAudio installation instructions.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/<your-username>/<your-repository>.git
   cd <your-repository>
   ```

2. (Recommended) Create and activate a virtual environment:

   **Windows PowerShell**
   ```powershell
   py -3.10 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS/Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies using the commands in the Requirements section.

4. Add your launcher/UI file (for example, `main.py`) and make sure it imports the assistant class correctly:

   ```python
   from assistant import Assistant

   assistant = Assistant()
   print(assistant.process_command("hello"))
   ```

5. Run your actual application entry point, for example:

   ```bash
   python main.py
   ```

   The supplied core file does not itself show a top-level launcher, so `python assistant.py` may not start an interactive application.

## Example voice/text commands

| Say or type | Expected action |
|---|---|
| `Hello Nova` | Responds to a greeting |
| `Nova, what time is it?` | Gives the current time |
| `Start listening` | Starts wake-word listening |
| `Stop listening` | Stops wake-word listening |
| `Open YouTube` | Opens YouTube |
| `Search Python tutorials` | Opens Google search results |
| `YouTube machine learning` | Searches YouTube |
| `Weather in Surat` | Requests weather information |
| `Open calculator` | Opens Calculator where supported |
| `Open downloads` | Opens the Downloads folder |
| `Take screenshot` | Attempts to capture a screenshot |
| `Increase volume` | Sends volume-up key events |
| `Tell me a joke` | Speaks a random joke |
| `Read PDF report.pdf` | Attempts to extract and speak PDF text |
| `Start typing` | Starts voice dictation; say `stop typing` to finish |

The command parser uses phrase matching, so wording and operating-system support can affect results.

## Important notes and limitations

- **Online speech recognition:** `recognize_google` sends audio to Google's speech-recognition service. A working internet connection is required; review the service's current terms and privacy practices before use.
- **Microphone access:** Grant microphone permission to your terminal/Python environment. Check the selected input device if recognition returns empty results.
- **Windows-specific functionality:** Process/window control, keyboard events, clipboard typing, and several system commands use Windows APIs or `pywin32`. These features are not guaranteed on macOS/Linux.
- **System actions are powerful:** Commands can close applications, terminate processes, log off, put the computer to sleep, restart, or shut down the machine. Test carefully and avoid running untrusted commands.
- **Process termination:** The implementation can terminate processes by name. It may close unsaved work and can fail when permissions are insufficient.
- **News feature:** The current code returns sample/hard-coded news messages; it does not currently retrieve live news. The placeholder NewsAPI URL uses a demo key and should not be treated as a working integration.
- **Email feature:** The current implementation opens a pre-filled Gmail compose page; it does not send email automatically.
- **Weather and external services:** Availability and response formats depend on third-party services and internet access.
- **PDF support:** Text extraction may not work for scanned/image-only PDFs. The code limits spoken PDF text to a short excerpt.
- **Secrets:** Do not commit API keys, passwords, personal tokens, or private configuration files. Use environment variables for any future credentials.
- **Review before public release:** Check all commands and dependencies, remove unused imports, handle exceptions visibly, and test on a clean environment.

## Safety and privacy

NOVA can listen through the microphone and interact with local applications and files. Run it only on a device you control. Stop wake-word listening when it is not needed, avoid using it in sensitive conversations, and review commands before enabling destructive system actions. Do not run the project with elevated administrator privileges unless a specific feature genuinely requires it.

## Troubleshooting

- **`ModuleNotFoundError`:** Activate the virtual environment and install the missing dependency.
- **Microphone not found / `PyAudio` error:** Verify the microphone in Windows sound settings and install a PyAudio build compatible with your Python version.
- **No speech detected:** Check microphone permissions, input device selection, internet connectivity, and background noise.
- **Text-to-speech is silent:** Check system audio output and the installed voices available to `pyttsx3`.
- **A desktop command does not work:** Confirm the application is installed and that the command is supported on your operating system.
- **`win32*` import errors:** Install `pywin32` on Windows and ensure the Python environment running the app is the one where it was installed.

## Future improvements

- Separate command handlers into modules and remove duplicate/unused imports.
- Add unit tests and structured logging.
- Add confirmation prompts for shutdown, restart, logoff, process termination, and other destructive actions.
- Replace sample news responses with a properly configured news provider.
- Add configurable settings for wake word, language, microphone, and voice.
- Improve command parsing and add a help/list-commands feature.



## Maintainer: `Vraj Sangani`  
## Repository: `https://github.com/Vrajsangani/NOVA-AI-Assistant`
