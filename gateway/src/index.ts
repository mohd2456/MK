/**
 * MK Gateway - Multi-platform messaging hub.
 *
 * Connects MK to:
 *   - Telegram (primary, rich commands)
 *   - Discord (slash commands + DMs)
 *   - Matrix (bridges WhatsApp, Signal, iMessage via mautrix)
 *
 * Each platform is optional — enable by setting the token.
 */

import "dotenv/config";
import express from "express";
import { loadConfig } from "./config.js";
import { MKBridge } from "./bridge.js";
import { createTelegramBot, startProactivePolling } from "./telegram.js";
import { createDiscordBot } from "./discord.js";
import type { GatewayConfig } from "./types.js";

async function main(): Promise<void> {
  console.log("MK Gateway starting...");

  let config: GatewayConfig;
  try {
    config = loadConfig();
  } catch (error) {
    console.error("Config error:", error);
    process.exit(1);
  }

  const bridge = new MKBridge(config);
  const cleanups: (() => void)[] = [];

  // --- Telegram ---
  if (config.telegramBotToken) {
    const bot = createTelegramBot(config, bridge);
    const pollHandle = startProactivePolling(bot, bridge, config);
    bot.launch();
    console.log("✓ Telegram bot active");
    cleanups.push(() => {
      clearInterval(pollHandle);
      bot.stop("shutdown");
    });
  }

  // --- Discord ---
  if (config.discordBotToken) {
    const client = await createDiscordBot(config, bridge);
    if (client) {
      console.log("✓ Discord bot active");
      cleanups.push(() => client.destroy());
    }
  }

  // --- Matrix (placeholder for mautrix bridge) ---
  if (config.matrixHomeserver && config.matrixAccessToken) {
    console.log("✓ Matrix configured (bridge mode)");
    // Matrix integration uses mautrix bridges (open source)
    // WhatsApp: https://github.com/mautrix/whatsapp
    // Signal: https://github.com/mautrix/signal
    // These run as separate services and bridge into Matrix rooms
    // MK joins those rooms and responds like any other platform
  }

  // --- Health endpoint ---
  const app = express();

  app.get("/health", async (_req, res) => {
    try {
      const status = await bridge.getStatus();
      res.json({ gateway: "healthy", core: status.status });
    } catch {
      res.json({ gateway: "healthy", core: "unreachable" });
    }
  });

  app.listen(config.healthPort, () => {
    console.log(`Health endpoint: http://0.0.0.0:${config.healthPort}/health`);
  });

  console.log("MK Gateway online.");

  // --- Graceful shutdown ---
  const shutdown = (signal: string) => {
    console.log(`${signal} — shutting down...`);
    cleanups.forEach((fn) => fn());
    process.exit(0);
  };

  process.once("SIGINT", () => shutdown("SIGINT"));
  process.once("SIGTERM", () => shutdown("SIGTERM"));
}

main().catch((error) => {
  console.error("Fatal:", error);
  process.exit(1);
});
