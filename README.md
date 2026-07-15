# MK — Personal AI Operating System

> Your homelab, orchestrated by one intelligent agent. Talk to it. It talks back.

MK is a **personal AI operating system** that boots on minimal hardware and orchestrates your entire digital life: containers, storage, networking, backups, media, and services. It delegates reasoning to LLM providers (cloud or local) while maintaining local awareness and control.

**MK is not an app running on your computer. MK *is* the OS.**

The terminal is MK. The dashboard is MK. Your Telegram. Your voice. All MK.

---

## What MK Can Do

### Talk to your homelab
```
MK> check the status of my media server
{
  "containers": "12 running, 0 stopped",
  "disk": "78% used (3.2TB/4TB)",
  "plex": "active, 0 streams",
  "last_backup": "6h ago"
}
```

### Multi-step agent actions (ReAct loop)
```
You: restart plex and check if it came back healthy
MK: [thinking] I'll restart the container then verify...
MK: [action] docker restart plex
MK: [observation] Container restarted, port 32400 responding
MK: Done — Plex is back up and healthy (2.3s restart).
```

### Proactive notifications (MK talks first)
```
[MK → Telegram]
⚠️ Your tank pool is 92% full. Want me to clean old snapshots?

[MK → Telegram]
✓ Weekly report: 12 containers healthy, 847GB free, last backup 3h ago.
```

### Voice interface (all local, nothing leaves your network)
```
POST /voice  (audio) → Whisper STT → MK brain → Piper TTS → audio response
```

### Stream replies token-by-token (SSE + WebSocket)
The UI renders MK's response as it thinks — live cursor, growing text.

---


## Full Capability List

