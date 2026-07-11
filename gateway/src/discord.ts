/**
 * Discord bot — talk to MK from Discord.
 *
 * Commands (slash commands):
 *   /mk [message]    - Send anything to MK
 *   /status          - System health
 *   /containers      - Docker status
 *   /storage         - ZFS pools
 *   /backup          - Backup health
 *   /logs [service]  - Service logs
 *   /help            - All commands
 *
 * Also responds to DMs and @mentions in guild channels.
 * Uses discord.js (open source, MIT license).
 */

import {
  Client,
  Events,
  GatewayIntentBits,
  REST,
  Routes,
  SlashCommandBuilder,
} from "discord.js";
import type { Interaction, Message } from "discord.js";
import { MKBridge } from "./bridge.js";
import { isDiscordUserAllowed } from "./config.js";
import type { GatewayConfig } from "./types.js";

/** All available commands with descriptions (for /help). */
const COMMAND_DESCRIPTIONS: Array<{ name: string; description: string }> = [
  { name: "/mk [message]", description: "Send any message to MK" },
  { name: "/status", description: "System health overview" },
  { name: "/containers", description: "Docker container status" },
  { name: "/storage", description: "ZFS storage status" },
  { name: "/backup", description: "Backup job health" },
  { name: "/logs [service]", description: "Recent logs for a service" },
  { name: "/help", description: "Show this help message" },
  { name: "@mention", description: "Mention the bot in any channel to chat" },
];

/**
 * Create and start the Discord bot.
 */
export async function createDiscordBot(
  config: GatewayConfig,
  bridge: MKBridge
): Promise<Client | null> {
  if (!config.discordBotToken) {
    console.log("Discord: No token configured, skipping.");
    return null;
  }

  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.DirectMessages,
      GatewayIntentBits.MessageContent,
    ],
  });

  // Register slash commands
  const commands = [
    new SlashCommandBuilder()
      .setName("mk")
      .setDescription("Send a message to MK")
      .addStringOption((opt) =>
        opt.setName("message").setDescription("Your message").setRequired(true)
      ),
    new SlashCommandBuilder()
      .setName("status")
      .setDescription("System health overview"),
    new SlashCommandBuilder()
      .setName("containers")
      .setDescription("Docker container status"),
    new SlashCommandBuilder()
      .setName("storage")
      .setDescription("ZFS storage status"),
    new SlashCommandBuilder()
      .setName("backup")
      .setDescription("Backup job health"),
    new SlashCommandBuilder()
      .setName("logs")
      .setDescription("Service logs")
      .addStringOption((opt) =>
        opt.setName("service").setDescription("Service name").setRequired(true)
      ),
    new SlashCommandBuilder()
      .setName("help")
      .setDescription("List all available commands"),
  ];

  // Ready event
  client.once(Events.ClientReady, async (readyClient) => {
    console.log(`Discord: Logged in as ${readyClient.user.tag}`);

    // Register commands globally
    const rest = new REST().setToken(config.discordBotToken);
    try {
      await rest.put(Routes.applicationCommands(readyClient.user.id), {
        body: commands.map((c) => c.toJSON()),
      });
      console.log("Discord: Slash commands registered.");
    } catch (error) {
      console.error("Discord: Failed to register commands:", error);
    }
  });

  // Slash command handler
  client.on(Events.InteractionCreate, async (interaction: Interaction) => {
    if (!interaction.isChatInputCommand()) return;

    const userId = interaction.user.id;
    if (!isDiscordUserAllowed(userId, config)) {
      await interaction.reply({ content: "⛔ Not authorized.", ephemeral: true });
      return;
    }

    const cmd = interaction.commandName;

    try {
      if (cmd === "mk") {
        const message = interaction.options.getString("message", true);
        await interaction.deferReply();
        const response = await bridge.sendMessage(message, userId, "discord");
        await interaction.editReply(truncate(response.text || "(no response)"));
      } else if (cmd === "status") {
        await interaction.deferReply();
        const response = await bridge.sendServerCommand("system", "overview", {});
        await interaction.editReply(codeBlock(response.text || "No data"));
      } else if (cmd === "containers") {
        await interaction.deferReply();
        const response = await bridge.sendServerCommand("containers", "list", {});
        await interaction.editReply(codeBlock(response.text || "No containers"));
      } else if (cmd === "storage") {
        await interaction.deferReply();
        const response = await bridge.sendServerCommand("storage", "list_pools", {});
        await interaction.editReply(codeBlock(response.text || "No pools"));
      } else if (cmd === "backup") {
        await interaction.deferReply();
        const response = await bridge.sendServerCommand("backups", "health", {});
        await interaction.editReply(codeBlock(response.text || "No backup data"));
      } else if (cmd === "logs") {
        const service = interaction.options.getString("service", true);
        await interaction.deferReply();
        const response = await bridge.sendServerCommand("services", "logs", {
          name: service,
          lines: 30,
        });
        await interaction.editReply(codeBlock(response.text || "(no logs)"));
      } else if (cmd === "help") {
        const helpText = formatHelpMessage();
        await interaction.reply({ content: helpText, ephemeral: false });
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      if (interaction.deferred) {
        await interaction.editReply(`❌ Error: ${msg}`);
      } else {
        await interaction.reply({ content: `❌ Error: ${msg}`, ephemeral: true });
      }
    }
  });

  // DM handler — plain text to MK
  client.on(Events.MessageCreate, async (message: Message) => {
    if (message.author.bot) return;

    // Handle DMs
    if (message.channel.isDMBased()) {
      const userId = message.author.id;
      if (!isDiscordUserAllowed(userId, config)) return;

      try {
        const response = await bridge.sendMessage(
          message.content,
          userId,
          "discord"
        );
        await message.reply(truncate(response.text || "(no response)"));
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        await message.reply(`❌ Error: ${msg}`);
      }
      return;
    }

    // Handle @mentions in guild channels
    if (client.user && message.mentions.has(client.user)) {
      const userId = message.author.id;
      if (!isDiscordUserAllowed(userId, config)) return;

      // Strip the mention from the message content
      const content = message.content
        .replace(new RegExp(`<@!?${client.user.id}>`, "g"), "")
        .trim();

      if (!content) {
        await message.reply(
          "Hey! Send me a message after the mention, or use `/help` to see available commands."
        );
        return;
      }

      try {
        const response = await bridge.sendMessage(content, userId, "discord");
        await message.reply(truncate(response.text || "(no response)"));
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Unknown error";
        await message.reply(`❌ Error: ${msg}`);
      }
    }
  });

  // Graceful reconnection on disconnect
  client.on(Events.Error, (error) => {
    console.error("Discord: Client error:", error.message);
  });

  client.on("disconnect", () => {
    console.warn("Discord: Disconnected. Will attempt automatic reconnection.");
  });

  client.on("reconnecting", () => {
    console.log("Discord: Reconnecting...");
  });

  await client.login(config.discordBotToken);
  return client;
}

/**
 * Format the help message listing all commands.
 */
function formatHelpMessage(): string {
  const lines = ["**MK Bot Commands**\n"];
  for (const cmd of COMMAND_DESCRIPTIONS) {
    lines.push(`\`${cmd.name}\` - ${cmd.description}`);
  }
  lines.push("\nYou can also DM the bot directly for a private conversation.");
  return lines.join("\n");
}

function truncate(text: string, max: number = 1900): string {
  return text.length > max ? text.slice(0, max) + "\n...(truncated)" : text;
}

function codeBlock(text: string): string {
  const t = truncate(text, 1850);
  return `\`\`\`\n${t}\n\`\`\``;
}
