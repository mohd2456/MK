/**
 * Telegram bot — enhanced with rich commands.
 *
 * Commands:
 *   /start         - Introduction
 *   /status        - System health
 *   /containers    - Docker container status
 *   /storage       - ZFS pool status
 *   /services      - Failed services
 *   /ip            - Public IP
 *   /temps         - System temperatures
 *   /backup        - Backup health
 *   /rip           - Disc ripper status
 *   /wake [name]   - Wake-on-LAN a machine
 *   /speedtest     - Internet speed test
 *   /logs [name]   - Service logs
 *   /help          - All commands
 *
 * Any plain text message is sent to MK as natural language.
 */

import { Telegraf } from "telegraf";
import type { Context } from "telegraf";
import { MKBridge } from "./bridge.js";
import { isChatAllowed } from "./config.js";
import type { GatewayConfig } from "./types.js";

/**
 * Create and configure the Telegram bot with all commands.
 */
export function createTelegramBot(
  config: GatewayConfig,
  bridge: MKBridge
): Telegraf {
  const bot = new Telegraf(config.telegramBotToken);

  // --- Auth middleware ---
  const requireAuth = async (ctx: Context, next: () => Promise<void>) => {
    const chatId = ctx.chat?.id?.toString() || "";
    if (!isChatAllowed(chatId, config)) {
      await ctx.reply("⛔ Access denied. Chat ID not authorized.");
      return;
    }
    await next();
  };

  bot.use(requireAuth);

  // --- /start ---
  bot.start(async (ctx) => {
    await ctx.reply(
      "🖥️ *MK OS* — Personal AI Operating System\n\n" +
        "Send me any message and I'll handle it.\n\n" +
        "Quick commands:\n" +
        "/status — System health\n" +
        "/containers — Docker status\n" +
        "/storage — ZFS pools\n" +
        "/services — Failed services\n" +
        "/backup — Backup health\n" +
        "/help — All commands",
      { parse_mode: "Markdown" }
    );
  });

  // --- /help ---
  bot.command("help", async (ctx) => {
    await ctx.reply(
      "*MK Commands:*\n\n" +
        "📊 *Status*\n" +
        "/status — Full system overview\n" +
        "/containers — Docker containers\n" +
        "/storage — ZFS pool health\n" +
        "/services — Failed services\n" +
        "/temps — CPU/system temperatures\n" +
        "/ip — Public IP address\n\n" +
        "💾 *Backup & Media*\n" +
        "/backup — Backup job health\n" +
        "/rip — Disc ripper status\n\n" +
        "🌐 *Network*\n" +
        "/speedtest — Internet speed\n" +
        "/wake — Wake-on-LAN\n\n" +
        "📋 *Logs*\n" +
        "/logs [service] — Recent logs\n\n" +
        "💬 *Or just talk to me naturally.*",
      { parse_mode: "Markdown" }
    );
  });

  // --- /status ---
  bot.command("status", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("system", "overview", {});
      await ctx.reply(formatResponse("System Status", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get status. MK core may be restarting.");
    }
  });

  // --- /containers ---
  bot.command("containers", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("containers", "list", {});
      await ctx.reply(formatResponse("Containers", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get container status.");
    }
  });

  // --- /storage ---
  bot.command("storage", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("storage", "list_pools", {});
      await ctx.reply(formatResponse("Storage", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get storage status.");
    }
  });

  // --- /services ---
  bot.command("services", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("services", "failed", {});
      await ctx.reply(formatResponse("Services", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get service status.");
    }
  });

  // --- /backup ---
  bot.command("backup", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("backups", "health", {});
      await ctx.reply(formatResponse("Backups", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get backup status.");
    }
  });

  // --- /rip ---
  bot.command("rip", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("ripper", "disc_status", {});
      await ctx.reply(formatResponse("Disc Ripper", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get ripper status.");
    }
  });

  // --- /ip ---
  bot.command("ip", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand("homelab", "public_ip", {});
      await ctx.reply(response.text || "Unknown");
    } catch (error) {
      await ctx.reply("❌ Failed to get public IP.");
    }
  });

  // --- /temps ---
  bot.command("temps", async (ctx) => {
    try {
      const response = await bridge.sendServerCommand(
        "homelab",
        "temperatures",
        {}
      );
      await ctx.reply(formatResponse("Temperatures", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ lm-sensors not available.");
    }
  });

  // --- /speedtest ---
  bot.command("speedtest", async (ctx) => {
    await ctx.reply("⏳ Running speed test...");
    try {
      const response = await bridge.sendServerCommand(
        "homelab",
        "speedtest",
        {}
      );
      await ctx.reply(formatResponse("Speed Test", response), {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Speed test failed.");
    }
  });

  // --- /wake [machine] ---
  bot.command("wake", async (ctx) => {
    const text = ctx.message.text.replace("/wake", "").trim();
    if (!text) {
      await ctx.reply("Usage: /wake AA:BB:CC:DD:EE:FF");
      return;
    }
    try {
      const response = await bridge.sendServerCommand("homelab", "wake", {
        mac_address: text,
      });
      await ctx.reply(response.text || "WoL sent");
    } catch (error) {
      await ctx.reply("❌ Wake-on-LAN failed.");
    }
  });

  // --- /logs [service] ---
  bot.command("logs", async (ctx) => {
    const service = ctx.message.text.replace("/logs", "").trim();
    if (!service) {
      await ctx.reply("Usage: /logs nginx");
      return;
    }
    try {
      const response = await bridge.sendServerCommand("services", "logs", {
        name: service,
        lines: 20,
      });
      const output = response.text || "(no logs)";
      // Truncate for Telegram (4096 char limit)
      const truncated =
        output.length > 3900 ? output.slice(-3900) + "\n...(truncated)" : output;
      await ctx.reply(`\`\`\`\n${truncated}\n\`\`\``, {
        parse_mode: "Markdown",
      });
    } catch (error) {
      await ctx.reply("❌ Failed to get logs.");
    }
  });

  // --- Plain text: natural language to MK ---
  bot.on("text", async (ctx) => {
    const chatId = ctx.chat?.id?.toString() || "";
    const userMessage = ctx.message.text;

    try {
      const response = await bridge.sendMessage(userMessage, chatId, "telegram");
      const text = response.text || "(no response)";
      // Truncate for Telegram limit
      const truncated =
        text.length > 4000 ? text.slice(0, 4000) + "\n...(truncated)" : text;
      await ctx.reply(truncated, { parse_mode: "Markdown" }).catch(() => {
        // If markdown fails, send as plain text
        ctx.reply(truncated);
      });
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      await ctx.reply(`❌ Error: ${msg}`);
    }
  });

  return bot;
}

/**
 * Format a server command response for Telegram display.
 */
function formatResponse(
  title: string,
  response: { text?: string; metadata?: Record<string, unknown> }
): string {
  const text = response.text || "(no data)";
  // Truncate for Telegram
  const body = text.length > 3800 ? text.slice(0, 3800) + "\n..." : text;
  return `*${title}*\n\`\`\`\n${body}\n\`\`\``;
}

/**
 * Start proactive message polling.
 */
export function startProactivePolling(
  bot: Telegraf,
  bridge: MKBridge,
  config: GatewayConfig
): NodeJS.Timeout {
  return setInterval(async () => {
    try {
      const messages = await bridge.pollProactive("telegram");
      for (const msg of messages) {
        try {
          await bot.telegram.sendMessage(msg.target_id, msg.text, {
            parse_mode: "Markdown",
          });
        } catch (sendError) {
          console.error(
            `Failed to send proactive message to ${msg.target_id}:`,
            sendError
          );
        }
      }
    } catch {
      // Non-critical
    }
  }, config.pollInterval);
}
