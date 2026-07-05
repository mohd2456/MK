# MK - Personal AI Operating System

> Your entire digital life, orchestrated by one intelligent agent.

MK is a personal AI operating system that runs on minimal hardware (a MacBook Pro 2010 with 6GB RAM) and orchestrates everything: your homelab, media servers, Docker containers, SSH sessions, files, and services. It delegates heavy computation to remote LLM providers while maintaining local awareness and control.

**MK is not an app. MK is the OS. The terminal is MK. MK is the terminal.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          MK AI Operating System                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────────────┐ │
│  │   Terminal   │────▶│              │     │   Telegram Gateway    │ │
│  │   (local)   │     │   MK Core    │◀───▶│   (Node.js/TS)       │ │
│  └─────────────┘     │   Engine     │     └──────────────────────┘ │
│                       │              │                               │
│  ┌─────────────┐     │  ┌────────┐  │     ┌──────────────────────┐ │
│  │  Internal   │◀───▶│  │ Agent  │  │     │   LLM Providers      │ │
│  │  HTTP API   │     │  │  Loop  │  │────▶│   - OpenAI           │ │
│  └─────────────┘     │  └────────┘  │     │   - Anthropic        │ │
│                       │              │     │   - Google            │ │
│                       └──────┬───────┘     │   - Ollama (local)   │ │
│                              │             │   - Groq             │ │
│                       ┌──────┴───────┐     │   - OpenRouter       │ │
│                       │              │     └──────────────────────┘ │
│  ┌─────────┐   ┌─────┴─────┐  ┌─────┴─────┐                       │
│  │ Safety  │   │  Memory   │  │   Tools    │                       │
│  │ Layer   │   │  System   │  │  Registry  │                       │
│  ├─────────┤   ├───────────┤  ├────────────┤                       │
│  │Confirm  │   │Short-term │  │SSH         │                       │
│  │Audit    │   │Long-term  │  │Files       │                       │
│  │Secrets  │   │Sys State  │  │Docker      │                       │
│  │Health   │   │           │  │Media       │                       │
│  └─────────┘   └───────────┘  │System Mon  │                       │
│                                └────────────┘                       │
│                                                                       │
├─────────────────────────────────────────────────────────────────────┤
│              Minimal Linux │ Kernel + Networking + MK                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### Intelligent Agent Loop

- **ReAct pattern**: Reason, Act, Observe, Respond
- **Multi-step planning**: Breaks complex tasks into executable steps
- **Context-aware**: Remembers your preferences, system state, and history
- **Self-correcting**: Detects errors and adjusts approach automatically

### Multi-Provider LLM Integration

- **6 providers**: OpenAI, Anthropic, Google Gemini, Ollama (local), Groq, OpenRouter
- **Intelligent routing**: Routes to the best provider based on task, cost, latency
- **Automatic fallback**: If one provider fails, seamlessly switches to another
- **Token management**: Tracks usage, enforces budgets, optimizes context windows
- **Prompt compilation**: Assembles optimized prompts from system state and context

### Three-Tier Memory System

| Tier | Purpose | Persistence |
|------|---------|-------------|
| Short-term | Current conversation context | Session |
| Long-term | User preferences, learned patterns, knowledge | Permanent |
| System State | Homelab status, service health, schedules | Real-time |

### Tool Framework

Extensible tool system with auto-discovery:

| Tool | Capability |
|------|-----------|
| **SSH** | Remote command execution on any machine |
| **Files** | Read, write, search, manage files |
| **Docker** | Container lifecycle management |
| **Media** | Media server control, library management |
| **System Monitor** | Resource tracking, process management |

### Safety Layer

- **Confirmation**: Asks before dangerous actions (rm -rf, drop database, shutdown)
- **Audit Trail**: Logs every action with timestamp, params, result, initiator
- **Encrypted Secrets**: API keys stored encrypted at rest (Fernet + PBKDF2)
- **Self-Monitoring**: Tracks own CPU, memory, disk usage; alerts when struggling

### Two-Way Communication

- **At home**: Talk to MK directly in the terminal
- **Away**: MK reaches you on Telegram
- **Proactive**: MK initiates contact for alerts, updates, completions
- **Bidirectional**: Reply from your phone to give MK commands

### MK OS

- Stripped-down minimal Linux
- Kernel + networking + MK. Nothing else.
- Boots directly into MK terminal mode
- systemd service with auto-restart and hardening

---

## Directory Structure

