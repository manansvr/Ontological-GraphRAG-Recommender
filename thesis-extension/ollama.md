# Ollama Setup Guide

This guide explains how to download, install, and configure Ollama for the SR8 Knowledge Graph chat system.

## 1. Download Ollama

### macOS (Recommended for this project)

Visit the official Ollama download page: **https://ollama.ai**

Click "Download" and select macOS. This will download `Ollama-0.x.x.dmg`.

Alternatively, use Homebrew:

```bash
brew install ollama
```

### Linux or Windows

Download from **https://ollama.ai** and follow the installer for your operating system.

## 2. Install Ollama

### macOS (DMG method)

1. Open the downloaded `Ollama-x.x.x.dmg` file.
2. Drag the Ollama icon to Applications.
3. Open Applications and double-click Ollama to install.

### macOS (Homebrew method)

```bash
brew install ollama
```

### Linux

```bash
curl https://ollama.ai/install.sh | sh
```

### Verify Installation

Check that Ollama is installed:

```bash
ollama --version
```

You should see a version number like `ollama version 0.1.x`.

## 3. Start Ollama Service

### macOS (Recommended)

**Option 1: Auto-launch on startup**

```bash
brew services start ollama
```

This registers Ollama to start automatically when you log in.

**Option 2: Manual start**

```bash
ollama serve
```

This starts Ollama in the foreground. Keep this terminal open while using the chat system.

### Linux / Windows

Same as macOS:

```bash
ollama serve
```

## 4. Download a Language Model

Once Ollama is running, pull a model in a **new terminal** (keep the `ollama serve` terminal open):

```bash
ollama pull llama3.1:8b
```

This downloads the Llama 3.1 8B model (~4GB). Other models available:

- `llama3.1:8b` - Fast, balanced (recommended)
- `gpt-oss:20b` - Larger, slower, more capable
- `deepseek-r1:latest` - Reasoning-focused
- `mistral:latest` - Small and fast

To see all available models:

```bash
ollama list
```

## 5. Verify Ollama is Running

Check if Ollama is accessible:

```bash
curl http://localhost:11434/api/tags
```

You should see a JSON response with your downloaded models. If you see an error, Ollama is not running yet.

## 6. Configure for SR8 Project

Update [thesis-extension/.env](thesis-extension/.env) with your model choice:

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
RL_ENABLED=true
RL_MODEL_PATH=.rl-model.json
```

Notes:

- `RL_ENABLED=true` enables adaptive SR8 retrieval strategy selection in the chat client.
- `RL_MODEL_PATH` is the persisted Q-learning model file used by `ollama-mcp`.

## 7. Run the Chat System

Now that Ollama is running and configured, start the SR8 chat client:

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
source .venv/bin/activate
.venv/bin/python ollama-mcp --model llama3.1:8b
```

Optional RL self-test before chat:

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
.venv/bin/python reinforcemnt-learning.py --self-test
```

## Troubleshooting

### Ollama won't start

**macOS:**
```bash
brew services stop ollama
brew services start ollama
```

**Linux/Manual start:**
Check for port conflicts on `localhost:11434`:
```bash
lsof -i :11434
```

### Model download is slow

Models are large (2GB–20GB depending on the model). Use a wired connection or ensure stable WiFi.

### PDF OCR fallback is not working

OCR for scanned PDFs requires both `tesseract` and Poppler's `pdftoppm` binary.

On macOS, install them with:

```bash
brew install tesseract poppler
```

Then verify the tools are on your PATH:

```bash
command -v tesseract
command -v pdftoppm
```

### "Connection refused" error

Ensure `ollama serve` is running in a separate terminal. You should see:
```
Listening on 127.0.0.1:11434
```

### Out of memory

If Ollama crashes with memory errors, try a smaller model:
```bash
ollama pull mistral:latest
```

Then update `.env` to use it:
```
OLLAMA_MODEL=mistral:latest
```

### RL bridge did not initialize

If startup shows RL disabled, verify all of the following:

```bash
cd /Users/manan/Desktop/Honours/thesis-extension
ls -l reinforcemnt-learning.py
test -f .rl-model.json && echo "model file exists" || echo "model file will be created on first RL update"
```

Then run the self-test:

```bash
.venv/bin/python reinforcemnt-learning.py --self-test
```

## Next Steps

Once Ollama is set up and running:

1. Activate the virtual environment:
   ```bash
   cd /Users/manan/Desktop/Honours/thesis-extension
   source .venv/bin/activate
   ```

2. Run the chat system:
   ```bash
   .venv/bin/python ollama-mcp --model llama3.1:8b
   ```

3. Ask questions like:
   - "How many requirements are there for SRP-043?"
   - "Find references to ADR-31 in local docs."
   - "Get essential requirements for ADR-25 from the graph."

4. For design or manufacturing questions, the chat client answers from the indexed
   documents and then appends a redirect to the relevant section:
   - Design questions point to the Design Manual's `The Design Process` section.
   - Manufacturing questions point to the Manufacturing Section's `Manufacturing` section.

For more help, see [README.md](README.md).
