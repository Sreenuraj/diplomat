# Diplomat

Type anything (rude, rushed, messy), press a hotkey, and get back a message you can send on Slack, in an Office app, or on LinkedIn. Runs on your machine with a local LLM. No accounts, no telemetry — nothing leaves your computer except requests to the model server you configure.

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

## Requirements

- macOS 13+
- Python 3.10+
- A local model server with an OpenAI-compatible API:
  - [Ollama](https://ollama.com) (default, `http://localhost:11434/v1`), or
  - [LM Studio](https://lmstudio.ai) (`http://localhost:1234/v1`), or
  - any other OpenAI-compatible server
- One instruct model. 7B works for simple rewrites; **8B or larger is recommended** (for example `qwen2.5:7b-instruct` or `llama3.1:8b`), because smaller models sometimes follow instructions inside your draft, add facts, or ignore the tone sliders.

## Quick start

```bash
git clone https://github.com/Sreenuraj/diplomat.git
cd diplomat

# Pull a local model if you haven't already, e.g. with Ollama:
ollama pull qwen2.5:7b-instruct

./run.sh
```

Or double-click **`Diplomat.command`** in Finder.

On first run, `./run.sh` creates `.venv`, installs `requirements.txt`, starts Diplomat, and opens **Settings** so you can verify your provider, pick an installed model, and click **Test Model**.

## Using Diplomat

Press **`⌥ Space`** from any app (or click the **D** icon in the macOS menu bar) to show or hide the floating window. Your cursor goes straight to the draft box.

| Shortcut | Action |
|----------|--------|
| `⌥ Space` (configurable) | Show / hide the popup |
| `⌘↩` | Generate |
| `↩` in the output box | Copy to clipboard and close |
| `⌘R` | Regenerate |
| `⌘,` | Open Settings |
| `Esc` | Cancel generation, or close the popup |

### Presets

| Preset | Limit | Style |
|--------|-------|-------|
| `Slack / Office` (default) | none | short paragraphs, no greeting/sign-off unless in draft, plain text, no emoji |
| `LinkedIn post` | 3,000 characters | strong opening lines, short paragraphs, concrete details, at most 3 hashtags at the end, no engagement bait |

For presets with a character limit, the model is asked for ~90% of the limit (`2,700` characters for LinkedIn). The character counter turns **amber** at 90% and **red** over the limit. If the first output exceeds the limit, Diplomat automatically asks once for a shorter version and never truncates silently.

### Tone sliders

Seven sliders (`0–100`): **Formality**, **Warmth**, **Directness**, **Humor**, **Sarcasm**, **Enthusiasm**, and **Brevity**. Each maps to one of five worded bands (`1/5` to `5/5`) because small models follow words better than numbers. Defaults are tuned for professional, concise workplace replies with no humor or sarcasm. Sarcasm stays workplace-safe even at the top band. The Tone panel collapses and remembers its state.

### Writing rules

Output follows a compact version of the [no-ai-slop](https://github.com/petergyang/no-ai-slop) rules: lead with the point, active voice, concrete details, no `"It's not X, it's Y"` contrasts, no throat-clearing openers, no banned buzzwords, and no em dashes. After generation, a regex check looks for the top patterns; if one appears, Diplomat retries once with those patterns explicitly banned.

## macOS permissions (Input Monitoring)

Global hotkeys via `pynput` require **Input Monitoring** permission on macOS. The permission attaches to the app you launch Diplomat from (**Terminal**, **iTerm**, **VS Code**, or **Python**):

1. Open **System Settings → Privacy & Security → Input Monitoring**.
2. Enable the app you launched from (for example **Terminal** or **Visual Studio Code**).
3. Restart Diplomat (or re-record the shortcut in **Settings**).

Even without Input Monitoring permission, you can always open and hide Diplomat from the **D** icon in the macOS menu bar.

## Switching provider, model, or hotkey

Press **`⌘,`** in the popup, click **⚙**, or choose **Settings…** from the menu bar icon:

- **Provider:** choose **Ollama** (`http://localhost:11434/v1`), **LM Studio** (`http://localhost:1234/v1`), or **Other** (custom URL + optional API key).
- **Model:** click **Refresh** to reload installed models and select one.
- **Test Model:** sends a short rewrite and shows the output and response time.
- **Global Hotkey:** click the hotkey field and press any modifier + key combination, or click **Default (⌥ Space)**.
- **Writing Rules:** turn the compact `no-ai-slop` rules on or off.

Changes apply immediately without restarting.

## Configuration file

Settings are stored in a single JSON file:

| OS | Location |
|----|----------|
| macOS | `~/Library/Application Support/Diplomat/config.json` |
| Linux | `~/.config/Diplomat/config.json` |
| Custom | set `DIPLOMAT_CONFIG=/path/to/config.json` |

```json
{
  "provider": "ollama",
  "base_url": "http://localhost:11434/v1",
  "api_key": null,
  "model": "qwen2.5:7b-instruct",
  "hotkey": "option+space",
  "default_preset": "slack_office",
  "slop_rules": true,
  "tone_open": false,
  "sliders": {
    "formality": 50,
    "warmth": 50,
    "directness": 50,
    "humor": 0,
    "sarcasm": 0,
    "enthusiasm": 30,
    "brevity": 50
  }
}
```

Writes are atomic. If the file is ever corrupted, Diplomat backs it up to `config.corrupt-<timestamp>.json` and restores defaults.

## Command-line tool

You can also run the prompt engine directly from the terminal:

```bash
.venv/bin/python -m diplomat.prompt "rough text"                    # Slack / Office reply (default)
.venv/bin/python -m diplomat.prompt "rough text" --preset linkedin  # LinkedIn post, 3,000 character limit
.venv/bin/python -m diplomat.prompt "rough text" --context "the message you are replying to"
.venv/bin/python -m diplomat.prompt "rough text" --set humor=60 --set brevity=90
.venv/bin/python -m diplomat.prompt "rough text" --no-rules         # disable no-ai-slop rules
.venv/bin/python -m diplomat.prompt --file tests/sample_inputs.txt  # run all 15 sample inputs
echo "rough text" | .venv/bin/python -m diplomat.prompt             # read from stdin
.venv/bin/python -m diplomat.prompt "rough text" --show-prompt      # print the system prompt and exit
```

## Running tests

```bash
.venv/bin/pytest -v
```

The test suite covers slider-to-band mapping, prompt assembly, output cleanup, slop detection, length retry logic, config persistence and corruption recovery, hotkey formatting, the popup UI, and the Settings dialog. No running model server is needed for unit tests.

To evaluate prompt changes against your local model across all 15 sample inputs:

```bash
.venv/bin/python -m diplomat.prompt --file tests/sample_inputs.txt
```

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Hotkey (`⌥ Space`) doesn't fire | Grant **Input Monitoring** to Terminal / your launcher in **System Settings → Privacy & Security → Input Monitoring**, or record a different shortcut in **Settings** (`⌘,`). You can also click the **D** menu bar icon. |
| `Can't reach the model server` | Start Ollama (`ollama serve`) or LM Studio's local server, then click **Refresh** in Settings or **Retry** in the popup. |
| `Model '…' was not found` | Open **Settings** (`⌘,`), click **Refresh**, and pick an installed model. |
| No models listed | Pull an instruct model, e.g. `ollama pull qwen2.5:7b-instruct`. Embedding models (`*embed*`) are hidden automatically. |
| First request is slow, or `took too long to start answering` | Cold models can take several seconds to load into memory (first-token timeout is 20s). Wait a moment and click **Retry**. |
| Output ignores your draft and follows text inside it | Switch to an 8B+ instruct model. Very small models sometimes treat draft text as instructions. |
| Preamble such as `"Here's the rewritten message:"` appears | Common preambles, markdown code fences, and wrapping quotes are stripped automatically. |

## Privacy

Local only. No accounts and no telemetry. Diplomat makes no network calls except to the model server URL you configure, and displays a warning if that URL is not on `localhost`.

## Credits and licenses

- Writing rules adapted from [no-ai-slop](https://github.com/petergyang/no-ai-slop) by Peter Yang, used under the MIT license (see [`diplomat/rules/LICENSE-no-ai-slop`](diplomat/rules/LICENSE-no-ai-slop)).