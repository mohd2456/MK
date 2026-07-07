/**
 * MK OS System Types
 * ====================
 * System info, services, updates, and AI configuration.
 */

export type ServiceStatus = "running" | "stopped" | "failed" | "inactive";
export type UpdatePriority = "security" | "feature" | "bugfix";

export interface SystemInfo {
  hostname: string;
  os: string;
  kernel: string;
  uptime_seconds: number;
  cpu_model: string;
  cpu_cores: number;
  cpu_threads: number;
  ram_total_bytes: number;
  ram_used_bytes: number;
  boot_drive: string;
  boot_drive_model: string;
}

export interface SystemService {
  name: string;
  status: ServiceStatus;
  cpu_percent: number;
  ram_bytes: number;
  uptime: string;
  description: string;
}

export interface SystemUpdate {
  package: string;
  current_version: string;
  available_version: string;
  priority: UpdatePriority;
  description: string;
}

export interface AISettings {
  provider: "openai" | "anthropic" | "local" | "ollama";
  model: string;
  api_key_set: boolean;
  temperature: number;
  max_tokens: number;
  system_prompt: string;
  context_options: {
    include_metrics: boolean;
    include_alerts: boolean;
    include_page_context: boolean;
    include_command_history: boolean;
  };
}

export interface PowerInfo {
  last_boot: string;
  ups_name?: string;
  ups_charge_percent?: number;
  ups_runtime_minutes?: number;
}
