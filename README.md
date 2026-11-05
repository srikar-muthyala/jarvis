# J.A.R.V.I.S. ⚡
### Just A Rather Very Intelligent System — Cross-Platform AI Desktop Assistant

> An authentic, Stark-inspired AI voice & desktop assistant for **Windows** and **Linux** featuring a buttery-smooth 60–120 FPS floating Dynamic Island widget, multimodal screen perception, proactive ambient telemetry, deep web research, email summaries, and Google Tasks & Calendar synchronization.

---

## 🌟 Key Architecture

- **Dynamic Spring-Width Island HUD**: Minimalist Monochrome Stark Arc Reactor pill anchored at top-center. Built with Euler spring physics, resting at a snug 118px and dynamically blooming to 176px during voice capture or playback to reveal a 4-bar dynamic audio visualizer with zero dead space.
- **Dual Voice Synthesis (TTS)**:
  - **Zero-Setup Default**: Free high-definition British neural voice (**Microsoft Edge-TTS** `en-GB-RyanNeural`). No API key or credit card required.
  - **Zero-Shot Voice Cloning**: Optional high-fidelity Paul Bettany voice cloning via **Fish Audio API**.
  - **Offline Fallback**: Windows SAPI5 / Linux local speech synthesis.
- **On-Device Speech Recognition (STT)**: Real-time local **Faster-Whisper** (`base.en` / `small.en`) running GPU/CPU on-device with zero cloud latency.
- **Dual-Engine AI Brain**: Multi-step tool-calling agent powered by **Google Gemini 2.5 / 3.1 Flash-Lite** and **Nex-N 2.5** (via OpenRouter or local Ollama). Features instant bidirectional fallback: if rate limits, quota issues (429), or network dropouts occur on one engine, J.A.R.V.I.S. seamlessly switches to the backup engine without dropping your prompt.
- **Headless Web Engine**: Integrated **Lightpanda Browser** for fast, JavaScript-rendered web scraping, search synthesis, and web page reading.
- **Cross-Platform**: Fully operational on Windows 10/11 and modern Linux distributions (Ubuntu, Debian, Fedora, Arch).

---

## 🚀 Capabilities & Voice Commands

### 1. 🎙️ Voice Interaction & Real-Time Barge-In (Interruption)
- Speaks with a calm, polite British cadence.
- **Zero-Latency Barge-In**: Interrupt J.A.R.V.I.S. mid-sentence:
  - **Spoken**: *"Jarvis, stop"*, *"Silence"*, *"Shut up"*, or *"Cancel"*.
  - **Keyboard**: Press <kbd>Esc</kbd> anytime.
  - **Mouse**: Click the speech response area inside the widget.

### 2. 👁️ Screen Perception & Multimodal Vision
J.A.R.V.I.S. inspects your active display to explain errors, code, or web pages:
- *"Jarvis, look at my screen"*
- *"What is visible on my display right now?"*
- *"Inspect my screen and help me debug this code"*
- *"Check the page opened and tell me what it says"*

### 3. 🛡️ Ambient System Telemetry & Proactive Alerts
Runs silently in the background and proactively speaks up when critical events occur:
- **Multi-Tier Battery Warning Sentinel**: Proactively alerts you as battery reserves deplete:
  - **25% (Low Battery)**: Polite reminder suggesting connecting the charger.
  - **20% (Very Low Battery)**: Caution alert indicating low reserves remaining.
  - **15% (Very Very Low Battery)**: Urgent warning urging power connection.
  - **10% (Critical Shutdown Imminent)**: High-priority Stark alert (*"We might shut down at any moment now. Connect the charger immediately"*).
- **Proactive Memory Sentinel & Optimizer**: Alerts when system RAM exceeds 90% (*"Notice, sir: system memory load is elevated at 93 percent. Would you like me to optimize memory and bring the load down?"*). When approved (*"yes"*, *"bring it down"*), silently calls Win32 `EmptyWorkingSet` across processes, immediately reclaiming 1–3 GB RAM without closing your applications.
- **Event Reminders**: Proactively alerts you 5 to 15 minutes before any scheduled Google Calendar event or Google Task begins.

### 4. 🔬 Deep Web Research Agent
Autonomous multi-source research agent that searches the web, navigates top results with the Lightpanda headless browser, synthesizes structured briefings, and saves a dossier to your computer:
- *"Deep research quantum computing breakthroughs"*
- *"Research solid-state battery advancements"*
- **Saved Dossiers**: Automatically written to `Documents/Jarvis/research_<topic>.md` with executive summaries, key findings, and cited sources.

### 5. 📋 Smart Clipboard Assistant
Instant AI operations on your active system clipboard without switching apps:
- *"Explain my clipboard"* — Analyzes whatever text or code is copied.
- *"Fix the grammar of what I copied"* — Polishes tone and replaces your clipboard automatically.
- *"Translate my clipboard to French"* (or Spanish, German, Japanese, etc.).
- *"Convert what I just copied to Python"* (or TypeScript, Go, Rust, JSON, SQL).

