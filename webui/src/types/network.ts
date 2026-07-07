/**
 * MK OS Network Types
 * =====================
 * Interfaces, firewall, WireGuard, DNS, and reverse proxy.
 */

export type InterfaceType = "physical" | "bridge" | "wireguard" | "vlan" | "bond";
export type InterfaceStatus = "connected" | "disconnected" | "up" | "down";
export type FirewallAction = "ACCEPT" | "DROP" | "REJECT";
export type FirewallChain = "INPUT" | "OUTPUT" | "FORWARD";

export interface NetworkInterface {
  name: string;
  type: InterfaceType;
  ip_address: string;
  speed: string;
  status: InterfaceStatus;
  mac_address: string;
  rx_bytes: number;
  tx_bytes: number;
}

export interface FirewallRule {
  id: string;
  order: number;
  chain: FirewallChain;
  source: string;
  destination: string;
  port: string;
  protocol: "tcp" | "udp" | "any";
  action: FirewallAction;
  comment?: string;
}

export interface WireGuardPeer {
  id: string;
  name: string;
  public_key: string;
  endpoint: string;
  last_seen: string;
  transfer_rx: number;
  transfer_tx: number;
  allowed_ips: string;
}

export interface DNSConfig {
  primary: string;
  secondary: string;
  search_domain: string;
  local_overrides: Array<{ hostname: string; ip: string }>;
}

export interface ProxySite {
  id: string;
  domain: string;
  backend: string;
  ssl: "auto" | "manual" | "none";
  status: "active" | "inactive" | "error";
  certificate_expires?: string;
}
