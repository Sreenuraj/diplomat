# Diplomat

Type anything (rude, rushed, messy), press a hotkey, and get back a message you can send on Slack, in an Office app, or on LinkedIn. It runs on your machine with a local LLM. No accounts, no telemetry, nothing leaves your computer except the request to the model server you configure.

```
┌────────────────────────────────────────────────────────┐
│  Diplomat     [ Slack / Office ▾ ]                  ⚙  │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Type anything…                                     │ │
│ └────────────────────────────────────────────────────┘ │
│  ▸ Replying to… (optional: paste the message you got)  │
│  ▾ Tone                                    [ Reset ]   │
│    Formality ──●──   Warmth ──●──   Directness ──●──   │
│    Humor ●─────      Sarcasm ●─────  Enthusiasm ─●──   │
│    Brevity ──●──                                       │
│ ────────────────────────────────────────────────────── │
│  Hi Priya, thanks for flagging this. I can have…       │
│  412 / 3000          [ Regenerate ]  [ Copy ]          │
└────────────────────────────────────────────────────────┘
```

English only in Phase 1.

## Requirements

- macOS 13+ (the engine and UI run on Python + PySide6; the hotkey workflow targets macOS first)
- Python 3.10+
- A local model server with an OpenAI-compatible API:
  - [Ollama](https://ollama.com) (default, `http://localhost:11434/v1`), or
  - [LM Studio](https://lmstudio.ai) (`http://localhost:1234/v1`), or
  - any other OpenAI-compatible server
- One instruct model. 7B works for simple rewrites, **8B or larger is recommended** (for example `qwen2.5:7b-instruct` or `llama3.1:8b`): smaller models tend to follow instructions inside your text, add facts, or ignore the tone sliders.

## Quick start

```bash
git clone <this repo's URL>
cd diplomat

# make sure you have a local model, for example with Ollama:
ollama pull qwen2.5:7b-instruct

./run.sh
```

Or double-click **`Diplomat.command`** in Finder.

On first run, `./run.sh` creates `.venv`, installs `requirements.txt`, starts the app, and opens the **Settings** dialog so you can verify your provider, pick an installed model, and click **Test Model**.

## Using it

Press **`⌥ Space`** from any app (or click the **D** icon in the macOS menu bar) to open the floating window. Your cursor goes straight to the text box.

| Key | Action |
|-----|--------|
| `⌥ Space` (configurable) | Show / hide the popup |
| `⌘↩` | Generate |
| `↩` in the output box | Copy and close |
| `⌘R` | Regenerate |
| `⌘,` | Open Settings |
| `Esc` | Cancel generation, or close the popup |

### Presets

| Preset | Limit | Style |
|--------|-------|-------|
| `Slack / Office` (default) | none | short paragraphs, no sign-off, plain text, no emoji |
| `LinkedIn post` | 3,000 characters | strong first lines, short paragraphs, concrete details, at most 3 hashtags, no engagement bait |

For presets with a limit, the model is asked for about 90% of the limit (`2,700` characters for LinkedIn). The character counter turns **amber** at 90% and **red** over the limit. If the first output is over the limit, Diplomat asks once for a shorter version and never truncates silently.

### Tone sliders

Seven sliders, 0 to 100: **Formality**, **Warmth**, **Directness**, **Humor**, **Sarcasm**, **Enthusiasm**, and **Brevity**. Each maps to one of five worded levels, because small models follow words better than numbers. Defaults are professional and concise, with no humor or sarcasm. Sarcasm stays workplace-safe even at the top. The Tone panel collapses and remembers its state.

### Writing rules

Output follows a compact version of the [no-ai-slop](https://github.com/petergyang/no-ai-slop) rules: lead with the point, no `"It's not X, it's Y"`, no throat-clearing openers, no buzzwords, and no em dashes. A small regex check looks for the top patterns after generation; one hit triggers a single retry with those patterns banned.

## macOS permissions (Input Monitoring)

Global hotkeys via `pynput` require **Input Monitoring** permission on macOS. The permission attaches to the app you launch Diplomat from (**Terminal**, **iTerm**, **VS Code**, or **Python**):

1. Open **System Settings → Privacy & Security → Input Monitoring**.
2. Enable your terminal app (e.g. **Terminal** or **Visual Studio Code**).
3. Restart Diplomat (or re-record the hotkey in **Settings**).

Even without Input Monitoring permission, you can always open/hide Diplomat from the **D** icon in the macOS menu bar.

## Switching provider or model later

Press **`⌘,`** in the popup (or click **⚙** / choose **Settings…** from the menu bar icon):

- **Provider:** switch between **Ollama** (`http://localhost:11434/v1`), **LM Studio** (`http://localhost:1234/v1`), or **Other** (custom URL and optional API key).
- **Model:** click **Refresh** to reload installed models and pick another one.
- **Test Model:** sends a short rewrite and displays the output and response time.
- **Global Hotkey:** click the hotkey field and press any modifier + key combination, or click **Default (⌥ Space)**.
- **Writing Rules:** toggle the compact `no-ai-slop` rules on or off.

All changes apply immediately without restarting.

Settings are stored in `~/Library/Application Support/Diplomat/config.json` on macOS (`~/.config/Diplomat/config.json` on Linux, or override with `DIPLOMAT_CONFIG=/path/to/config.json`). Writes are atomic; a corrupt file is backed up to `config.corrupt-<timestamp>.json` and defaults are restored.

## Command-line tool

You can also run the prompt engine directly from the terminal:

```bash
.venv/bin/python -m diplomat.prompt "rough text"                    # Slack / Office reply (default)
.venv/bin/python -m diplomat.prompt "rough text" --preset linkedin  # LinkedIn post, 3,000 character limit
.venv/bin/python -m diplomat.prompt "rough text" --context "the message you are replying to"
.venv/bin/python -m diplomat.prompt "rough text" --set humor=60 --set brevity=90
.venv/bin/python -m diplomat.prompt --file tests/sample_inputs.txt  # run all 15 sample inputs
.venv/bin/python -m diplomat.prompt "rough text" --show-prompt      # print the system prompt and exit
```

## Running the tests

```bash
.venv/bin/pytest -v
```

The unit tests cover slider mapping, prompt assembly, output cleanup, slop detection, length retry logic, config handling, hotkey formatting, the popup UI, and the Settings dialog. They do not require a running model server.

After any change to prompts or rules, run the 15 sample inputs against your local model and read the outputs:

```bash
.venv/bin/python -m diplomat.prompt --file tests/sample_inputs.txt
```

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Hotkey (`⌥ Space`) doesn't fire | Grant **Input Monitoring** to Terminal / your launcher in **System Settings → Privacy & Security → Input Monitoring**, or record a different shortcut in **Settings** (`⌘,`). You can also use the **D** menu bar icon. |
| `Can't reach the model server` | Start Ollama (`ollama serve`) or LM Studio's local server, then click **Refresh** or **Retry**. |
| `Model '…' was not found` | Open **Settings** (`⌘,`), click **Refresh**, and pick an installed model. |
| No models listed | Install one, e.g. `ollama pull qwen2.5:7b-instruct`. Embedding models (`*embed*`) are hidden on purpose. |
| First request is slow, or `took too long to start answering` | Cold models take a moment to load into memory (first-token timeout is 20s). Wait a few seconds and click **Retry**. |
| Output ignores your text and does something else | Use an 8B+ instruct model. Very small models sometimes obey text inside the draft. |
| Preamble such as "Here's the rewritten message:" appears | Common preambles and wrapping quotes are stripped automatically. |

## Privacy

Local only. No telemetry and no accounts. The only network traffic is to the model URL you configure, and Diplomat warns you whenever that URL isn't `localhost`.

## Credits and licenses

- Writing rules adapted from [no-ai-slop](https://github.com/petergyang/no-ai-slop) by Peter Yang, used under the MIT license. The license text is in [`diplomat/rules/LICENSE-no-ai-slop`](diplomat/rules/LICENSE-no-ai-slop).