| Category | Capabilities |
|----------|-------------|
| **Chat** | Natural language → actions, streaming responses (SSE + WS), multi-step agent reasoning with tool execution, context-aware suggestions, persistent chat history |
| **Containers** | List, start, stop, restart Docker containers; view logs; manage stacks |
| **Storage** | ZFS pools/datasets/snapshots, disk health, SMART data, NFS/SMB shares |
| **Networking** | Interface config, firewall rules (nftables), WireGuard peers, DNS, reverse proxy, Tailscale |
| **Backups** | ZFS snapshots, ZFS send/receive replication, rsync, restic; scheduled via systemd timers; retention policies; real execution (not simulated) |
| **Media** | Disc ripping (MakeMKV), library stats, Plex/Sonarr/Radarr integration, media organization |
| **System** | Service management (start/stop/restart), system updates, power (reboot/shutdown), AI settings |
| **Security** | PIN auth + session tokens, role separation (admin/viewer), rate limiting, audit trail, dangerous-command detection, encrypted secrets |
| **Monitoring** | Live dashboard (CPU/RAM/disk/containers via WS push), proactive alerts (container down, disk full, backup stale), Prometheus metrics |
| **Voice** | Local Whisper.cpp STT + Piper TTS — talk to MK, get spoken answers (no cloud) |
| **Notifications** | Bell icon dropdown in UI, WS push to all clients, Telegram delivery |
| **Memory** | Short-term (session), long-term (SQLite + vector/semantic), system state tracking |
| **Local Brain** | Fine-tuned model runs locally (cost $0, preferred first, cloud fallback) |
| **Training** | Conversation capture (opt-in) → JSONL → ingest into dataset → retrain local model |
| **Plugins** | YAML-declared tool packs, CLI install/list/remove/search from git URLs |
| **Multi-user** | Admin (full control) vs Viewer (read-only) via separate PINs |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         MK AI Operating System v2.0                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Interfaces          Core Engine              LLM Providers                │
│  ──────────          ───────────              ─────────────                │
│  Terminal ─────┐     MKEngineV2               Claude (Opus/Sonnet/Haiku)   │
│  Web UI ───────┤     ├─ Agent Loop (ReAct)    OpenAI (GPT-5.x)            │
│  Telegram ─────┤───▶ ├─ Command Router        Gemini (3.5 Flash/Pro)       │
│  Discord ──────┤     ├─ Stream Agent          Groq / DeepSeek / Mistral   │
│  Voice ────────┘     ├─ Tool Executor         xAI (Grok 4.x)             │
│                      ├─ Ops Manager           Local Brain (Ollama/llama)   │
│                      └─ Memory Manager        + 10 more providers          │
│                                                                            │
│  Web Dashboard (React)     Safety Layer        Server Managers             │
│  ─────────────────────     ────────────        ────────────────            │
│  10 pages, live WS stats   Confirmation        Docker containers           │
│  Streaming chat panel      Audit trail         ZFS storage                 │
│  Notification center       Secrets (Fernet)    VMs (KVM/libvirt)           │
│  Theme toggle (dark/light) Rate limiting       LXC containers              │
│  Context suggestions       Shell injection     Network (nftables/WG)       │
│  Mobile responsive         validation          Backups (real execution)    │
│                                                Services (systemd)          │
│                                                Media (MakeMKV/Plex)        │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Observability: Prometheus metrics (/metrics) │ Structured JSON logs        │
│  mk_llm_requests_total{provider,tier=local|cloud}                          │
│  mk_llm_streams_total, mk_notifications_total, mk_training_captured_total  │
├──────────────────────────────────────────────────────────────────────────┤
│              Debian 12 │ Docker │ ZFS │ systemd │ Tailscale                 │
└──────────────────────────────────────────────────────────────────────────┘
```

---


## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Core engine | Python 3.10+ (async) | Fast prototyping, great LLM libraries |
| Web API | FastAPI + Uvicorn | Async, OpenAPI docs, WebSocket native |
| Web UI | React 19 + TypeScript + Vite + Tailwind | Fast, type-safe, dark-first design system |
| State management | Zustand (persisted) | Minimal, no boilerplate |
| Gateway | Node.js + TypeScript + Express | Telegram/Discord/Voice adapters |
| Database | SQLite (aiosqlite) + vector embeddings | Zero-config, embedded, fast |
| Package management | uv (Python) + pnpm (JS) | Fastest available |
| Testing | pytest (847 tests) + vitest (75+5) | Comprehensive, offline-friendly |
| Linting | ruff (Python) + biome (TS) | Sub-second, strict |
| LLM routing | Custom multi-provider router | Health-based fallback, cost-sorted |
| Encryption | Fernet (AES-128-CBC + HMAC, PBKDF2 480K) | Battle-tested, no deps |
| OS target | Debian 12 (Bookworm) | Stable, ZFS in repos |
| Containerization | Docker + docker-compose | Standard, declarative |

---

## Installation

### Option A: Full OS (MK boots as the computer)

```bash
# Flash Debian 12 minimal on a USB, install on your box, SSH in:
curl -sSL https://raw.githubusercontent.com/mohd2456/MK/main/os-build/install.sh | sudo bash
sudo reboot
# → Machine boots straight into MK. No login screen. Just talk.
```

### Option B: Service on existing Linux (recommended for testing)

```bash
git clone https://github.com/mohd2456/MK.git /opt/mk && cd /opt/mk
curl -LsSf https://astral.sh/uv/install.sh | sh  # install uv
uv sync                                            # install deps
export MK_PIN=your-secure-pin
uv run mk-web --host 0.0.0.0 --port 8080          # start web UI
# → Open http://your-ip:8080 in any browser
```

### Option C: Docker (zero commitment)

```bash
git clone https://github.com/mohd2456/MK.git && cd MK
docker compose up --build
# → Web UI on :8080
```

### Post-install: verify readiness

```bash
uv run mk-doctor
# → 16-point green/red readout with fix suggestions
```

---


## Configuration

### LLM Providers (at least one needed for AI features)

```yaml
# /etc/mk/config.yaml
llm_providers:
  - name: anthropic
    api_key_ref: anthropic_key
    model: claude-sonnet-4-6
    endpoint: https://api.anthropic.com/v1
    priority: 10

  - name: openai
    api_key_ref: openai_key
    model: gpt-5.4-mini
    endpoint: https://api.openai.com/v1
    priority: 8
