# Reddit Video Automator

An end-to-end automation pipeline that fetches Reddit stories, links their updates, generates narrated videos with stylized subtitles, and publishes them to YouTube. The project ships with a modern Electron desktop application for visual management, a complete CLI, and a real-time notification system.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation and Setup](#installation-and-setup)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Command Line Interface](#command-line-interface)
  - [Desktop Application](#desktop-application)
- [Directory Structure](#directory-structure)
- [Development](#development)
- [License](#license)

---

## Overview

Reddit Video Automator transforms Reddit text stories into ready-to-upload YouTube videos. It automatically fetches posts from monitored subreddits, detects and links multi-part updates, then goes through a complete media pipeline: text-to-speech narration, word-level subtitle generation, background video compositing, dynamic thumbnail creation, and finally upload to YouTube. The system is built around a robust backend API with a rich CLI and an Electron-based frontend that supports both manual and fully automated workflows through templates and scheduling.

---

## Features

- **Reddit Story Fetching** – Pull top, hot, or new posts from any subreddit; deduplication prevents re-fetching.
- **Update Detection & Linking** – Automatically identifies follow‑up posts (e.g. “UPDATE”, “Part 2”) and links them to the original story, enabling complete narrative chains.
- **Text‑to‑Speech Narration** – Supports OpenAI TTS and ElevenLabs, with selectable voices.
- **Whisper‑Based Subtitling** – Generates word‑level ASS subtitles with configurable style, position, and word wrapping.
- **Video Composition** – FFmpeg‑based rendering that overlays narration and subtitles on a randomly chosen background video; supports vertical (9:16 Shorts) and horizontal (16:9) formats.
- **Thumbnail Generation** – Dynamic thumbnails with gradient backgrounds, story title, subreddit badge, and score.
- **YouTube Integration**
  - OAuth 2.0 authentication with secure token storage.
  - Resumable video upload with progress tracking.
  - Custom thumbnail upload.
  - Full video management: update metadata, change privacy, fetch analytics, delete videos.
- **Real‑time Notifications** – Server‑Sent Events broadcast pipeline progress and system events to the UI.
- **Automation Templates** – Define reusable workflows that combine subreddit selection, generation settings, and YouTube upload parameters. Templates can be triggered manually or run on a schedule.
- **CLI** – A full‑featured command line interface built with Click and Rich for all operations (settings, fetching, linking, video generation, YouTube management).
- **Desktop Application** – An Electron wrapper with React frontend, providing a polished user interface for the entire pipeline, including live progress and YouTube studio tools.

---

## Technology Stack

### Backend (Python)

- **FastAPI** – REST API with async support and automatic OpenAPI docs.
- **SQLAlchemy** – ORM with SQLite storage, encrypting sensitive fields at rest.
- **PRAW** – Reddit API client.
- **OpenAI & ElevenLabs** – TTS providers.
- **OpenAI Whisper** – Speech‑to‑text for subtitle generation.
- **FFmpeg** – Video compositing, scaling, and subtitle burning.
- **Google API Client** – YouTube Data API v3 integration.
- **Click** – CLI framework.
- **Rich** – Beautiful terminal output.
- **Pydantic** – Data validation and settings management.
- **Cryptography (Fernet)** – Symmetric encryption of API tokens and keys.

### Frontend

- **React 18** – Functional components with hooks.
- **TypeScript** – Static typing across the project.
- **Vite** – Fast build tool and dev server.
- **Tailwind CSS v4** – Utility‑first styling with dark mode.
- **Zustand** – Lightweight state management.
- **React Query** – Server state synchronization.
- **React Router** – Client‑side routing.
- **Electron** – Desktop container with native file dialogs and external link handling.
- **Lucide Icons** – Modern icon set.

---

## Architecture

The application is split into three layers:

1. **Backend** (`backend/`) – The core engine. It exposes a RESTful API (FastAPI), runs the scheduler, and contains all business logic: fetching stories, linking updates, video generation, YouTube integration, and automation. A CLI (`cli.py`) provides direct access to the same functionality for scripting and debugging.

2. **Frontend** (`frontend/`) – A React application built with Vite that communicates with the backend via the API. It includes an Electron shell (`electron/main.cjs`) that starts the backend as a child process in production mode, providing a single-user desktop experience.

3. **Shared** – Pydantic schemas and TypeScript types mirror the data structures, ensuring type safety between layers.

Communication between frontend and backend happens over HTTP (REST) and Server‑Sent Events (SSE) for notifications. In development, the Vite dev server proxies API requests to the backend. The Electron wrapper uses a localhost backend and disables sandbox restrictions for file dialogs.

---

## Prerequisites

- **Python 3.10+** with `pip` and a virtual environment recommended.
- **Node.js 18+** and `npm` (for the frontend).
- **FFmpeg** installed on the system and available in PATH (required for video processing).
- **API Credentials**:
  - Reddit API client ID and secret (free, obtained from Reddit Apps).
  - OpenAI API key (or ElevenLabs) for TTS.
  - Google Cloud OAuth 2.0 credentials (for YouTube upload).
- **Git** for cloning the repository.

---

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/reddit-video-automator.git
cd reddit-video-automator
```

### 2. Backend Setup

Create and activate a Python virtual environment, then install dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -e .
```

The backend will automatically create an SQLite database and encryption key in `~/.reddit-video-automator/` on first run.

### 3. Frontend Setup

```bash
cd ../frontend
npm install
```

### 4. FFmpeg

Install FFmpeg from your system’s package manager or from [ffmpeg.org](https://ffmpeg.org/download.html). Verify with:

```bash
ffmpeg -version
```

### 5. Configuration

All sensitive settings are stored in the encrypted database. Use the CLI to set them, or fill them through the UI (Settings page). See [Configuration](#configuration).

---

## Configuration

The application requires several API keys and tokens. Set them using the CLI:

```bash
# Reddit API
rva set-setting reddit_client_id "your_client_id" --encrypt
rva set-setting reddit_client_secret "your_client_secret" --encrypt

# OpenAI TTS
rva set-setting openai_api_key "sk-..." --encrypt

# (Optional) ElevenLabs
rva set-setting elevenlabs_api_key "your_key" --encrypt

# YouTube OAuth credentials (set via UI or CLI)
rva set-setting youtube_client_id "your_google_client_id" --encrypt
rva set-setting youtube_client_secret "your_google_client_secret" --encrypt
```

You can verify stored settings with `rva get-setting <key> --decrypt`.

YouTube authentication is done interactively:

```bash
rva youtube auth-url      # get the consent URL
rva youtube exchange-code <code> <state>
```

All credentials are encrypted with a symmetric key derived at first start and stored in `~/.reddit-video-automator/.key`.

---

## Usage

### Command Line Interface

The CLI (`rva`) provides a comprehensive interface for every operation.

**Subreddits & Fetching**

```bash
rva add-subreddit AskReddit --sort top --time week --limit 10
rva fetch 1                    # using the subreddit ID
rva fetch-all                  # fetch from all active subreddits
```

**Update Linking**

```bash
rva link-updates --subreddit AskReddit
rva show-chain 5               # show original + updates for story ID 5
```

**Video Generation**

```bash
rva generate-video 5 --tts-provider openai --tts-voice alloy --background /path/to/videos --format shorts
rva list-videos
```

**YouTube Management**

```bash
rva youtube upload 1 --privacy private --thumbnail
rva youtube stats <youtube_video_id>
rva youtube update-metadata <id> --title "New Title" --tags "tag1,tag2"
```

**Notifications & General**

```bash
rva notifications --unread-only
rva mark-read 3
rva check-ffmpeg
```

For a full list of commands, type `rva --help`.

### Desktop Application

Start both backend and frontend:

```bash
# Terminal 1
cd backend
uvicorn main:app --port 8000

# Terminal 2
cd frontend
npm run dev
```

Then open `http://localhost:3000` in your browser. For an Electron desktop experience, build and launch:

```bash
npm run electron:dev    # builds the frontend and launches Electron
```

The desktop app provides:

- **Stories Page** – Add subreddits, fetch stories, link updates, and trigger individual video generation.
- **Videos Page** – Monitor generated videos, upload to YouTube, and open YouTube Studio for stats.
- **Automation Page** – Create, edit, and toggle automation templates; run them manually or let the scheduler handle them.
- **Settings Page** – Manage API keys, FFmpeg path, and theme.
- **Real‑time Notifications** – Dropdown bell icon showing pipeline progress and system messages.

---

## Directory Structure

```text
reddit-video-automator/
├── backend/                     # Python backend
│   ├── main.py                  # FastAPI application entry point
│   ├── cli.py                   # Click‑based CLI
│   ├── config.py                # Paths, video format definitions
│   ├── crypto.py                # Encryption / decryption utilities
│   ├── database.py              # SQLAlchemy engine and session factory
│   ├── models.py                # ORM models (Stories, Videos, Subreddits, etc.)
│   ├── schemas.py               # Pydantic models for API
│   ├── settings_manager.py      # Encrypted settings CRUD
│   ├── api/                     # REST routes and SSE
│   ├── automation/              # Template models & routes
│   ├── reddit/                  # Reddit client, fetcher, update linker
│   ├── video/                   # Video pipeline, TTS, subtitles, composer, thumbnail, utils
│   ├── youtube/                 # OAuth, uploader, manager
│   ├── scheduler/               # Background template scheduler
│   └── tests/                   # Unit tests
├── frontend/                    # React + Electron frontend
│   ├── electron/                # Electron main process and preload
│   ├── src/
│   │   ├── components/          # Reusable UI components
│   │   ├── pages/               # App pages (Stories, Videos, Automation, Settings, Login)
│   │   ├── services/            # Axios HTTP client and SSE manager
│   │   ├── store/               # Zustand stores (auth, theme, notifications)
│   │   └── types/               # TypeScript type definitions
│   └── package.json
└── README.md
```

---

## Development

### Backend

Run tests with `pytest`:

```bash
cd backend
pytest
```

The backend uses in‑memory SQLite for tests with no external dependencies.

### Frontend

Start the development server with hot module replacement:

```bash
cd frontend
npm run dev
```

Ensure the backend is running on port 8000. The Vite proxy forwards API requests automatically.

### Building for Production

```bash
cd frontend
npm run build          # builds static assets
npm run electron:build # packages the Electron app
```

---

## License

This project is licensed under the MIT License.

```text
MIT License

Copyright (c) 2026 Dimitris Markou

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The full license text is also available in the `LICENSE` file at the root of the repository.
