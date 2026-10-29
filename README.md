# Diplomat

Type anything (rude, rushed, messy) and get back a message you can send on Slack, in an Office app, or on LinkedIn. It runs on your machine with a local LLM. No accounts, no telemetry, nothing leaves your computer except the request to the model server you configure.

> **Status: Phase 1 in progress.** The prompt engine and command-line tool work today. The floating window, global hotkey and settings screen are the next steps (see [`docs/plan.md`](docs/plan.md)). This README covers what you can use now and is marked where things are still to come.

English only for now.

## Requirements

- macOS 13+ (the engine itself runs on any OS; the hotkey UI targets macOS first)
- Python 3.10+
- A local model server with an OpenAI-compatible API:
  - [Ollama](https://ollama.com) (default, `http://localhost:11434/v1`), or
  - [LM Studio](https://lmstudio.ai) (`http://localhost:1234/v1`), or
  - any other OpenAI-compatible server
- One instruct model. 7B works for simple rewrites, **8B or larger is recommended**: smaller models tend to follow instructions inside your text, add facts, or ignore the tone sliders.

## Quick start

```bash
git clone <this repo's URL>
cd diplomat

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# make sure you have a model, for example:
ollama pull qwen2.5:7b-instruct

python -m diplomat.prompt "send me the q3 numbers asap, need them for the board meeting tmrw"
```

If you haven't chosen a model, the tool lists what your server has installed and uses the first one. Pick one explicitly with `--model`:

```bash
python -m diplomat.prompt "can't do the offsite in march, too busy w/ the launch. maybe june?" --model llama3.1:8b
```

(`PySide6` and `pynput` in `requirements.txt` are for the upcoming window and hotkey. For the command-line tool alone, `pip install httpx pytest` is enough.)

## Using the command-line tool

```bash
python -m diplomat.prompt "rough text"                    # Slack / Office reply (default)
python -m diplomat.prompt "rough text" --preset linkedin  # LinkedIn post, 3,000 character limit
python -m diplomat.prompt "rough text" --context "the message you are replying to"
python -m diplomat.prompt --file tests/sample_inputs.txt  # run many inputs (separated by lines of ---)
echo "rough text" | python -m diplomat.prompt             # from stdin
python -m diplomat.prompt "rough text" --show-prompt      # print the system prompt and exit
```

### Presets

| Preset | Limit | Style |
|--------|-------|-------|
| `slack_office` (default) | none | short paragraphs, no sign-off, plain text, no emoji |
| `linkedin` | 3,000 characters | strong first lines, short paragraphs, concrete details, at most 3 hashtags, no engagement bait |

For the limit, the model is asked for about 90% of it. The code counts the result. If it is still over, it asks once for a shorter version. If it is still over after that, you get the text as is with an `OVER LIMIT` note. Output is never silently truncated.

### Tone sliders

Seven sliders, 0 to 100: formality, warmth, directness, humor, sarcasm, enthusiasm, brevity. Each maps to one of five worded levels, because small models follow words better than numbers. Defaults are professional and concise, with no humor or sarcasm. Sarcasm stays workplace-safe even at the top.

Override one for a single run:

```bash
python -m diplomat.prompt "rough text" --set humor=60 --set brevity=90
```

### Writing rules

Output follows a compact version of the [no-ai-slop](https://github.com/petergyang/no-ai-slop) rules: lead with the point, no "It's not X, it's Y", no throat-clearing openers, no buzzwords. A small regex check looks for the most common patterns after generation. If it finds one, the tool regenerates once with those phrases banned, then shows the result as is. Turn all of this off with `--no-rules`.

## Configuration

Settings live in one JSON file:

| OS | Location |
|----|----------|
| macOS | `~/Library/Application Support/Diplomat/config.json` |
| Linux | `~/.config/Diplomat/config.json` |
| Any | set `DIPLOMAT_CONFIG=/path/to/config.json` to use another file |

The file is optional. Anything you leave out uses the defaults.

```json
{
  "provider": "ollama",
  "base_url": "http://localhost:11434/v1",
  "api_key": null,
  "model": "",
  "hotkey": "option+space",
  "default_preset": "slack_office",
  "slop_rules": true,
  "sliders": { "formality": 50, "warmth": 50, "directness": 50, "humor": 0, "sarcasm": 0, "enthusiasm": 30, "brevity": 50 }
}
```

To use LM Studio, set `base_url` to `http://localhost:1234/v1`. For another server, enter its URL and an optional `api_key`. You'll get a warning if the URL isn't a local address. A corrupt file is renamed to `config.corrupt-<timestamp>.json` and defaults are restored.

## Coming next (Phase 1)

- Floating window opened by a global hotkey (default `⌥ Space`), with tone sliders, copy button and tray icon
- Settings screen to choose the provider, pick an installed model, test it and set the hotkey
- `run.sh` and a double-click launcher
- macOS permission notes: the global hotkey needs **Input Monitoring** for the Terminal or Python app you launch it from

## Running the tests

```bash
pip install pytest httpx
python -m pytest
```

The tests cover slider mapping, prompt assembly, output cleanup, slop detection, the length logic and config handling. They don't need a model server.

After any change to prompts or rules, run the sample inputs and read the results yourself:

```bash
python -m diplomat.prompt --file tests/sample_inputs.txt
```

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `Can't reach the model server` | Start Ollama (`ollama serve`) or LM Studio's local server, and check `base_url`. |
| `Model '…' was not found` | Run `ollama list`, then pass an installed name with `--model`. |
| No models listed | Install one, e.g. `ollama pull qwen2.5:7b-instruct`. Embedding models are hidden on purpose. |
| First request is slow, or `took too long to start answering` | The model is loading into memory. Wait and run it again. |
| Output ignores your text and does something else | Use a larger model (8B or more). Small models sometimes obey instructions found inside the draft. |
| Reasoning models are slow | The client asks the server to skip thinking (`reasoning_effort: none`). If your server ignores that, pick a non-reasoning model. |
| Preamble such as "Here's the rewritten message:" appears | Common ones are stripped automatically. If you see another, open an issue with the text. |

## Privacy

Local only. No telemetry and no accounts. The only network traffic is to the model URL you configure, and the tool warns when that URL isn't localhost.

## Credits and licenses

- Writing rules adapted from [no-ai-slop](https://github.com/petergyang/no-ai-slop) by Peter Yang, used under the MIT license. The license text is in [`diplomat/rules/LICENSE-no-ai-slop`](diplomat/rules/LICENSE-no-ai-slop).