```

Or just add a key at runtime: `/setkey sk-ant-your-key-here` (auto-detects provider).

### Local Brain (runs with no cloud keys at all)

```bash
export MK_LOCAL_BRAIN_URL=http://localhost:8080/v1  # llama.cpp server
export MK_LOCAL_BRAIN_MODEL=mk-brain               # your fine-tuned model
# MK prefers local (cost $0), falls back to cloud only if unreachable.
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `MK_PIN` | Admin PIN for web/API auth | `1234` |
| `MK_VIEWER_PIN` | Read-only viewer PIN (optional) | — |
| `MK_LOCAL_BRAIN_URL` | Local LLM server URL | — |
| `MK_LOCAL_BRAIN_KIND` | `openai` or `ollama` | `openai` |
| `MK_LOCAL_BRAIN_MODEL` | Model name to request | `mk-brain` |
| `MK_CAPTURE_CONVERSATIONS` | Enable training capture | `0` |
| `MK_CAPTURE_PATH` | JSONL output for captured data | `~/.mk/training/captured.jsonl` |
| `MK_AUDIT_DIR` | Security audit log directory | `~/.mk/audit` |
| `MK_PLUGIN_DIR` | Plugin install directory | `~/.mk/plugins` |
| `MK_COMPRESSION` | Enable prompt compression | `0` |
| `MK_WHISPER_MODEL` | Whisper GGML model path | `/opt/mk/models/whisper-base.bin` |
| `MK_PIPER_MODEL` | Piper TTS voice model path | `/opt/mk/models/en_US-lessac-medium.onnx` |

---

## API Reference (86 endpoints)

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login with PIN → session token |
| POST | `/api/v1/auth/logout` | Invalidate session |
| GET | `/api/v1/auth/status` | Check session validity |

### Chat & AI
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat/message` | Send message, get full response |
| POST | `/api/v1/chat/stream` | Send message, stream reply (SSE) |
| POST | `/api/v1/chat/agent` | Multi-step agent with tool execution (SSE) |
| GET | `/api/v1/chat/suggestions` | Context-aware action suggestions |
| GET | `/api/v1/chat/history` | Persistent conversation history |
| WS | `/ws/chat` | Real-time chat + live stats + notifications |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/dashboard/summary` | CPU/RAM/disk/containers/Tailscale |
| GET | `/api/v1/dashboard/alerts` | Active alerts from ops checks |
| GET | `/api/v1/dashboard/activity` | Security audit trail (newest first) |

### Storage
| GET | `/api/v1/storage/pools` | ZFS pools with health |
| GET | `/api/v1/storage/datasets` | ZFS datasets |
| GET | `/api/v1/storage/snapshots` | Snapshots |
| GET | `/api/v1/storage/disks` | Physical disks + SMART |

### Containers
| GET | `/api/v1/apps/containers` | All containers with state |
| POST | `/api/v1/apps/containers/{name}/restart` | Restart container |
| POST | `/api/v1/apps/containers/{name}/stop` | Stop container |
| POST | `/api/v1/apps/containers/{name}/start` | Start container |

### Network
| GET | `/api/v1/network/interfaces` | Network interfaces |
| GET/POST | `/api/v1/network/firewall` | nftables rules CRUD |
| GET/POST | `/api/v1/network/wireguard` | WireGuard interfaces + peers |
| GET/PUT | `/api/v1/network/dns` | DNS configuration |
| GET/POST | `/api/v1/network/proxy` | Reverse proxy sites |
| GET | `/api/v1/network/tailscale` | Tailscale mesh status |

### Protection (Backups)
| GET/POST | `/api/v1/protection/jobs` | Backup job CRUD |
| POST | `/api/v1/protection/jobs/{id}/run` | Trigger real backup execution |
| GET | `/api/v1/protection/jobs/{id}/history` | Run history with status/duration |
| GET/PUT | `/api/v1/protection/scrubs/{pool}` | ZFS scrub schedules |
| POST | `/api/v1/protection/scrubs/{pool}/run` | Run scrub |
| GET/POST | `/api/v1/protection/replication` | ZFS send/receive tasks |
| GET/POST | `/api/v1/protection/retention` | Retention policies |

### System
| GET | `/api/v1/system/info` | Hostname, OS, kernel, CPU, RAM, uptime |
| GET | `/api/v1/system/health` | Health checks |
| GET | `/api/v1/system/services` | systemd services |
| POST | `/api/v1/system/services/{name}/restart` | Restart service |
| GET | `/api/v1/system/updates` | Available updates |
| POST | `/api/v1/system/updates/apply` | Apply updates |
| POST | `/api/v1/system/power/reboot` | Reboot |
| POST | `/api/v1/system/power/shutdown` | Shutdown |
| GET/PUT | `/api/v1/system/ai/settings` | LLM provider/model config |

