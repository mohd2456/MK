/**
 * Voice interface — local speech-to-text + text-to-speech.
 *
 * Accepts audio via HTTP POST, transcribes with Whisper.cpp (local,
 * no cloud), sends the text to MK core, converts the reply to speech
 * via Piper TTS (local), and returns the audio.
 *
 * This runs entirely on-device — no audio ever leaves the homelab.
 *
 * Requirements:
 *   - whisper-cpp server or CLI (`whisper-cli` / `whisper-server`)
 *   - piper TTS binary + a voice model
 *
 * Environment:
 *   MK_WHISPER_MODEL    - path to Whisper GGML model (default: /opt/mk/models/whisper-base.bin)
 *   MK_WHISPER_BIN      - whisper CLI binary (default: whisper-cli)
 *   MK_PIPER_BIN        - piper binary (default: piper)
 *   MK_PIPER_MODEL      - piper voice model path (default: /opt/mk/models/en_US-lessac-medium.onnx)
 *   MK_VOICE_PORT       - HTTP port for the voice endpoint (default: 8090)
 */

import { execFile } from "node:child_process";
import { writeFile, readFile, unlink, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import express from "express";
import type { Router } from "express";
import { MKBridge } from "./bridge.js";
import type { GatewayConfig } from "./types.js";

const execFileAsync = promisify(execFile);

// --- Config from environment ---

const WHISPER_MODEL =
  process.env.MK_WHISPER_MODEL || "/opt/mk/models/whisper-base.bin";
const WHISPER_BIN = process.env.MK_WHISPER_BIN || "whisper-cli";
const PIPER_BIN = process.env.MK_PIPER_BIN || "piper";
const PIPER_MODEL =
  process.env.MK_PIPER_MODEL || "/opt/mk/models/en_US-lessac-medium.onnx";

// --- STT: Whisper.cpp ---

/**
 * Transcribe an audio file using the local Whisper.cpp binary.
 *
 * @param audioPath - Path to WAV audio file (16kHz mono recommended).
 * @returns The transcribed text.
 */
export async function transcribe(audioPath: string): Promise<string> {
  // whisper-cli: whisper-cli -m model.bin -f input.wav --no-timestamps --output-txt
  const { stdout } = await execFileAsync(WHISPER_BIN, [
    "-m",
    WHISPER_MODEL,
    "-f",
    audioPath,
    "--no-timestamps",
    "--output-txt",
    "--print-progress",
    "false",
  ]);
  // whisper-cli prints transcription to stdout when --output-txt is used with -
  return stdout.trim();
}

// --- TTS: Piper ---

/**
 * Synthesize speech from text using the local Piper TTS binary.
 *
 * @param text - Text to speak.
 * @param outputPath - Path to write the output WAV file.
 */
export async function synthesize(
  text: string,
  outputPath: string
): Promise<void> {
  // piper reads from stdin, writes WAV to --output_file
  return new Promise<void>((resolve, reject) => {
    const { spawn } = require("node:child_process");
    const proc = spawn(PIPER_BIN, [
      "--model",
      PIPER_MODEL,
      "--output_file",
      outputPath,
    ]);
    let stderr = "";
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    proc.on("error", (err: Error) => reject(err));
    proc.on("close", (code: number) => {
      if (code !== 0) {
        reject(new Error(`Piper exited ${code}: ${stderr.slice(0, 200)}`));
      } else {
        resolve();
      }
    });
    proc.stdin.write(text);
    proc.stdin.end();
  });
}

// --- Voice HTTP endpoint ---

/**
 * Create an Express router with the voice endpoint.
 *
 * POST /voice
 *   Body: raw audio (WAV or webm, Content-Type: audio/*)
 *   Response: audio/wav with the spoken MK reply
 *
 * POST /voice/text
 *   Body: JSON { "text": "..." }
 *   Response: audio/wav with the spoken MK reply (TTS only, skip STT)
 */
export function createVoiceRouter(
  config: GatewayConfig,
  bridge: MKBridge
): Router {
  const router = express.Router();

  // Accept raw audio body (up to 10MB)
  router.use(express.raw({ type: "audio/*", limit: "10mb" }));
  router.use(express.json({ limit: "1mb" }));

  router.post("/voice", async (req, res) => {
    const audioBuffer = req.body as Buffer;
    if (!audioBuffer || audioBuffer.length === 0) {
      res.status(400).json({ error: "No audio data received" });
      return;
    }

    let tmpDir: string | null = null;
    try {
      tmpDir = await mkdtemp(join(tmpdir(), "mk-voice-"));
      const inputPath = join(tmpDir, "input.wav");
      const outputPath = join(tmpDir, "reply.wav");

      // Write incoming audio to a temp file for Whisper.
      await writeFile(inputPath, audioBuffer);

      // STT: transcribe audio → text
      const userText = await transcribe(inputPath);
      if (!userText.trim()) {
        res.status(422).json({ error: "Could not transcribe audio" });
        return;
      }

      // Send to MK core
      const mkResponse = await bridge.sendMessage(userText, "voice-user", "voice");
      const replyText = mkResponse.text || "I have no response.";

      // TTS: text → audio
      await synthesize(replyText, outputPath);
      const replyAudio = await readFile(outputPath);

      res.set("Content-Type", "audio/wav");
      res.set("X-MK-Transcription", encodeURIComponent(userText));
      res.set("X-MK-Reply-Text", encodeURIComponent(replyText.slice(0, 200)));
      res.send(replyAudio);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      console.error("[voice] Error:", msg);
      res.status(500).json({ error: msg });
    } finally {
      // Cleanup temp files (best-effort)
      if (tmpDir) {
        try {
          await unlink(join(tmpDir, "input.wav")).catch(() => {});
          await unlink(join(tmpDir, "reply.wav")).catch(() => {});
          const { rmdir } = await import("node:fs/promises");
          await rmdir(tmpDir).catch(() => {});
        } catch {
          /* ignore cleanup errors */
        }
      }
    }
  });

  // TTS-only endpoint (useful for reading notifications aloud)
  router.post("/voice/text", async (req, res) => {
    const text = (req.body as { text?: string })?.text;
    if (!text) {
      res.status(400).json({ error: "Missing 'text' field" });
      return;
    }

    let tmpDir: string | null = null;
    try {
      tmpDir = await mkdtemp(join(tmpdir(), "mk-tts-"));
      const outputPath = join(tmpDir, "speech.wav");
      await synthesize(text, outputPath);
      const audio = await readFile(outputPath);
      res.set("Content-Type", "audio/wav");
      res.send(audio);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unknown error";
      res.status(500).json({ error: msg });
    } finally {
      if (tmpDir) {
        try {
          await unlink(join(tmpDir, "speech.wav")).catch(() => {});
          const { rmdir } = await import("node:fs/promises");
          await rmdir(tmpDir).catch(() => {});
        } catch {
          /* ignore */
        }
      }
    }
  });

  // Health/capability check
  router.get("/voice/status", (_req, res) => {
    res.json({
      whisper_model: WHISPER_MODEL,
      whisper_bin: WHISPER_BIN,
      piper_model: PIPER_MODEL,
      piper_bin: PIPER_BIN,
      status: "configured",
    });
  });

  return router;
}