### 6. 🌅 Daily Morning Digest & Calendar Sync
- **First-Run Prompt**: On your first launch of the day, J.A.R.V.I.S. asks:
  > *"Good morning, sir. Would you like me to start with today's briefing?"*
- **Daily Digest Covers**:
  - Real-time weather, temperature, and precipitation chance.
  - Synchronized Google Calendar schedule & national holidays.
  - Pending Google Tasks and to-do items.
  - Unread priority emails.
- **On-Demand**: *"Daily digest"*, *"Brief me for today"*, *"Start my day"*.

### 7. 📬 Gmail & IMAP Email Automation
- **Inbox Summaries**: *"Check my email"*, *"Summarize my latest 5 emails"*.
- **Targeted Search**: *"Check for my latest emails from GitHub"*, *"Search emails for flight tickets"*.
- **One-Click Action Chips**: When an email contains a verification or portal link, J.A.R.V.I.S. renders an interactive chip (`🔗 Open portal`) right on the island.

### 8. 💻 System & Application Control
- **Open Apps / Websites**: *"Open Chrome and Spotify"*, *"Open YouTube in Brave"*, *"Launch VS Code"*.
- **Volume & Media**: *"Volume up / down"*, *"Set volume to 40%"*, *"Mute"*, *"Pause music"*, *"Next track"*.
- **OS Controls**: *"Lock the PC"*, *"Put computer to sleep"*, *"Show desktop"*, *"Take a screenshot"*.
- **Timers & Reminders**: *"Set a timer for 15 minutes"*, *"Remind me in 1 hour to drink water"*.

---

## 📦 Quick Installation