### Media
| GET | `/api/v1/media/drives` | Optical drives |
| POST | `/api/v1/media/rip` | Start disc rip |
| GET | `/api/v1/media/rip/status` | Rip progress |
| GET | `/api/v1/media/library/stats` | Library counts |
| POST | `/api/v1/media/organize` | Organize incoming files |

### Keys
| GET/POST/DELETE | `/api/v1/keys/llm` | LLM API key management |
| POST | `/api/v1/keys/telegram` | Set Telegram bot token |
| POST | `/api/v1/keys/tailscale` | Set Tailscale auth key |

### Observability
| GET | `/metrics` | Prometheus metrics (local/cloud hit rate, streams, captures) |

---


## CLI Commands

| Command | What it does |
|---------|-------------|
| `mk` | Main CLI — terminal REPL or daemon mode |
| `mk --mode terminal` | Interactive chat (boot sequence → `MK>` prompt) |
| `mk --mode daemon` | Background service (systemd, with Season 2 subsystems) |
| `mk-web` | Start the web API + React dashboard |
| `mk-doctor` | Pre-flight readiness check (16 checks, green/red + fixes) |
| `mk-doctor --json` | Machine-readable doctor output (for CI) |
| `mk-plugin list` | Show installed plugins |
| `mk-plugin install <url>` | Install plugin from git URL |
| `mk-plugin remove <name>` | Remove a plugin |
| `mk-plugin search <query>` | Search available plugins |
| `mk-validate-config` | Validate config YAML |

### Terminal commands (offline, no LLM needed)

```
status       — System overview (JSON)
health       — Full health report
containers   — Docker containers
storage      — ZFS pools
services     — Failed services
network      — Network interfaces
backup       — Backup health
hardware     — Hardware info
temps        — Temperatures
speedtest    — Internet speed
users        — User accounts
vms          — Virtual machines
lxc          — LXC containers
keys         — API keys configured
rip          — Disc ripper status
eject        — Eject disc
updates      — Check for updates
aboutme      — What MK knows about you
remember ... — Store a fact
forget ...   — Remove a fact
help         — Show all commands
```

---

## Code Structure (130 Python modules, 847 tests)

