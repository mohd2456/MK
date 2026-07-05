/**
 * MK Gateway - Main Entry Point
 *
 * Starts the Telegram bot, health endpoint, and connects
 * to MK core engine for message processing.
 */

import "dotenv/config";
import express from "express";
import { loadConfig } from "./config.js";
import { MKBridge } from "./bridge.js";
import { createTelegramBot, startProactivePolling } from "./telegram.js";
import type { GatewayConfig } from "./types.js";

/**
 * Start the MK Gateway.
 *
 * Initializes all components:
 * 1. Loads configuration from environment
 * 2. Creates the bridge to MK core
 * 3. Starts the Telegram bot
 * 4. Launches the health endpoint
 * 5. Begins proactive message polling
 */
async function main(): Promise<void> {
  console.log("MK Gateway starting...");

  // Load configuration
  let config: GatewayConfig;
  try {
    config = loadConfig();
  } catch (error) {
    console.error("Configuration error:", error);
    process.exit(1);
  }

  // Create bridge to MK core
  const bridge = new MKBridge(config);

  // Create and start Telegram bot
  const bot = createTelegramBot(config, bridge);

  // Health endpoint using Express
  const app = express();

  app.get("/health", async (_req, res) => {
    try {
      const status = await bridge.getStatus();
      res.json({
        gateway: "healthy",
        core: status.status,
        version: status.version,
      });
    } catch {
      res.json({
        gateway: "healthy",
        core: "unreachable",
      });
    }
  });

  app.listen(config.healthPort, () => {
    console.log(`Health endpoint listening on port ${config.healthPort}`);
  });

  // Start proactive message polling
  const pollHandle = startProactivePolling(bot, bridge, config);

  // Launch the bot
  bot.launch();
  console.log("MK Gateway online. Telegram bot active.");

  // Graceful shutdown
  const shutdown = (signal: string) => {
    console.log(`\n${signal} received. Shutting down gracefully...`);
    clearInterval(pollHandle);
    bot.stop(signal);
    process.exit(0);
  };

  process.once("SIGINT", () => shutdown("SIGINT"));
  process.once("SIGTERM", () => shutdown("SIGTERM"));
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
