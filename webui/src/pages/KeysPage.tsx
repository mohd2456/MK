/**
 * KeysPage — API Keys & Authentication Management
 * ==================================================
 * Central place to manage all credentials and integrations:
 * - LLM API Keys (OpenAI, Anthropic, Gemini, Groq, etc.)
 * - Telegram Bot Token + Allowed Chat IDs
 * - Tailscale Auth Key
 * - Service API Keys (Sonarr, Radarr, Plex, Overseerr)
 * - Webhook URLs
 * - MK PIN change
 */

import { useState } from "react";
import {
  Key,
  Bot,
  Globe,
  Tv,
  Shield,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Check,
  Copy,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

// ─── Types ───

interface StoredKey {
  id: string;
  provider: string;
  label: string;
  maskedValue: string;
  status: "active" | "expired" | "invalid" | "untested";
  addedAt: string;
}

// ─── Mock Data (replaced by real API calls in production) ───

const mockLLMKeys: StoredKey[] = [
  { id: "1", provider: "anthropic", label: "Anthropic (Claude)", maskedValue: "sk-ant-...****7f2a", status: "active", addedAt: "2024-12-15" },
  { id: "2", provider: "openai", label: "OpenAI", maskedValue: "sk-...****3bc1", status: "active", addedAt: "2024-11-20" },
  { id: "3", provider: "groq", label: "Groq", maskedValue: "gsk_...****9de4", status: "active", addedAt: "2025-01-05" },
];

const mockServiceKeys: StoredKey[] = [
  { id: "4", provider: "sonarr", label: "Sonarr", maskedValue: "a1b2c3...****", status: "active", addedAt: "2024-10-01" },
  { id: "5", provider: "radarr", label: "Radarr", maskedValue: "d4e5f6...****", status: "active", addedAt: "2024-10-01" },
  { id: "6", provider: "plex", label: "Plex Token", maskedValue: "xyz...****", status: "active", addedAt: "2024-09-15" },
  { id: "7", provider: "overseerr", label: "Overseerr", maskedValue: "abc...****", status: "untested", addedAt: "2025-01-10" },
];

// ─── Supported LLM Providers ───

const llmProviders = [
  { id: "anthropic", name: "Anthropic (Claude)", prefix: "sk-ant-" },
  { id: "openai", name: "OpenAI", prefix: "sk-" },
  { id: "gemini", name: "Google Gemini", prefix: "AI" },
  { id: "groq", name: "Groq", prefix: "gsk_" },
  { id: "mistral", name: "Mistral", prefix: "" },
  { id: "together", name: "Together AI", prefix: "" },
  { id: "fireworks", name: "Fireworks", prefix: "" },
  { id: "perplexity", name: "Perplexity", prefix: "pplx-" },
  { id: "deepseek", name: "DeepSeek", prefix: "sk-" },
  { id: "openrouter", name: "OpenRouter", prefix: "sk-or-" },
  { id: "cohere", name: "Cohere", prefix: "" },
  { id: "xai", name: "xAI (Grok)", prefix: "xai-" },
  { id: "nvidia", name: "NVIDIA NIM", prefix: "nvapi-" },
  { id: "sambanova", name: "SambaNova", prefix: "" },
  { id: "cerebras", name: "Cerebras", prefix: "" },
  { id: "hyperbolic", name: "Hyperbolic", prefix: "" },
];

// ─── Key Input Component ───

function KeyInput({
  placeholder,
  buttonLabel,
  onSubmit,
}: {
  placeholder: string;
  buttonLabel: string;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);

  const handleSubmit = () => {
    if (value.trim()) {
      onSubmit(value.trim());
      setValue("");
    }
  };

  return (
    <div className="flex gap-2">
      <div className="relative flex-1">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          className={cn(
            "w-full bg-mk-elevated rounded-[8px] px-3 py-2.5 pr-10",
            "text-sm text-mk-text-primary font-mono",
            "placeholder:text-mk-text-muted",
            "border border-mk-border",
            "focus:outline-none focus:ring-1 focus:ring-mk-accent focus:border-mk-accent",
            "transition-all duration-[150ms]"
          )}
        />
        <button
          onClick={() => setVisible(!visible)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-mk-text-muted hover:text-mk-text-primary"
          tabIndex={-1}
        >
          {visible ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
      <Button size="sm" onClick={handleSubmit} disabled={!value.trim()}>
        <Plus size={14} />
        {buttonLabel}
      </Button>
    </div>
  );
}

// ─── Key Row Component ───

function KeyRow({ keyData, onDelete }: { keyData: StoredKey; onDelete: (id: string) => void }) {
  const [copied, setCopied] = useState(false);

  const statusColors = {
    active: "success",
    expired: "error",
    invalid: "error",
    untested: "warning",
  } as const;

  return (
    <div className="flex items-center gap-3 py-3 px-4 rounded-[8px] bg-mk-elevated border border-mk-border hover:border-mk-border-strong transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-mk-text-primary">{keyData.label}</span>
          <Badge variant={statusColors[keyData.status]}>{keyData.status}</Badge>
        </div>
        <span className="text-xs font-mono text-mk-text-muted">{keyData.maskedValue}</span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-[10px] text-mk-text-muted hidden sm:block">{keyData.addedAt}</span>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => {
            navigator.clipboard.writeText(keyData.maskedValue);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          aria-label="Copy"
        >
          {copied ? <Check size={12} className="text-mk-success" /> : <Copy size={12} />}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onDelete(keyData.id)}
          aria-label="Delete"
          className="hover:text-mk-error"
        >
          <Trash2 size={12} />
        </Button>
      </div>
    </div>
  );
}

// ─── Main Page ───

export function KeysPage() {
  const [llmKeys, setLlmKeys] = useState(mockLLMKeys);
  const [serviceKeys, setServiceKeys] = useState(mockServiceKeys);
  const [telegramToken, setTelegramToken] = useState("7012345678:AAG...**masked**");
  const [telegramChats, setTelegramChats] = useState(["123456789"]);
  const [tailscaleKey, setTailscaleKey] = useState("tskey-auth-...****");
  const [newChatId, setNewChatId] = useState("");

  const handleDeleteKey = (id: string) => {
    setLlmKeys((keys) => keys.filter((k) => k.id !== id));
    setServiceKeys((keys) => keys.filter((k) => k.id !== id));
  };

  const handleAddLLMKey = (value: string) => {
    // Auto-detect provider from prefix
    const detected = llmProviders.find((p) => p.prefix && value.startsWith(p.prefix));
    const newKey: StoredKey = {
      id: String(Date.now()),
      provider: detected?.id || "unknown",
      label: detected?.name || "Unknown Provider",
      maskedValue: value.slice(0, 6) + "...****" + value.slice(-4),
      status: "untested",
      addedAt: new Date().toISOString().split("T")[0],
    };
    setLlmKeys((keys) => [...keys, newKey]);

    // In production: POST /api/v1/keys/llm { provider, key }
  };

  const handleAddServiceKey = (provider: string, value: string) => {
    const newKey: StoredKey = {
      id: String(Date.now()),
      provider,
      label: provider.charAt(0).toUpperCase() + provider.slice(1),
      maskedValue: value.slice(0, 4) + "...****" + value.slice(-4),
      status: "untested",
      addedAt: new Date().toISOString().split("T")[0],
    };
    setServiceKeys((keys) => [...keys, newKey]);
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-mk-text-primary">Keys & Auth</h1>
          <p className="text-sm text-mk-text-muted mt-0.5">Manage API keys, tokens, and integrations</p>
        </div>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} />
          Test All
        </Button>
      </div>

      <Tabs defaultValue="llm">
        <TabsList>
          <TabsTrigger value="llm">
            <Key size={14} className="mr-1.5" />
            AI Providers
          </TabsTrigger>
          <TabsTrigger value="telegram">
            <Bot size={14} className="mr-1.5" />
            Telegram
          </TabsTrigger>
          <TabsTrigger value="tailscale">
            <Globe size={14} className="mr-1.5" />
            Tailscale
          </TabsTrigger>
          <TabsTrigger value="services">
            <Tv size={14} className="mr-1.5" />
            Services
          </TabsTrigger>
          <TabsTrigger value="security">
            <Shield size={14} className="mr-1.5" />
            Security
          </TabsTrigger>
        </TabsList>

        {/* ═══ AI Providers ═══ */}
        <TabsContent value="llm">
          <Card>
            <CardContent className="p-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Add API Key</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  Paste any LLM API key — MK auto-detects the provider from the prefix.
                  Supports: {llmProviders.slice(0, 8).map((p) => p.name).join(", ")}, and more.
                </p>
                <KeyInput
                  placeholder="sk-ant-... or sk-... or gsk_... (paste your key)"
                  buttonLabel="Add Key"
                  onSubmit={handleAddLLMKey}
                />
              </div>

              <div className="border-t border-mk-border pt-4">
                <h3 className="text-sm font-semibold text-mk-text-primary mb-3">
                  Stored Keys ({llmKeys.length})
                </h3>
                <div className="space-y-2">
                  {llmKeys.map((key) => (
                    <KeyRow key={key.id} keyData={key} onDelete={handleDeleteKey} />
                  ))}
                  {llmKeys.length === 0 && (
                    <p className="text-sm text-mk-text-muted text-center py-6">
                      No API keys configured. Add one above to enable AI features.
                    </p>
                  )}
                </div>
              </div>

              <div className="border-t border-mk-border pt-4">
                <p className="text-xs text-mk-text-muted">
                  MK routes requests to the cheapest healthy provider automatically.
                  Add multiple keys for failover. Keys are stored encrypted at rest.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ═══ Telegram ═══ */}
        <TabsContent value="telegram">
          <Card>
            <CardContent className="p-5 space-y-5">
              {/* Bot Token */}
              <div>
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Bot Token</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  Get from <span className="text-mk-accent">@BotFather</span> on Telegram.
                  Send /newbot and follow the prompts.
                </p>
                <KeyInput
                  placeholder="7012345678:AAG... (bot token from BotFather)"
                  buttonLabel="Save"
                  onSubmit={(val) => setTelegramToken(val.slice(0, 10) + "...**masked**")}
                />
                {telegramToken && (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge variant="success">Connected</Badge>
                    <span className="text-xs font-mono text-mk-text-muted">{telegramToken}</span>
                  </div>
                )}
              </div>

              {/* Allowed Chat IDs */}
              <div className="border-t border-mk-border pt-4">
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Allowed Chat IDs</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  Only these chats can talk to MK. Send /start to your bot, then use
                  <span className="font-mono text-mk-accent"> @userinfobot</span> to get your ID.
                </p>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={newChatId}
                    onChange={(e) => setNewChatId(e.target.value)}
                    placeholder="Chat ID (e.g., 123456789)"
                    className={cn(
                      "flex-1 bg-mk-elevated rounded-[8px] px-3 py-2.5",
                      "text-sm text-mk-text-primary font-mono",
                      "placeholder:text-mk-text-muted border border-mk-border",
                      "focus:outline-none focus:ring-1 focus:ring-mk-accent"
                    )}
                  />
                  <Button
                    size="sm"
                    onClick={() => {
                      if (newChatId.trim()) {
                        setTelegramChats((c) => [...c, newChatId.trim()]);
                        setNewChatId("");
                      }
                    }}
                    disabled={!newChatId.trim()}
                  >
                    <Plus size={14} />
                    Add
                  </Button>
                </div>
                <div className="space-y-1.5">
                  {telegramChats.map((chatId, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between py-2 px-3 rounded-[6px] bg-mk-elevated border border-mk-border"
                    >
                      <span className="text-sm font-mono text-mk-text-primary">{chatId}</span>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setTelegramChats((c) => c.filter((_, idx) => idx !== i))}
                        className="hover:text-mk-error"
                      >
                        <Trash2 size={12} />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-mk-border pt-4">
                <p className="text-xs text-mk-text-muted">
                  Once configured, you can message MK directly on Telegram.
                  All commands, media requests, and server management work through chat.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ═══ Tailscale ═══ */}
        <TabsContent value="tailscale">
          <Card>
            <CardContent className="p-5 space-y-5">
              <div>
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Auth Key</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  Get from{" "}
                  <a
                    href="https://login.tailscale.com/admin/settings/keys"
                    target="_blank"
                    rel="noopener"
                    className="text-mk-accent hover:underline"
                  >
                    Tailscale Admin → Settings → Keys
                  </a>
                  . Use a reusable, pre-approved key with no expiry for servers.
                </p>
                <KeyInput
                  placeholder="tskey-auth-kABC123... (from admin console)"
                  buttonLabel="Connect"
                  onSubmit={(val) => setTailscaleKey(val.slice(0, 12) + "...****")}
                />
                {tailscaleKey && (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge variant="success">Connected</Badge>
                    <span className="text-xs font-mono text-mk-text-muted">{tailscaleKey}</span>
                  </div>
                )}
              </div>

              <div className="border-t border-mk-border pt-4">
                <h3 className="text-sm font-semibold text-mk-text-primary mb-2">Tailscale Settings</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-mk-text-secondary">Hostname</span>
                    <span className="text-sm font-mono text-mk-text-primary">mk-brain</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-mk-text-secondary">SSH Enabled</span>
                    <Badge variant="success">Yes</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-mk-text-secondary">Accept Routes</span>
                    <Badge variant="success">Yes</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-mk-text-secondary">Exit Node</span>
                    <Badge variant="warning">Off</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-mk-text-secondary">Advertise Routes</span>
                    <span className="text-sm font-mono text-mk-text-primary">192.168.1.0/24</span>
                  </div>
                </div>
              </div>

              <div className="border-t border-mk-border pt-4">
                <p className="text-xs text-mk-text-muted">
                  Tailscale gives you secure access to MK from anywhere — no port forwarding needed.
                  Install Tailscale on your phone/laptop to reach this dashboard remotely.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ═══ Services ═══ */}
        <TabsContent value="services">
          <Card>
            <CardContent className="p-5 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Media Services</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  API keys for Sonarr, Radarr, Plex, Overseerr, and other homelab services.
                </p>
              </div>

              <div className="space-y-2">
                {serviceKeys.map((key) => (
                  <KeyRow key={key.id} keyData={key} onDelete={handleDeleteKey} />
                ))}
              </div>

              <div className="border-t border-mk-border pt-4 space-y-3">
                <h4 className="text-xs font-semibold text-mk-text-muted uppercase tracking-wider">Add Service Key</h4>

                {[
                  { id: "sonarr", label: "Sonarr", placeholder: "Sonarr API key (Settings → General)" },
                  { id: "radarr", label: "Radarr", placeholder: "Radarr API key (Settings → General)" },
                  { id: "plex", label: "Plex Token", placeholder: "Plex token (from browser inspector)" },
                  { id: "overseerr", label: "Overseerr", placeholder: "Overseerr API key (Settings)" },
                  { id: "transmission", label: "Transmission", placeholder: "Transmission RPC password" },
                ].map((svc) => (
                  <div key={svc.id}>
                    <label className="text-xs text-mk-text-secondary mb-1 block">{svc.label}</label>
                    <KeyInput
                      placeholder={svc.placeholder}
                      buttonLabel="Save"
                      onSubmit={(val) => handleAddServiceKey(svc.id, val)}
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ═══ Security ═══ */}
        <TabsContent value="security">
          <Card>
            <CardContent className="p-5 space-y-5">
              {/* Change PIN */}
              <div>
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Change Dashboard PIN</h3>
                <p className="text-xs text-mk-text-muted mb-3">
                  This PIN protects the web dashboard. 4-8 digits.
                </p>
                <div className="flex gap-2 max-w-sm">
                  <input
                    type="password"
                    placeholder="Current PIN"
                    className={cn(
                      "flex-1 bg-mk-elevated rounded-[8px] px-3 py-2.5",
                      "text-sm text-mk-text-primary",
                      "border border-mk-border",
                      "focus:outline-none focus:ring-1 focus:ring-mk-accent"
                    )}
                  />
                  <input
                    type="password"
                    placeholder="New PIN"
                    className={cn(
                      "flex-1 bg-mk-elevated rounded-[8px] px-3 py-2.5",
                      "text-sm text-mk-text-primary",
                      "border border-mk-border",
                      "focus:outline-none focus:ring-1 focus:ring-mk-accent"
                    )}
                  />
                  <Button size="sm">Save</Button>
                </div>
              </div>

              {/* Active Sessions */}
              <div className="border-t border-mk-border pt-4">
                <h3 className="text-sm font-semibold text-mk-text-primary mb-2">Active Sessions</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between py-2 px-3 rounded-[6px] bg-mk-elevated border border-mk-border">
                    <div>
                      <span className="text-sm text-mk-text-primary">This device</span>
                      <p className="text-xs text-mk-text-muted">Current session</p>
                    </div>
                    <Badge variant="success">Active</Badge>
                  </div>
                </div>
              </div>

              {/* Secrets Store */}
              <div className="border-t border-mk-border pt-4">
                <h3 className="text-sm font-semibold text-mk-text-primary mb-1">Encryption</h3>
                <p className="text-xs text-mk-text-muted">
                  All keys are encrypted at rest using Fernet symmetric encryption (AES-128-CBC + HMAC).
                  The encryption key is derived from a master passphrase via PBKDF2 (480,000 iterations).
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <Badge variant="success">Vault Encrypted</Badge>
                  <span className="text-xs text-mk-text-muted">~/.mk/secrets/vault.enc</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
