/**
 * MK OS Storage Types
 * ====================
 * ZFS pools, datasets, snapshots, disks, and shares.
 */

export type PoolHealth = "ONLINE" | "DEGRADED" | "FAULTED" | "OFFLINE";
export type PoolLayout = "RAIDZ1" | "RAIDZ2" | "RAIDZ3" | "Mirror" | "Stripe";
export type ShareType = "SMB" | "NFS";
export type SMARTStatus = "PASS" | "WARN" | "FAIL";

export interface Pool {
  name: string;
  layout: PoolLayout;
  size_bytes: number;
  used_bytes: number;
  usage_percent: number;
  health: PoolHealth;
  disk_count: number;
  scrub_last: string;
  scrub_errors: number;
}

export interface Dataset {
  name: string;
  pool: string;
  used_bytes: number;
  available_bytes: number;
  compression: string;
  mountpoint: string;
  record_size: string;
  quota: number | null;
}

export interface Snapshot {
  name: string;
  dataset: string;
  size_bytes: number;
  created: string;
  referenced_bytes: number;
}

export interface Disk {
  device: string;
  model: string;
  size_bytes: number;
  temperature: number;
  smart_status: SMARTStatus;
  pool: string | null;
  serial: string;
  hours_on: number;
}

export interface Share {
  name: string;
  type: ShareType;
  path: string;
  access: string;
  status: "active" | "inactive";
  description?: string;
}
