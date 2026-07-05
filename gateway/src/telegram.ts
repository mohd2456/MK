/**
 * Telegram bot implementation using Telegraf.
 *
 * Handles incoming messages from Telegram users, forwards them
 * to MK core via the bridge, and sends responses back.
 * Also supports proactive messaging from MK to users.
 */

import { Telegraf } from "telegraf";
import type { Context } from "telegraf";
import { MKBridge } from "./bridge.js";
import { isChatAllowed } from "./config.js";
import type { GatewayConfig } from "./types.js";

/**
 * Create and configure the Telegram bot.
 *
 * Sets up message handlers, command handlers, and the
 * proactive message polling loop.
 *
 * @param config - Gateway configuration
 * @param bridge - MK core bridge instance
 * @returns Configured Telegraf bot instance
 */
export function createTelegramBot(
  config: GatewayConfig,
  bridge: MKBridge
): Telegraf {
  const bot = new Telegraf(config.telegramBotToken);

  // /start command handler
  bot.start(async (ctx: Context) => {
    const chatId = ctx.chat?.id?.toString() || "";

    if (!isChatAllowed(chatId, config)) {
      await ctx.reply("Access denied. Your chat ID is not authorized.");
      return;
    }

    await ctx.reply(
      "MK online. I'm your personal AI operating system.\n\n" +
        "Send me any message and I'll process it. I can manage your homelab, " +
        "handle media, run commands, and more.\n\n" +
        "I'll also reach out proactively when something needs your attention."
    );
  });

  // /status command handler
  bot.command("status", async (ctx: Context) => {
    const chatId = ctx.chat?.id?.toString() || "";

    if (!isChatAllowed(chatId, config)) {
      await ctx.reply("Access denied.");
      return;
    }

    try {
      const status = await bridge.getStatus();
      await ctx.reply(
        `MK Status: ${status.status}\n` +
          `Version: ${status.version}\n` +
          `Uptime: ${Math.floor(status.uptime_seconds / 60)} minutes`
      );
    } catch (error) {
      await ctx.reply("Unable to reach MK core. The system may be restarting.");
    }
  });

  // Text message handler - main interaction point
  bot.on("text", async (ctx) => {
    const chatId = ctx.chat?.id?.toString() || "";

    if (!isChatAllowed(chatId, config)) {
      await ctx.reply("Access denied. Your chat ID is not authorized.");
      return;
    }

    const userMessage = ctx.message.text;

    try {
      const response = await bridge.sendMessage(userMessage, chatId, "telegram");
      await ctx.reply(response.text, { parse_mode: "Markdown" });
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      await ctx.reply(
        `I'm having trouble processing that right now. Error: ${errorMessage}`
      );
    }
  });

  return bot;
}

/**
 * Start the proactive message polling loop.
 *
 * Periodically checks MK core for messages that MK wants to
 * send to the user proactively (alerts, updates, etc.).
 *
 * @param bot - Telegraf bot instance
 * @param bridge - MK core bridge
 * @param config - Gateway configuration
 * @returns Interval handle for cleanup
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
    } catch (error) {
      // Polling failures are non-critical, just log
      console.debug("Proactive polling error:", error);
    }
  }, config.pollInterval);
}
