/**
 * MK OS Apps Types
 * =================
 * Docker containers, compose stacks, and virtual machines.
 */

export type ContainerStatus = "running" | "stopped" | "restarting" | "error";
export type StackHealth = "healthy" | "degraded" | "down";
export type VMStatus = "running" | "stopped" | "paused" | "error";

export interface Container {
  id: string;
  name: string;
  image: string;
  status: ContainerStatus;
  cpu_percent: number;
  ram_bytes: number;
  uptime: string;
  ports: string[];
  created: string;
}

export interface Stack {
  name: string;
  services_total: number;
  services_running: number;
  health: StackHealth;
  compose_file: string;
  created: string;
}

export interface VM {
  id: string;
  name: string;
  os: string;
  vcpu: number;
  ram_bytes: number;
  status: VMStatus;
  disk_size_bytes: number;
  vnc_port?: number;
}