```
MK/
├── src/mk/                    # Python core engine
│   ├── core/                  # Agent loop, engine, context, models
│   │   ├── engine.py          # Main orchestrator
│   │   ├── agent_loop.py      # ReAct reasoning loop
│   │   ├── context.py         # Context management
│   │   ├── command_router.py  # Command classification
│   │   └── models.py          # Core data models
│   ├── llm/                   # Multi-provider LLM integration
│   │   ├── providers/         # Provider implementations (6 providers)
│   │   ├── router.py          # Intelligent provider selection
│   │   ├── token_manager.py   # Token tracking and budgets
│   │   └── prompt_compiler.py # Prompt assembly and optimization
│   ├── memory/                # Three-tier memory system
│   │   ├── short_term.py      # Conversation context
│   │   ├── long_term.py       # Persistent knowledge
│   │   ├── system_state.py    # Live system state
│   │   └── manager.py         # Memory coordination
│   ├── tools/                 # Extensible tool framework
│   │   ├── registry.py        # Tool discovery and registration
│   │   ├── ssh.py             # Remote execution
│   │   ├── files.py           # File operations
│   │   ├── docker.py          # Container management
│   │   ├── media.py           # Media services
│   │   └── system_monitor.py  # Resource monitoring
│   ├── safety/                # Safety mechanisms
│   │   ├── confirmation.py    # Dangerous action detection
│   │   ├── audit.py           # Action audit logging
│   │   ├── secrets.py         # Encrypted credential storage
│   │   └── health.py          # Self-health monitoring
│   ├── api/                   # Internal HTTP API
│   │   └── server.py          # Gateway communication endpoints
│   └── config/                # Configuration management
│       └── settings.py        # Pydantic-validated settings
├── gateway/                   # Telegram messaging gateway (TypeScript)
│   ├── src/
│   │   ├── index.ts           # Entry point
│   │   ├── telegram.ts        # Telegraf bot implementation
│   │   ├── bridge.ts          # HTTP bridge to MK core
│   │   ├── config.ts          # Environment configuration
│   │   └── types.ts           # TypeScript type definitions
│   ├── package.json
│   └── tsconfig.json
├── os-build/                  # Minimal Linux OS build
│   ├── build.sh               # Main build script
│   ├── Dockerfile             # Docker build environment
│   ├── mk.service             # systemd service file
│   ├── mk-shell.sh            # Login shell wrapper
│   └── motd                   # MK branding
├── tests/                     # Test suite
├── config.example.yaml        # Example configuration
└── pyproject.toml             # Python project config
```

---

## Setup

### Prerequisites

- Python 3.9+
- Node.js 22+
- `uv` (Python package manager)
- `pnpm` (Node.js package manager)

### Installation

```bash
# Clone the repository
git clone https://github.com/mohd2456/MK.git
cd MK

# Install Python dependencies
uv sync

# Install gateway dependencies
cd gateway
pnpm install
pnpm build
cd ..

# Copy and configure
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

### Quick Start

```bash
# Run MK in terminal mode
uv run mk --mode terminal

# Or run the gateway for Telegram access
cd gateway && pnpm start
```

---

## Configuration

MK uses a YAML configuration file (`config.yaml`):

```yaml
# LLM Providers (configure at least one)
llm_providers:
  - name: openai
    api_key_ref: openai_api_key    # Reference to encrypted secret
    model: gpt-4-turbo
    endpoint: https://api.openai.com/v1
    priority: 10

  - name: anthropic
    api_key_ref: anthropic_api_key
    model: claude-3-sonnet
    endpoint: https://api.anthropic.com/v1
    priority: 8

  - name: ollama
    model: llama3
    endpoint: http://localhost:11434
    priority: 5

# Memory settings
memory:
  short_term_max_messages: 50
  context_window_budget: 8000

# Safety settings
safety:
  max_iterations: 10
  require_confirmation: true
  audit_enabled: true

# Gateway
gateway:
  telegram_bot_token_ref: telegram_token
  allowed_chat_ids:
    - "123456789"
```

### Storing Secrets

```bash
# Store API keys encrypted
export MK_SECRETS_PASSPHRASE="your-master-passphrase"
uv run python -c "
from mk.safety.secrets import SecretsManager
sm = SecretsManager()
sm.store_secret('openai_api_key', 'sk-...')
sm.store_secret('telegram_token', '1234567890:ABC...')
"
```

---

## Usage Examples

### Terminal Mode

```
$ mk

  ███╗   ███╗██╗  ██╗
  ████╗ ████║██║ ██╔╝
  ██╔████╔██║█████╔╝
  ██║╚██╔╝██║██╔═██╗
  ██║ ╚═╝ ██║██║  ██╗
  ╚═╝     ╚═╝╚═╝  ╚═╝

You: Check the status of my media server

MK: Connecting to media-server via SSH...
    Plex Media Server: Running (uptime: 14d 6h)
    Library: 2,847 movies, 412 TV shows
    Active streams: 0
    Disk usage: 78% (3.2TB / 4TB)
    Everything looks healthy.

You: Download the latest episode of that show I was watching

MK: Last show you watched: "Severance" S2E06
    Searching... Found: S2E07 (aired yesterday)
    ⚠️  This will download ~4GB to media-server:/data/tv/
    Confirm? [y/N]

You: y

MK: Download queued. I'll let you know when it's ready.
```

### Telegram Interaction

```
[MK -> You]
Hey - your media server disk is at 92%.
Want me to clean up old transcodes? (~180GB reclaimable)

[You -> MK]
Yes, clean them up