```
MK/
├── src/mk/                        # Python core (35K+ lines)
│   ├── core/                      # Engine + agent loop
│   │   ├── __init__.py            # Canonical Engine alias + create_engine()
│   │   ├── engine.py              # MKEngine: tools, routing, streaming, agent loop
│   │   ├── engine_v2.py           # MKEngineV2: plugins, planner, ops, semantic memory
│   │   ├── agent_loop.py          # ReAct reasoning loop (reason → act → observe)
│   │   ├── command_router.py      # Fast direct-command dispatch (no LLM needed)
│   │   ├── context.py             # Context builder for LLM prompts
│   │   └── models.py             # AgentResponse, AgentStep, Conversation, Role
│   ├── llm/                       # Multi-provider LLM layer
│   │   ├── router.py              # Health-based fallback, cost routing, streaming
│   │   ├── keys.py                # Auto-detect provider from key, 20+ providers
│   │   ├── provider_factory.py    # Build providers from keys, local brain registration
│   │   ├── providers/             # 7 provider implementations (all with stream())
│   │   ├── compression.py         # Optional Headroom context compression
│   │   ├── token_manager.py       # Budget tracking
│   │   └── prompt_compiler.py     # System prompt assembly
│   ├── memory/                    # Three-tier memory
│   │   ├── short_term.py          # Conversation buffer (token-budgeted)
│   │   ├── long_term.py           # Persistent user knowledge
│   │   ├── system_state.py        # Live homelab state tracking
│   │   ├── sqlite_store.py        # Durable key-value (async SQLite)
│   │   └── vector/               # Semantic search (embeddings + cosine sim)
│   ├── tools/                     # Extensible tool framework
│   │   ├── docker.py, ssh.py, files.py, media.py, system_monitor.py
│   │   └── registry.py           # Auto-discovery + registration
│   ├── server/                    # Homelab server managers
│   │   ├── backups.py             # Real ZFS/rsync/restic execution
│   │   ├── containers.py          # Docker lifecycle
│   │   ├── storage.py             # ZFS pools/datasets/snapshots
│   │   ├── network.py             # Interfaces, firewall, WireGuard, DNS, proxy
│   │   ├── vms.py, lxc.py         # KVM VMs, LXC containers
│   │   ├── services.py            # systemd service management
│   │   └── _shell.py             # Shell safety (validate_name, safe_quote, validate_calendar)
│   ├── ops/                       # Proactive operations
│   │   ├── scheduler.py           # Interval-based check runner
│   │   ├── alerts.py              # Alert manager (fire/resolve/dedup/cooldown)
│   │   ├── real_checks.py         # Real system checks (docker ps, zpool, df, curl)
│   │   ├── notifications.py       # Broadcaster → WS + Telegram delivery
│   │   ├── reports.py             # Weekly summary generator
│   │   └── manager.py            # OpsManager orchestrator
│   ├── web/                       # FastAPI web API + React serving
│   │   ├── app.py                 # 86 endpoints, WS, audit, streaming, rate limiting
│   │   ├── chat_history.py        # Persistent session-keyed chat (async SQLite)
│   │   └── serve.py              # Uvicorn launcher
│   ├── wrapper/                   # MKWrapper (the single choke point)
│   │   └── wrapper.py            # Validate → timeout → isolate → screen → suggest
│   ├── safety/                    # Security layer
│   │   ├── confirmation.py        # Dangerous-command detection
│   │   ├── audit.py               # Durable audit trail (JSONL, rotation)
│   │   ├── secrets.py             # Fernet-encrypted credential store
│   │   └── health.py             # Self-health monitoring
│   ├── training/                  # Local brain retraining
│   │   ├── capture.py             # Opt-in conversation capture → JSONL
│   │   └── ingest.py             # Deduplicate + merge into dataset
│   ├── plugins/                   # Plugin system
│   │   └── marketplace.py         # CLI install/list/remove/search
│   ├── config/                    # Configuration
│   │   ├── settings.py            # Pydantic models for all config
│   │   └── validate.py           # Config file validator
│   ├── brain/                     # Knowledge + routing
│   ├── planner/                   # Task decomposition + critique
│   ├── policy/                    # Policy engine (permissions, constraints)
│   ├── clock.py                   # Non-deprecated UTC helper
│   ├── metrics.py                 # Dependency-free Prometheus collector
│   ├── observability.py           # Structured logging + request tracing
│   ├── doctor.py                  # Pre-flight readiness checks (16 checks)
│   ├── boot.py                    # Boot sequence (hardware/network/AI probes)
│   ├── chat.py                    # Chat handler (offline + LLM)
│   └── main.py                   # CLI entry point (terminal/daemon)
├── webui/                         # React dashboard (75 tests)
│   └── src/
│       ├── pages/ (10)            # Dashboard, Storage, Apps, Network, Protection,
│       │                          #   Media, MediaManager, Keys, System, Login
│       ├── components/            # UI components (chat, dashboard, layout, etc.)
│       ├── stores/                # Zustand (auth, chat, ui, dashboard, notification)
│       ├── hooks/                 # useChat, useAuth, useWebSocket, useApi
│       └── lib/                   # API client, chat helpers, SSE consumer
├── gateway/                       # Messaging gateway (TypeScript, 5 tests)
│   └── src/
│       ├── telegram.ts            # Telegram bot adapter
│       ├── discord.ts             # Discord bot adapter
│       ├── voice.ts               # Whisper STT + Piper TTS (local)
│       └── bridge.ts             # HTTP bridge to MK core (retry + fallback)
├── training/                      # Fine-tuning pipeline
│   ├── data/                      # Training dataset (JSONL)
│   ├── scripts/
│   │   ├── finetune.py           # QLoRA fine-tuning (Qwen2.5-3B)
│   │   ├── ingest_captured.py    # Fold captured convos into dataset
│   │   └── quantize.py          # GGUF quantization for local deploy
│   └── README.md                 # Training + retraining + local brain docs
├── os-build/                      # Bootable Linux OS
│   ├── install.sh                 # Multi-distro installer (apt + dnf)
│   ├── mk.service                # systemd unit
│   └── build.sh                  # Image builder
├── docs/                          # Architecture + API docs
├── examples/plugins/              # Example plugin (backup-verifier)
├── pyproject.toml                 # Python project config (5 CLI entry points)
└── docker-compose.yml             # One-command deploy
```