### Windows Installation
1. Ensure **Python 3.10 to 3.13** is installed from [python.org](https://www.python.org/downloads/) (make sure to check **"Add python.exe to PATH"**).
2. Clone this repository:
   ```cmd
   git clone https://github.com/your-username/jarvis.git
   cd jarvis
   ```
3. Run the automated setup script:
   ```cmd
   setup.bat
   ```
   *This automatically creates `.venv`, installs all dependencies, and creates `.env` from `.env.example`.*

### Linux Installation (Ubuntu, Debian, Fedora, Arch)
1. Install system prerequisites (Python venv, audio headers, Tkinter):
   - **Ubuntu/Debian**:
     ```bash
     sudo apt update
     sudo apt install -y python3 python3-venv python3-pip python3-tk portaudio19-dev libasound2-dev mpg123
     ```
   - **Fedora**:
     ```bash
     sudo dnf install -y python3 python3-pip python3-tkinter portaudio-devel alsa-lib-devel mpg123
     ```
   - **Arch Linux**:
     ```bash
     sudo pacman -S python python-pip tk portaudio alsa-lib mpg123
     ```
2. Clone this repository:
   ```bash
   git clone https://github.com/your-username/jarvis.git
   cd jarvis
   ```
3. Run the setup script:
   ```bash
   chmod +x setup.sh run.sh widget.sh chat.sh link_google_tasks.sh
   ./setup.sh
   ```

---

## ⚙️ Configuration Guide (`.env`)

Open `.env` in any text editor. All integrations are modular — configure only what you need.

```ini
# ==============================================================================
# J.A.R.V.I.S. Configuration
# ==============================================================================

# --- 1. Google Gemini API (Primary / Multimodal Vision) ---
# Get your free API key at: https://aistudio.google.com/app/apikey
LLM_API_KEY=your_gemini_api_key_here
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.1-flash-lite

# --- 2. Nex-N 2.5 API (Dual-Engine Fallback via OpenRouter or Ollama) ---
# Sign up at https://openrouter.ai/keys for a free or pay-as-you-go key
NEX_API_KEY=sk-or-v1-your_openrouter_key_here
NEX_BASE_URL=https://openrouter.ai/api/v1
NEX_MODEL=nex-agi/nex-n2.5-mini:free
# Or use local offline Ollama:
# NEX_BASE_URL=http://localhost:11434/v1
# NEX_MODEL=nex-n2.5-mini

# --- 3. Speech & Voice Synthesis ---
# High-definition British neural voice via Microsoft Edge-TTS (Free, no setup needed)
TTS_VOICE=en-GB-RyanNeural
TTS_RATE=+0%
TTS_PITCH=-2Hz

# --- 3. Optional: Fish Audio (Paul Bettany Voice Cloning) ---
# Sign up at https://fish.audio for zero-shot voice cloning.
# Leave blank to use the free built-in Edge-TTS Ryan voice above.
FISH_AUDIO_API_KEY=
FISH_AUDIO_VOICE_ID=88b183bfbdda44a09ad4474712b967f4
FISH_AUDIO_MODEL=s2.1-pro-free

# --- 4. Email Reading & Summaries (Optional) ---
# For Gmail: Generate a 16-character App Password at https://myaccount.google.com/apppasswords
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_APP_PASSWORD=your_16_char_app_password
EMAIL_IMAP_SERVER=imap.gmail.com

# --- 5. Google Calendar Sync (Optional) ---
# Paste your Secret iCal format address from Google Calendar Settings
GOOGLE_CALENDAR_URL=https://calendar.google.com/calendar/ical/your_email/private-xxxx/basic.ics

# --- 6. Speech Recognition (Whisper) ---
WHISPER_MODEL=base.en
MIC_DEVICE=
MIC_THRESHOLD=

# --- 7. Floating Dynamic Island Hotkey ---
WIDGET_HOTKEY=alt+space
```

---

## 🛠️ Step-by-Step Tool Integrations

### 1. Google Gemini Brain & Vision (Primary)
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with any Google account and click **"Create API key"**.
3. Copy the key and paste it into `.env` under `LLM_API_KEY=`.

---

### 2. Nex-N 2.5 Setup (OpenRouter & Ollama Fallback)
Jarvis uses a dual-engine brain. If Gemini encounters rate limits (HTTP 429) or temporary outages, Jarvis seamlessly fails over to Nex-N 2.5 without interrupting your conversation.

#### Option A: Via OpenRouter (Cloud)
1. Visit [OpenRouter](https://openrouter.ai/keys) and create a free account.
2. Generate an API Key (starts with `sk-or-v1-...`).
3. Add to your `.env`:
   ```ini
   NEX_API_KEY=sk-or-v1-your-key-here
   NEX_BASE_URL=https://openrouter.ai/api/v1
   NEX_MODEL=nex-agi/nex-n2.5-mini:free
   ```
   *(You can also use `nex-agi/nex-n2.5-pro` or other OpenRouter models).*

#### Option B: Via Local Ollama (100% Free & Offline)
1. Download [Ollama](https://ollama.com/) and pull your chosen model:
   ```bash
   ollama run nex-n2.5-mini
   ```
2. Configure `.env` to point to your local endpoint:
   ```ini
   NEX_API_KEY=ollama
   NEX_BASE_URL=http://localhost:11434/v1
   NEX_MODEL=nex-n2.5-mini
   ```

---

### 3. Google Calendar Integration
1. Open [Google Calendar](https://calendar.google.com/) in your browser.
2. In the left sidebar, hover over your primary calendar, click the three dots **⋮**, and select **Settings and sharing**.
3. Scroll down to the **Integrate calendar** section.
4. Locate **"Secret address in iCal format"** and copy the `.ics` URL.
   *(Warning: Keep this secret; do not share it).*
5. Paste this URL into `.env` under `GOOGLE_CALENDAR_URL=`.

---

### 4. Google Tasks Synchronization
Jarvis syncs your real-time to-do list from Google Tasks via official OAuth 2.0.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `Jarvis-Assistant`).
3. In the search bar, search for **"Google Tasks API"** and click **Enable**.
4. Navigate to **APIs & Services** -> **OAuth consent screen**:
   - Choose **External** user type and click **Create**.
   - Enter an app name (e.g. `Jarvis`) and your email address.
   - Click **Save and Continue** through the scopes screen.
   - Under **Test users**, add your own Google email address.
5. Navigate to **Credentials** -> **Create Credentials** -> **OAuth client ID**:
   - Application type: Select **Web application**.
   - Name: `Jarvis Desktop`.
   - Under **Authorized redirect URIs**, click **Add URI** and enter:
     ```text
     http://localhost:5678/rest/oauth2-credential/callback
     ```
   - Click **Create**.
6. Click **Download JSON** for your new client ID.
7. Rename the downloaded file to **`credentials.json`** and place it in the project root directory (refer to `credentials.json.example`).
8. Connect your account:
   - On Windows: Double-click **`link_google_tasks.bat`** (or run `.venv\Scripts\python.exe setup_google_tasks.py`).
   - On Linux: Run `./link_google_tasks.sh`.
9. A browser tab will open prompting you to grant access. Once authorized, a green checkmark will appear, and your credentials will be securely saved to `token.json` (which is git-ignored).

---

### 5. Gmail IMAP Reading
1. Ensure **2-Step Verification** is enabled on your Google account.
2. Visit [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Create a new App Password:
   - App name: `Jarvis`.
4. Copy the generated 16-character code (e.g., `abcd efgh ijkl mnop`).
5. In `.env`, set:
   ```ini
   EMAIL_ADDRESS=your_email@gmail.com
   EMAIL_APP_PASSWORD=abcd efgh ijkl mnop
   EMAIL_IMAP_SERVER=imap.gmail.com
   ```

---

### 6. Fish Audio Voice Cloning (Optional)
Jarvis comes out of the box with Microsoft Edge's authentic British neural voice (`en-GB-RyanNeural`), requiring no setup.

If you prefer custom zero-shot voice-cloned speech:
1. Create a free account at [fish.audio](https://fish.audio).
2. Generate an API Key under your profile settings.
3. In `.env`, set:
   ```ini
   FISH_AUDIO_API_KEY=your_key_here
   FISH_AUDIO_VOICE_ID=88b183bfbdda44a09ad4474712b967f4
   FISH_AUDIO_MODEL=s2.1-pro-free
   ```

---

## 🖥️ Launching J.A.R.V.I.S.

| Mode | Windows Command | Linux Command | Description |
| :--- | :--- | :--- | :--- |
| **Silent Windows Auto-Boot** | `python setup_autostart.py --enable` | Systemd service | Automatically starts Jarvis silently on system startup via `pythonw.exe`. |
| **Dynamic Island (Recommended)** | Double-click `widget.bat` | `./widget.sh` | 60 FPS floating desktop notch with Euler spring physics, live audio waveforms, and hotkeys. |
| **Always-Listening Mode** | Double-click `run.bat` | `./run.sh` | Hands-free wake word (*"Hey Jarvis..."*). |
| **Interactive Terminal Chat** | Double-click `chat.bat` | `./chat.sh` | Silent or spoken interactive conversation in terminal. |
| **Push-to-Talk (PTT)** | `python jarvis.py --ptt` | `python3 jarvis.py --ptt` | Speak while holding <kbd>Right Ctrl</kbd>. |

### Dynamic Island Hotkeys
- <kbd>Ctrl</kbd> + <kbd>Space</kbd> or <kbd>Alt</kbd> + <kbd>Space</kbd> or <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>J</kbd>: Toggle open/close and focus input.
- <kbd>Esc</kbd>: Cut off speech playback or collapse the widget.
- Hover cursor over the collapsed pill to peek at live telemetry and auto-collapse after 5 seconds of leaving.

---

## 🧪 Running Unit Tests

To verify local command parsing, app resolution, and wake-word regexes across 115 test cases:

```bash
# Windows
.venv\Scripts\python.exe test_commands.py

# Linux
./.venv/bin/python3 test_commands.py
```

---

## 📂 Project Architecture

```text
jarvis/
├── actions.py             # Cross-platform system automation, volume, apps, memory reclamation
├── generate_icon.py       # Stark Arc Reactor vector & antialiased icon renderer
├── jarvis.ico / .png      # High-DPI Windows application and tray icons
├── setup_autostart.py     # Windows Startup & Desktop silent auto-boot manager
├── audio.py               # Edge-TTS, Fish Audio, local Whisper capture, cross-platform audio
├── clipboard_helper.py    # Clipboard AI assistant (grammar, code conversion, translation)
├── commands.py            # Local regex intent parser & natural language routing
├── credentials.json.example # Template structure for Google Tasks OAuth 2.0
├── jarvis.py              # Assistant core coordinator & barge-in logic
├── lightpanda_browser.py  # Headless browser controller for JS-heavy web pages
├── link_google_tasks.bat  # Windows launcher for Google Tasks connection
├── link_google_tasks.sh   # Linux launcher for Google Tasks connection
├── llm.py                 # Gemini multimodal & tool-calling function declarations
├── proactive_monitor.py   # Background battery, RAM, and calendar sentinel
├── research_agent.py      # Multi-source web research & Markdown dossier compiler
├── run.bat / run.sh       # Hands-free background voice listener
├── setup.bat / setup.sh   # One-click environment bootstrap & dependency installer
├── setup_google_tasks.py  # Google Tasks OAuth 2.0 local loopback server
├── test_commands.py       # Comprehensive parser unit test suite (115 tests)
├── vision.py              # Win32 GDI / Pillow screen perception & Gemini vision
├── widget.bat / widget.sh # Desktop floating Dynamic Island launcher
├── widget.py              # 60-120 FPS Tkinter Dynamic Island desktop HUD
└── requirements.txt       # Dependencies with cross-platform platform markers
```

---

## 🔒 Security & Privacy

- **Never Commit Secrets**: `.env`, `credentials.json`, `token.json`, and `.daily_briefing.json` are strictly excluded in `.gitignore`.
- **Local Whisper Transcription**: Microphone audio is transcribed locally on your CPU/GPU using `faster-whisper`. No voice recordings are uploaded to third parties.
- **Direct Cloud Connections**: API calls to Google Gemini and Fish Audio connect directly via encrypted TLS HTTPS connections from your computer.

---

## 📄 License

MIT License. Designed with admiration for Tony Stark's J.A.R.V.I.S.
