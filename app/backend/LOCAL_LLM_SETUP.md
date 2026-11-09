# 🏢 AI Assist on your own server — local LLM setup (4 GB GPU)

This guide installs a free, open-weight AI model on your **server PC**, the same PC that runs the RecoverIQ backend. AI Assist then answers without sending any data outside the office.

**Recommended model for a 4 GB GPU: `qwen3:4b`.** It is about 2.6 GB, fits fully on the GPU, and is the strongest model of this size at the "tool calling" AI Assist needs.

---

## 1. Check the GPU (2 min)

Open **Command Prompt** and run:
```
nvidia-smi
```
You should see your GPU, for example "4096MiB" total memory.
- If the command isn't found, install the latest **NVIDIA driver** from nvidia.com/drivers and restart the PC.
- AMD GPUs also work with Ollama on Windows.
- Without a supported GPU the model runs on the CPU. That works, but answers are about 5–10× slower.

## 2. Install Ollama (5 min)

1. Download **OllamaSetup.exe** from https://ollama.com/download and install it.
2. Ollama runs in the background. You'll see the llama icon in the system tray, and it starts automatically with Windows.
3. Check it in Command Prompt:
   ```
   ollama --version
   ```

## 3. Set the context size (important on 4 GB)

The context size is how much conversation the model keeps in memory. A larger context uses more VRAM, and on 4 GB that pushes the model partly onto the CPU, which is slow. **8192** is the right value.

1. Press **Windows key**, type **"environment variables"**, and open **Edit the system environment variables** → **Environment Variables…**
2. Under **System variables**, click **New…**:
   - Name: `OLLAMA_CONTEXT_LENGTH` · Value: `8192`
3. Optional: to keep the model loaded so the first answer each morning isn't slow, add:
   - Name: `OLLAMA_KEEP_ALIVE` · Value: `24h`
4. Click OK on every window. Then **quit Ollama** (right-click the tray icon → Quit) and start it again from the Start menu.

## 4. Download the model (5–15 min, about 2.6 GB)

```
ollama pull qwen3:4b
```
Quick test:
```
ollama run qwen3:4b "Say hello in one line /no_think"
```
Press `Ctrl+D` to exit.

Then check that it fits on the GPU:
```
ollama ps
```
The **PROCESSOR** column should say **100% GPU**. If it shows something like "30%/70% CPU/GPU", the context is too large; go back to step 3.

Optional fallback models to try:
```
ollama pull qwen2.5:3b        # faster, a bit weaker
ollama pull phi4-mini         # good English, weaker Telugu/Hindi
```

## 5. Connect RecoverIQ (2 min)

Sign in as **Admin**, then go to **⚙️ Services → AI Assist → ⚙ Settings**:

| Setting | Value |
|---|---|
| AI provider | 🏢 **Ollama on your server — data stays in the office** |
| Model | Click **⟳ Load models**, then pick `qwen3:4b` (or type it) |
| Ollama / LM Studio server URL | `http://127.0.0.1:11434/v1` (when Ollama is on the same PC as the backend) |
| Let local models 'think' | **Off** (gives quick answers) |
| Mask phone & account numbers | On |

Press **Save settings**, then **🧪 Test main provider**.
- ✅ **"works with AI Assist — answered in Ns"** means you're done.
- ❌ **"didn't use the tool"** means the chosen model can't drive AI Assist. Pick `qwen3:4b`.
- ❌ **"not reachable"** means Ollama isn't running, or the URL is wrong. Check the tray icon and step 6.

## 6. If Ollama is on a different PC than the backend

By default Ollama only listens to its own PC. On the Ollama PC:
1. Add the system variable `OLLAMA_HOST` = `0.0.0.0:11434`, then restart Ollama.
2. In Windows Firewall, allow inbound **TCP 11434**, but **only from the backend PC's IP**. Ollama has no password, so never expose this port to the internet or to the whole office network.
3. In RecoverIQ, set the URL to `http://<ollama-pc-ip>:11434/v1`.

## 7. Add a backup (recommended)

A 4B model is good at simple questions, but it can struggle with long, multi-step reports. You can add a cloud backup that answers only when the local model fails, for example when Ollama is stopped or errors out.

1. In the same settings, set **Backup provider** to Google Gemini (or OpenRouter, Groq, …).
2. Paste that provider's API key in the 🔑 box that appears, then save.
3. Press **🧪 Test backup**.

Data sent to a cloud backup still has phone and account numbers masked. For bank and NBFC clients that require data to stay in India, leave the backup off.

## What to expect on 4 GB

| Works well | Needs a bigger model (8 GB GPU → `qwen3:8b`) |
|---|---|
| "How many PTPs are due today?", "my unpaid cases", "team collection this month" | Multi-step requests ("compare all branches, explain why, make a PDF") |
| "How do I upload a DPR?" (app help) | Long reports and polished Telugu |
| Short WhatsApp / SMS drafts | Many follow-up questions in one chat |
| Simple Excel exports of a list | |

Typical speed is **2–6 s** per simple answer on the GPU.

**Tips for staff:** ask one clear thing at a time, and start a **New chat** for a new topic.

## Troubleshooting

| Problem | Fix |
|---|---|
| Very slow (30 s or more) | `ollama ps` shows CPU usage. Lower `OLLAMA_CONTEXT_LENGTH` to 4096, or close other GPU apps (games, video editors). |
| First answer of the day is slow | The model is loading. Set `OLLAMA_KEEP_ALIVE=24h`. |
| Answers show "thinking" text, or take too long | Make sure "Let local models think" is **off** and save. |
| Wrong numbers / "I can't find that" | Rephrase more specifically ("my cases in AXIS X-bucket this month"). The model only sees what that user can see. |
| "AI Assist isn't set up" | Run the test in ⚙️ Services; it tells you what's missing. |
| Ollama updates | Ollama updates itself. Run `ollama pull qwen3:4b` now and then to get the latest model version. |

## Upgrading later

- **8 GB GPU:** `ollama pull qwen3:8b`, then pick it in **Model**. This gives clearly better reports and Telugu.
- **12–16 GB GPU:** `qwen3:14b`.

No RecoverIQ restart is needed: change the model, save, then **Test**.