---


## How the Code Works

### Request lifecycle (the MKWrapper pattern)

Every request — HTTP, WebSocket, Terminal — flows through **one choke point**:

```
User input
    → MKWrapper.validate_request()     (reject bad input → 422)
    → MKWrapper.chat() / stream_chat() (route to engine)
        → MKEngine.process() or stream_reply() or stream_agent()
            → CommandRouter (fast path, no LLM)  OR
            → AgentLoop (ReAct: reason → tool call → observe → loop)
    ← Result always wrapped: {content, ok, failure_type, actions, suggestions}
    ← Engine crash? Caught. Returns calm message, never 500.
```

### LLM routing (cost-sorted fallback)

```python
# The router tries providers in cost order (cheapest first):
# 1. Local brain ($0) — always preferred when configured
# 2. Groq/fast tier — cheap + fast
# 3. Cloud providers — by priority/cost
# If one fails: fall back to next (before first token for streaming)
router.complete(request)  # or router.stream(request)
```

### Streaming (three paths)

| Path | Use case | Yields |
|------|----------|--------|
| `stream_reply()` | Simple conversational (no tools) | Text chunks |
| `stream_agent()` | Multi-step with tool execution | thought/action/observation/answer frames |
| `stream_chat()` | Wrapper boundary (validates + isolates) | Text chunks (safe) |

### Memory (three tiers)

```
Short-term: last N messages (token-budgeted, in-memory)
Long-term:  "remember that I prefer dark mode" → SQLite + vector embeddings
System:     live tracking of machines, services, recent actions
```

### Safety (defense in depth)

```
1. Input validation:    shell-injection regex on ALL path params
2. Dangerous detection: rm -rf, DROP TABLE, dd → require confirmation
3. Audit trail:         every mutating API call logged (no bodies → no secrets)
4. Rate limiting:       100/min per IP + login lockout (10 attempts / 5 min)
5. Role separation:     admin PIN vs viewer PIN (MK_VIEWER_PIN)
6. Calendar validation: cron expressions validated before systemd unit write
7. Encrypted secrets:   Fernet + PBKDF2 480K iterations
```

---

## Development

### Running tests

```bash
# Full Python suite (847 tests)
uv run pytest tests/ -v

# Specific area
uv run pytest tests/core/ tests/llm/ tests/web/ -v

# WebUI (75 tests)
cd webui && pnpm test

# Gateway (5 tests)
cd gateway && pnpm test

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

### Adding a new tool

```python
# src/mk/tools/my_tool.py
async def my_tool(target: str, action: str = "info") -> str:
    """Describe what this tool does (shown to the LLM)."""
    result = await some_operation(target, action)
    return f"Done: {result}"

# Register in engine setup:
engine._tools["my_tool"] = my_tool
```

### Adding a new LLM provider

1. Create `src/mk/llm/providers/my_provider.py` implementing `LLMProvider`
2. Implement `complete()`, `stream()`, `health_check()`
3. Add to `PROVIDER_MODELS` and `PROVIDER_ENDPOINTS` in `keys.py`
4. Add key-pattern regex to `KEY_PATTERNS` for auto-detection

### Creating a plugin

```yaml
# my-plugin/plugin.yaml
name: my-plugin
version: 1.0.0
description: Does cool stuff
tools:
  - name: cool_tool
    description: Does the cool thing
    handler: tools.py:cool_tool
    params:
      - name: target
        type: string
        required: true
```

```bash
mk-plugin install /path/to/my-plugin
# or
mk-plugin install https://github.com/user/mk-plugin-cool.git
```

---

## Contributing

1. Fork → branch → code → test → PR
2. All public functions need docstrings + type hints
3. Tests must pass: `uv run pytest tests/ && cd webui && pnpm test`
4. Lint must pass: `uv run ruff check src/ tests/`
5. Format must pass: `uv run ruff format --check src/ tests/`

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Philosophy

MK was built with one belief: **your AI should work for you, not the other way around.**

- No cloud dependency (runs on local brain alone)
- No subscription lock-in (bring any provider key)
- No data harvesting (everything stays on your hardware)
- No complexity tax (one command to install, one PIN to login)

Your AI. Your hardware. Your rules.

---

*MK — Because your computer should be smarter than you.*
