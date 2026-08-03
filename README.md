# CuriousAsian — Automated YouTube Channel

Fully automated YouTube pipeline. Generates daily 5-8 min videos about everyday cultural habits, superstitions, and traditions people follow without knowing why.

**"Your grandma's rules, finally explained."**

## How It Works

1. **You** batch-write scripts via Claude chat (using the prompt template)
2. **Pipeline** (GitHub Actions, daily) picks a script → generates ~100 cartoon images → generates voiceover → assembles video → sends you a Telegram notification
3. **You** download the video and upload to YouTube (~2 min/day)
4. **When scripts run low** → Telegram alerts you + Gemini auto-generates backup scripts

## Cost: $0/month

Everything runs on free tiers (Gemini API, Edge TTS, FFmpeg, GitHub Actions, Telegram).

## Setup (~15 min)

### 1. Gemini API Key
- Go to [aistudio.google.com](https://aistudio.google.com) → "Get API Key"

### 2. Telegram Bot
- Message `@BotFather` on Telegram → `/newbot` → save the token
- Message `@userinfobot` → save your chat ID

### 3. GitHub Repository
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/curiosasian-youtube.git
git push -u origin main
```

### 4. GitHub Secrets
Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Your Gemini API key |
| `TELEGRAM_BOT_TOKEN` | From BotFather |
| `TELEGRAM_CHAT_ID` | From userinfobot |
| `REPO_TOKEN` | Fine-grained token (Contents only, scoped to this repo) |

### 5. GitHub Token (REPO_TOKEN)
- Settings → Developer settings → Personal access tokens → Fine-grained tokens
- **Repository access**: Only select repositories → pick this repo
- **Permissions**: Contents → Read and write (ONLY this, nothing else)
- Set expiry: 90 days
- Copy and save as `REPO_TOKEN` secret

### 6. Write Your First Scripts
See `claude_script_prompt.md` for the exact prompt to use in Claude chat.
Save each script as a JSON file in `scripts/queue/`.

### 7. Test
Actions tab → "Daily Video Pipeline" → "Run workflow"

## Folder Structure

```
scripts/
  queue/     ← Pre-written scripts (pipeline picks 1/day)
  done/      ← Used scripts (moved here after video is made)
data/
  topics_100.json  ← 100 topic ideas to write scripts for
  logs/            ← Daily run logs
src/               ← Pipeline source code
```

## Writing Scripts

1. Open Claude chat
2. Paste the prompt from `claude_script_prompt.md`
3. Replace the topics list with topics from `data/topics_100.json`
4. Save each script as `scripts/queue/001_topic_name.json`
5. Push to repo

Claude works best with 5-10 scripts per prompt.
