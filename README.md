# Queryfi Discord bot

A Python bot that answers text prompts in bound channels using Open Notebook sources and its configured Ollama model. Three server slash commands manage bindings:

| Command | Result |
| --- | --- |
| `/list` | Reads Open Notebook notebooks and lists their IDs, names, and bound channels in this server. |
| `/status` | Shows whether the current text channel is bound and to which subject. |
| `/bind subject_id:<id>` | Binds the current text channel to that notebook ID in SurrealDB. Unknown IDs are rejected. |

Each notebook represents one course subject. Each channel holds one subject; rebinding replaces that channel's previous binding. A subject can be bound to several channels. Bindings persist in Open Notebook's SurrealDB database, in the `queryfi_channel_binding` table, and are isolated by server. Notebook and source records are not modified. All server members with access to the commands can use them, including `/bind`; no administrator permission is required. Responses are visible in the channel. DMs, threads, voice channels, and forum posts are not supported.

## Setup (PowerShell)

Requires Python 3.10 or newer. From this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Fill in `.env` beside `bot.py` (see `.env.example`):

```dotenv
DISCORD_TOKEN=your-bot-token
OPEN_NOTEBOOK_URL=http://localhost:5055
OPEN_NOTEBOOK_PASSWORD=
OPEN_NOTEBOOK_MODEL_ID=
OPEN_NOTEBOOK_CHAT_TIMEOUT=180
SURREAL_URL=http://localhost:8001
SURREAL_NAMESPACE=open_notebook
SURREAL_DATABASE=open_notebook
SURREAL_USER=root
SURREAL_PASSWORD=your-surrealdb-password
```

Use the same database, namespace, and database credentials as Open Notebook. `SURREAL_URL` is the host-published HTTP(S) base URL without `/rpc`; this machine's Open Notebook compose file publishes port 8001. `OPEN_NOTEBOOK_URL` is the API base URL without `/api`. Leave `OPEN_NOTEBOOK_PASSWORD` empty if API authentication is disabled. The Open Notebook API password and SurrealDB password are separate settings. The database user needs read/write access to `queryfi_channel_binding` and permission to create it on first use.

The bot automatically loads this file on startup, even when launched from another directory. Existing environment variables take precedence over `.env` values. The file is excluded from Git by `.gitignore`. Restart the bot after changing it. Startup verifies the API and database connections and checks that the selected chat model is an Ollama language model before logging into Discord.

```powershell
.\.venv\Scripts\python.exe bot.py
```

Create an application in the [Discord Developer Portal](https://discord.com/developers/applications), obtain its bot token from the **Bot** page, and install it into your server using the `bot` and `applications.commands` scopes. Allow **View Channels**, **Send Messages**, and **Read Message History** in the channels where you will use it. Users need **Use Application Commands**. No server ID setting is needed: each command identifies its server from the Discord interaction.

Use a bot token, keep it private, and set it locally in `.env` or through the environment. You interact with the bot from your normal Discord account. The script connects as the separate bot account. Enable **Message Content Intent** under **Bot > Privileged Gateway Intents** in the Developer Portal. The bot requests this intent to read ordinary text prompts; without it, the message flow cannot work. No members or presence intent is needed. See [Discord's bot overview](https://docs.discord.com/developers/bots/overview) and the [discord.py slash command example](https://github.com/Rapptz/discord.py/blob/master/examples/app_commands/basic.py).

Startup registers `/list`, `/status`, and `/bind` globally so they are available in servers where the bot is installed. Commands remain restricted to server text channels. Keep the script running to answer commands and prompts; stop it with Ctrl+C. This bot application should be dedicated to Queryfi: command synchronization replaces that application's global command set. If commands do not appear, check installation scopes, integration command permissions, and startup logs.

## Try the commands

Create a notebook for each course in Open Notebook, then run `/list` in Discord. Copy the complete notebook ID, including `notebook:`, and run `/bind subject_id:<copied-id>` in the desired text channel. Run `/status` and `/list` to confirm the binding. Restart the bot and run `/status` again to check persistence.

Notebook names are display labels, so renaming one keeps its bindings. The catalog is read on each command and includes archived notebooks. If a bound notebook is deleted, `/status` preserves its ID and reports that it is unavailable. API/database failures produce an error instead of a success message. After binding, write a normal text prompt in that channel, for example `Explain the main ideas in these sources`. The bot replies to your message with the notebook answer. No slash command or bot mention is needed.

`OpenNotebookSubjects` and `SurrealBindings` in `queryfi/storage.py` implement the existing course interfaces. SQLite and the temporary JSON catalog are no longer used. Existing files in `data/` are left untouched; old local bindings are not imported, so bind channels using notebook IDs.

## Notebook questions with Ollama

Use an Ollama **language** model already registered in Open Notebook, with working provider credentials/base URL. Leave `OPEN_NOTEBOOK_MODEL_ID` empty to select Open Notebook's default chat model at startup. To override it, set the registered `model:...` ID from `GET /api/models?type=language`, rather than an Ollama name such as `gemma4_e2b_q8:latest`. Restart the bot after changing the model or its default assignment. Queryfi calls Open Notebook; Open Notebook connects to Ollama using its existing configuration. A separate Ollama installation or direct bot-to-Ollama connection is unnecessary.

Every non-empty user text message in a bound server text channel becomes a question. Bot/webhook messages, system messages, DMs, threads, and attachment-only messages are ignored. Unbound channels receive no answer. Rebinding takes effect on the next question.

For each question, Queryfi lists the bound notebook's sources (including all pages), builds their full-content context through `/api/chat/context`, creates a notebook chat session, and calls `/api/chat/execute` with the selected Ollama model. It excludes notebook notes and sources from other notebooks. Each prompt creates a separate `Queryfi Discord question` session visible in Open Notebook; replies do not carry previous Discord conversation history. Notebook and source records are left unchanged. Source references returned by Open Notebook are preserved in the answer.

Empty or unprocessed notebooks receive an explanation instead of an ungrounded model call. API/model failures return a generic error in Discord, with details in the bot logs. Long answers are split across replies, and generated text cannot trigger mentions. Source context must fit the chosen model's context window; Queryfi sends full content and does not silently truncate or run a global search. `OPEN_NOTEBOOK_CHAT_TIMEOUT` sets the chat request timeout in seconds (default `180`); increase it for slow local inference. Other API/database requests retain their 15-second timeout.

The API contract is documented in the [Open Notebook API reference](https://github.com/lfnovo/open-notebook/blob/main/docs/7-DEVELOPMENT/api-reference.md). Ordinary Discord message access requires the [Message Content intent](https://discordpy.readthedocs.io/en/stable/intents.html#message-content).

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover commands, message routing, notebook source isolation and pagination, Ollama model selection, long replies, timeouts, API validation, parameterized database requests, error handling, and startup configuration without connecting to Discord. To also test real persistence, rebinding, and server isolation against your configured services:

```powershell
$env:QUERYFI_LIVE_TEST = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:QUERYFI_LIVE_TEST
```

The opt-in check requires two existing notebooks. It creates three temporary bindings under randomly chosen test server IDs and deletes those exact records afterward. It does not modify notebooks or sources. A real Discord check requires running the bot and invoking the commands in your server.