[MK -> You]
Done. Removed 847 transcode files (183GB freed).
Disk now at 74%. All good.

[MK -> You]
That episode of Severance just finished downloading.
Ready to watch whenever you want.
```

### Homelab Management

```
You: What's running on my Docker host?

MK: docker-host (192.168.1.50):
    - nginx-proxy    : Up 30d  | 12MB RAM
    - plex           : Up 14d  | 890MB RAM
    - sonarr         : Up 14d  | 210MB RAM
    - radarr         : Up 14d  | 185MB RAM
    - transmission   : Up 14d  | 45MB RAM
    - home-assistant : Up 7d   | 320MB RAM
    - pihole         : Up 30d  | 88MB RAM

    Total: 7 containers | 1.7GB RAM used

You: Restart home-assistant, it's been acting up

MK: ⚠️  This will restart the home-assistant container.
    Smart home automations will pause briefly.
    Confirm? [y/N]
```

---

## LLM Providers

MK supports multiple LLM providers with intelligent fallback:

| Provider | Best For | Local? | Cost |
|----------|----------|--------|------|
| OpenAI | General tasks, coding | No | $$ |
| Anthropic | Complex reasoning, safety | No | $$ |
| Google Gemini | Long context, multimodal | No | $ |
| Ollama | Privacy, offline use | Yes | Free |
| Groq | Speed (lowest latency) | No | $ |
| OpenRouter | Model variety, fallback | No | Varies |

### Provider Selection Logic

1. Route based on task type (coding -> OpenAI, reasoning -> Anthropic)
2. Respect cost budgets and rate limits
3. Fall back to next provider on failure
4. Use local Ollama when privacy is needed or network is down

---

## Safety

### Dangerous Action Detection

MK recognizes and blocks dangerous operations until confirmed:

- `rm -rf`, `rm -r` (recursive deletion)
- `DROP DATABASE`, `DROP TABLE`, `TRUNCATE`
- `shutdown`, `reboot`
- `mkfs`, `dd`, `fdisk` (disk operations)
- `git push --force`, `git reset --hard`
- `curl | bash` (piped execution)
- `chmod 777`, `iptables -F`
- Custom patterns can be added

### Audit Trail

Every action is logged:

```json
{
  "timestamp": "2024-01-15T14:30:22.123456",
  "action": "ssh_execute",
  "params": {"host": "media-server", "command": "docker restart plex"},
  "result": "Container restarted successfully",
  "initiator": "user",
  "success": true,
  "duration_ms": 2340
}
```

### Secret Storage

- Fernet symmetric encryption (AES-128-CBC + HMAC)
- Key derived from passphrase via PBKDF2 (480,000 iterations)
- Salt stored separately, rotatable
- Secrets never logged or exposed in plaintext

---

## Building MK OS

Create a minimal Linux image that boots directly into MK:

```bash
cd os-build

# Using Docker (recommended)
./build.sh

# Specify architecture
./build.sh --arch arm64

# Custom output directory
./build.sh --output /path/to/images
```

The resulting image contains:
- Linux kernel with minimal modules
- systemd + networkd (DHCP)
- Python 3.9+, Node.js 22
- MK (core + gateway)
- No GUI, no desktop, no browser, no bloat

On boot:
1. Kernel loads
2. systemd starts mk.service
3. Login shell is mk-shell (not bash)
4. User sees MK, not a command prompt

---

## Development

### Running Tests

```bash
# All Python tests
uv run pytest tests/ -v

# Specific module
uv run pytest tests/safety/ -v
uv run pytest tests/core/ -v

# Build gateway
cd gateway && pnpm build

# Type checking
uv run mypy src/mk/
```

### Project Conventions

- **Python**: Type hints everywhere, docstrings on all public APIs
- **Async**: All I/O operations are async (asyncio-based)
- **Models**: Pydantic for data validation and serialization
- **HTTP**: httpx for outbound HTTP calls
- **Testing**: pytest + pytest-asyncio, mock external dependencies
- **TypeScript**: Strict mode, Zod for runtime validation

### Adding a New Tool

```python
from mk.tools.base import Tool, ToolResult

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Does something useful"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target to act on"}
            },
            "required": ["target"]
        }

    async def execute(self, **kwargs) -> ToolResult:
        target = kwargs["target"]
        # Do the thing
        return ToolResult(success=True, output=f"Done: {target}")
```

### Adding a New LLM Provider

Implement the provider interface in `src/mk/llm/providers/` and register it in the router configuration.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-thing`)
3. Write tests for your changes
4. Ensure all tests pass (`uv run pytest tests/`)
5. Submit a pull request

### Code Style

- Follow existing patterns in the codebase
- All public functions need docstrings
- Type hints on all function signatures
- Keep modules focused and cohesive

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

MK was built with the philosophy that AI should work for you, not the other way around. No cloud dependency, no subscription lock-in, no data harvesting. Your AI, your hardware, your rules.

---

*MK - Because your computer should be smarter than you.*
