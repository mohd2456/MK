# MK OS Web UI - Complete Blueprint

## Vision

A homelab server management dashboard that makes TrueNAS look dated. Dark-first,
minimal, blazing fast, with an AI chat panel always one click away. Every page
gives you the info you need in 2 seconds - no clicking through 5 menus to find
a setting. MK OS is what happens when you build a server dashboard for people
who actually run servers.

**URL:** `https://mk.yourdomain.com` (or `http://mk.local:8080`)

**Philosophy:**
- Show, do not hide. Surface the important stuff.
- AI-first. Chat is not a gimmick - it is the primary control interface.
- One-click actions. No confirmation dialogs for reversible operations.
- Dark by default. Light mode exists for the brave.
- Speed. Every page loads in under 200ms.

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | **React 18 + TypeScript** | Fast, huge ecosystem, easy to maintain |
| Styling | **Tailwind CSS** | Utility-first, dark mode built in, no CSS bloat |
| Components | **shadcn/ui** | Beautiful, accessible, copy-paste components |
| Icons | **Lucide** | Clean, consistent, open source |
| Charts | **Recharts** | Simple, React-native charts for monitoring |
| State | **Zustand** | Tiny, fast, no boilerplate |
| Routing | **React Router v6** | Standard, simple |
| HTTP | **fetch + SWR** | Auto-refresh, caching, stale-while-revalidate |
| WebSocket | **Native WebSocket** | Real-time chat + live updates |
| Build | **Vite** | Instant HMR, fast builds |
| Backend API | **Python FastAPI** | Already have the server layer, just expose it |
| Auth | **Session token + PIN** | Simple, no OAuth complexity for homelab |

---

## Color System

### Dark Theme (Primary - Default)

```
BACKGROUND LAYERS (darkest to lightest):
  bg-base:        #0a0a0f    Near-black with slight blue tint (page background)
  bg-surface:     #12121a    Card/panel backgrounds
  bg-elevated:    #1a1a2e    Hover states, elevated cards
  bg-overlay:     #1e1e32    Modals, dropdowns, tooltips

BORDERS:
  border-subtle:  #2a2a3e    Card borders, dividers
  border-strong:  #3a3a5e    Focused inputs, active elements

TEXT:
  text-primary:   #f0f0f5    Headings, important content
  text-secondary: #9090a8    Body text, descriptions
  text-muted:     #5a5a72    Placeholders, disabled, timestamps

ACCENT (MK Brand):
  accent:         #00d4ff    Primary actions, links, highlights
  accent-hover:   #33ddff    Hover state for accent
  accent-muted:   #00d4ff20  Accent backgrounds (20% opacity)

STATUS COLORS:
  success:        #00e676    Healthy, online, completed
  warning:        #ffab00    Degraded, attention needed
  error:          #ff5252    Failed, offline, critical
  info:           #448aff    Informational badges

CHAT BUBBLES:
  chat-user:      #1a2a3a    User message background
  chat-mk:        #0a1a2a    MK response background
  chat-border:    #2a3a4a    Bubble border (subtle)
```

### Light Theme (Optional)

```
BACKGROUND LAYERS:
  bg-base:        #f8f9fc    Page background
  bg-surface:     #ffffff    Card backgrounds
  bg-elevated:    #f0f1f5    Hover states
  bg-overlay:     #ffffff    Modals

BORDERS:
  border-subtle:  #e2e4ea    Dividers
  border-strong:  #c8cad2    Focused inputs

TEXT:
  text-primary:   #1a1a2e    Headings
  text-secondary: #4a4a62    Body text
  text-muted:     #8a8aa2    Placeholders

ACCENT:
  accent:         #0099cc    Slightly darker for contrast on white
```

### Tailwind Config

```typescript
// tailwind.config.ts
export default {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        mk: {
          base: "#0a0a0f",
          surface: "#12121a",
          elevated: "#1a1a2e",
          overlay: "#1e1e32",
          border: "#2a2a3e",
          "border-strong": "#3a3a5e",
          accent: "#00d4ff",
          "accent-hover": "#33ddff",
          success: "#00e676",
          warning: "#ffab00",
          error: "#ff5252",
          info: "#448aff",
        },
      },
    },
  },
}
```

---

## Layout Architecture

```
+------------------------------------------------------------------+
|  TOP BAR (h-14, bg-surface, border-b border-subtle)              |
|  [MK Logo]  Dashboard  Storage  Apps  Network  ...  [?] [Chat]  |
+------------------------------------------------------------------+
|                                           |                      |
|                                           |   CHAT PANEL         |
|          MAIN CONTENT AREA                |   (w-96, collapsible)|
|          (flex-1, p-6)                    |                      |
|                                           |   Conversation...    |
|          Page-specific content            |                      |
|          renders here                     |   [Type message...]  |
|                                           |                      |
+-------------------------------------------+----------------------+
```

### Top Bar Navigation

- Fixed at top, 56px height
- Logo (MK icon) on the left - click returns to dashboard
- Nav links: Dashboard, Storage, Apps, Network, Protection, Media, System
- Right side: Help button, Chat toggle button (shows unread indicator)
- Active page gets accent underline + accent text color
- Responsive: collapses to hamburger menu on mobile

### Chat Panel

- Right sidebar, 384px wide (w-96)
- Collapsible via toggle button or keyboard shortcut (Ctrl+/)
- Persists across page navigation (state preserved)
- Has its own scroll, independent of main content
- Context-aware: knows what page you are on, suggests relevant actions

### Main Content

- Fills remaining space (flex-1)
- 24px padding on all sides
- Max-width 1400px, centered on ultra-wide screens
- Scrolls independently of nav and chat

---

## Pages

### Dashboard (/)

The home page. At-a-glance system health. No scrolling needed for the
critical stuff.

```
+------------------------------------------------------------------+
|  DASHBOARD                                          [Refresh] [+] |
+------------------------------------------------------------------+
|                                                                    |
|  +------------+  +------------+  +------------+  +------------+   |
|  |   CPU      |  |   RAM      |  |  NETWORK   |  |   DISK     |  |
|  |            |  |            |  |            |  |            |   |
|  |   [====]   |  |   [===]    |  |  ^ 120MB/s |  |   [=====]  |  |
|  |   47%      |  |   62%      |  |  v  45MB/s |  |   78%      |  |
|  |  12 cores  |  |  32/64 GB  |  |  eth0      |  |   18.2 TB  |  |
|  +------------+  +------------+  +------------+  +------------+   |
|                                                                    |
|  +---------------------------+  +-------------------------------+ |
|  |  HEALTH SUMMARY           |  |  QUICK ACTIONS                | |
|  |                           |  |                               | |
|  |  * Storage: Healthy       |  |  [Start Backup]              | |
|  |  * Network: 2 interfaces  |  |  [Update System]            | |
|  |  * Apps: 12/12 running    |  |  [Rip Disc]                 | |
|  |  * Backups: Last 2h ago   |  |  [Restart Service...]       | |
|  |  * Temp: 42C (normal)     |  |                               | |
|  +---------------------------+  +-------------------------------+ |
|                                                                    |
|  +---------------------------+  +-------------------------------+ |
|  |  ALERTS (3)               |  |  ACTIVITY LOG                 | |
|  |                           |  |                               | |
|  |  ! Disk sda temp 55C     |  |  14:32  Backup job completed  | |
|  |  ! Pool 89% capacity     |  |  14:15  Container restarted   | |
|  |  i Update available       |  |  13:58  Snapshot created      | |
|  |                           |  |  13:45  User login (admin)    | |
|  +---------------------------+  +-------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `GaugeCard` - Circular or bar gauge with label, value, subtitle
- `HealthSummary` - List with status dots (green/amber/red)
- `QuickActions` - Button grid for common operations
- `AlertsList` - Prioritized alerts with severity icons
- `ActivityLog` - Time-stamped event feed (auto-scrolling)

**Data refresh:** Every 5 seconds via SWR with WebSocket push for alerts.

---

### Storage (/storage)

Pool management, datasets, snapshots, disk health, and shares - all on one page
with tabbed sections.

```
+------------------------------------------------------------------+
|  STORAGE                                        [Create Pool] [+] |
+------------------------------------------------------------------+
|  [Pools]  [Datasets]  [Snapshots]  [Disks]  [Shares]            |
+------------------------------------------------------------------+
|                                                                    |
|  POOLS                                                            |
|  +--------------------------------------------------------------+ |
|  | Name      | Layout   | Size   | Used   | Health  | Actions   | |
|  |-----------|----------|--------|--------|---------|-----------|  |
|  | tank      | RAIDZ2   | 48 TB  | 36 TB  | ONLINE  | [...]     | |
|  |           |          |        | [======75%======]  |         | |
|  | fast      | Mirror   | 2 TB   | 800 GB | ONLINE  | [...]     | |
|  |           |          |        | [==40%==         ] |         | |
|  | backup    | RAIDZ1   | 24 TB  | 20 TB  | DEGRADED| [...]     | |
|  |           |          |        | [=======83%=====]  |         | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  DATASETS (when Datasets tab active)                              |
|  +--------------------------------------------------------------+ |
|  | Dataset          | Used   | Avail  | Compress | Mountpoint   | |
|  |------------------|--------|--------|----------|--------------|  |
|  | tank/media       | 28 TB  | 12 TB  | lz4      | /mnt/media   | |
|  | tank/apps        | 4 TB   | 12 TB  | zstd     | /mnt/apps    | |
|  | tank/backups     | 3.5 TB | 12 TB  | off      | /mnt/backups | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  SNAPSHOTS (when Snapshots tab active)                            |
|  +--------------------------------------------------------------+ |
|  | Name                        | Dataset    | Size  | Created    | |
|  |-----------------------------|------------|-------|------------|  |
|  | tank/media@auto-2024-01-15  | tank/media | 2.1G  | 2024-01-15 | |
|  | tank/media@auto-2024-01-14  | tank/media | 1.8G  | 2024-01-14 | |
|  | tank/apps@pre-update        | tank/apps  | 500M  | 2024-01-15 | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  DISKS (when Disks tab active)                                    |
|  +--------------------------------------------------------------+ |
|  | Device | Model          | Size  | Temp | SMART  | Pool       | |
|  |--------|----------------|-------|------|--------|------------|  |
|  | sda    | WD Red 12TB    | 12 TB | 38C  | PASS   | tank       | |
|  | sdb    | WD Red 12TB    | 12 TB | 40C  | PASS   | tank       | |
|  | sdc    | WD Red 12TB    | 12 TB | 55C  | WARN   | tank       | |
|  | nvme0  | Samsung 980Pro | 1 TB  | 42C  | PASS   | fast       | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  SHARES (when Shares tab active)                                  |
|  +--------------------------------------------------------------+ |
|  | Name      | Type | Path            | Access       | Status   | |
|  |-----------|------|-----------------|--------------|----------|  |
|  | media     | SMB  | /mnt/media      | read-only    | Active   | |
|  | downloads | NFS  | /mnt/downloads  | 192.168.1.*  | Active   | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `PoolCard` - Expandable row with usage bar, health badge, action menu
- `DatasetTable` - Sortable table with inline edit for properties
- `SnapshotList` - Filterable list with rollback/delete actions
- `DiskGrid` - Card or table view with SMART summary + temperature
- `ShareManager` - CRUD for SMB/NFS shares

---

### Apps (/apps)

Containers, stacks (docker-compose), and VMs in one unified view.

```
+------------------------------------------------------------------+
|  APPS                                   [Deploy Container] [+]    |
+------------------------------------------------------------------+
|  [Containers]  [Stacks]  [VMs]                                   |
+------------------------------------------------------------------+
|                                                                    |
|  CONTAINERS                                                       |
|  +--------------------------------------------------------------+ |
|  | Name          | Image          | Status  | CPU  | RAM  | Act | |
|  |---------------|----------------|---------|------|------|-----|  |
|  | plex          | plexinc/pms    | Running | 12%  | 2.1G | [.] | |
|  | sonarr        | linuxserver/.. | Running |  2%  | 512M | [.] | |
|  | radarr        | linuxserver/.. | Running |  1%  | 480M | [.] | |
|  | nginx-proxy   | jwilder/nginx  | Running |  0%  | 64M  | [.] | |
|  | db-postgres   | postgres:16    | Stopped |  -   |  -   | [.] | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  STACKS (when Stacks tab active)                                  |
|  +--------------------------------------------------------------+ |
|  | Stack Name    | Services | Status    | Actions                | |
|  |---------------|----------|-----------|------------------------|  |
|  | media-stack   | 5/5 up   | Healthy   | [Restart] [Edit] [..] | |
|  | monitoring    | 3/3 up   | Healthy   | [Restart] [Edit] [..] | |
|  | dev-tools     | 2/4 up   | Degraded  | [Restart] [Edit] [..] | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  VMs (when VMs tab active)                                        |
|  +--------------------------------------------------------------+ |
|  | Name       | OS          | vCPU | RAM  | Status  | Actions   | |
|  |------------|-------------|------|------|---------|-----------|  |
|  | win11-dev  | Windows 11  | 4    | 8 GB | Running | [...]     | |
|  | ubuntu-lab | Ubuntu 24   | 2    | 4 GB | Stopped | [...]     | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `ContainerTable` - Live-updating table with status badges, sparkline CPU/RAM
- `StackCard` - Grouped view of related containers with combined health
- `VMTable` - VM list with console access button (noVNC integration)
- `DeployDialog` - Modal for deploying new container/stack/VM
- Status badges: Running (green), Stopped (muted), Degraded (amber), Error (red)

---

### Network (/network)

Interfaces, firewall, VPN, DNS, and reverse proxy management.

```
+------------------------------------------------------------------+
|  NETWORK                                              [Scan] [+]  |
+------------------------------------------------------------------+
|  [Interfaces]  [Firewall]  [WireGuard]  [DNS]  [Reverse Proxy]  |
+------------------------------------------------------------------+
|                                                                    |
|  INTERFACES                                                       |
|  +--------------------------------------------------------------+ |
|  | Name   | Type     | IP Address      | Speed   | Status      | |
|  |--------|----------|-----------------|---------|-------------|  |
|  | eth0   | Physical | 192.168.1.10/24 | 10 Gbps | Connected   | |
|  | eth1   | Physical | 10.0.0.1/24     | 1 Gbps  | Connected   | |
|  | br0    | Bridge   | 172.17.0.1/16   | -       | Up          | |
|  | wg0    | WireGrd  | 10.8.0.1/24     | -       | Active      | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  FIREWALL RULES (when Firewall tab active)                        |
|  +--------------------------------------------------------------+ |
|  | #  | Chain   | Source       | Dest    | Port  | Action       | |
|  |----|---------|-------------|---------|-------|--------------|  |
|  | 1  | INPUT   | 192.168.1.* | *       | 22    | ACCEPT       | |
|  | 2  | INPUT   | *           | *       | 80,443| ACCEPT       | |
|  | 3  | INPUT   | *           | *       | *     | DROP         | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  WIREGUARD PEERS (when WireGuard tab active)                      |
|  +--------------------------------------------------------------+ |
|  | Peer Name    | Public Key     | Endpoint       | Last Seen   | |
|  |--------------|----------------|----------------|-------------|  |
|  | phone        | aB3c...xYz    | dynamic        | 2 min ago   | |
|  | laptop       | dE4f...wVu    | 73.42.18.5     | 1 hr ago    | |
|  | remote-site  | gH5i...tSr    | 198.51.100.1   | 30 sec ago  | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  DNS (when DNS tab active)                                        |
|  +--------------------------------------------------------------+ |
|  | Primary:   1.1.1.1                                           | |
|  | Secondary: 8.8.8.8                                           | |
|  | Search:    home.lab                                          | |
|  | Local overrides:                                             | |
|  |   plex.home.lab    -> 192.168.1.10                          | |
|  |   nas.home.lab     -> 192.168.1.10                          | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  REVERSE PROXY (when Reverse Proxy tab active)                    |
|  +--------------------------------------------------------------+ |
|  | Domain              | Backend          | SSL    | Status     | |
|  |---------------------|------------------|--------|------------|  |
|  | plex.example.com    | localhost:32400  | Auto   | Active     | |
|  | sonarr.example.com  | localhost:8989   | Auto   | Active     | |
|  | grafana.example.com | localhost:3000   | Auto   | Active     | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `InterfaceCard` - Network interface with traffic sparkline
- `FirewallTable` - Drag-reorder rules, inline edit
- `WireGuardPeers` - Peer list with QR code generation for mobile
- `DNSConfig` - Simple form for DNS settings + local override list
- `ProxySites` - Domain-to-backend mapping with SSL status

---
### Data Protection (/protection)

Backup jobs, scrub schedules, replication, and retention policies.

```
+------------------------------------------------------------------+
|  DATA PROTECTION                            [Create Job] [+]      |
+------------------------------------------------------------------+
|  [Backup Jobs]  [Scrub Schedule]  [Replication]  [Retention]     |
+------------------------------------------------------------------+
|                                                                    |
|  BACKUP JOBS                                                      |
|  +--------------------------------------------------------------+ |
|  | Job Name       | Source       | Dest         | Schedule | St | |
|  |----------------|-------------|--------------|----------|-----|  |
|  | daily-media    | tank/media  | backup/media | Daily 2AM| OK | |
|  | weekly-full    | tank        | offsite-s3   | Sun 3AM  | OK | |
|  | apps-config    | tank/apps   | backup/apps  | 6h       | OK | |
|  | db-dump        | postgres    | tank/backups | 1h       | !! | |
|  +--------------------------------------------------------------+ |
|  | Last run: 2024-01-15 02:00  |  Next run: 2024-01-16 02:00   | |
|  | Duration: 45 min            |  Size: 2.3 TB transferred     | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  SCRUB SCHEDULE (when Scrub tab active)                           |
|  +--------------------------------------------------------------+ |
|  | Pool   | Schedule     | Last Run     | Duration | Errors     | |
|  |--------|--------------|--------------|----------|------------|  |
|  | tank   | Sun 1AM      | 2024-01-14   | 4h 12m   | 0          | |
|  | fast   | Wed/Sun 3AM  | 2024-01-15   | 12m      | 0          | |
|  | backup | 1st Sun 2AM  | 2024-01-07   | 6h 30m   | 0          | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  REPLICATION (when Replication tab active)                        |
|  +--------------------------------------------------------------+ |
|  | Task           | Source     | Target         | Status | Lag  | |
|  |----------------|------------|----------------|--------|------|  |
|  | offsite-sync   | tank       | remote:backup  | Active | 2h   | |
|  | local-mirror   | fast       | tank/mirror    | Active | 10m  | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  RETENTION (when Retention tab active)                            |
|  +--------------------------------------------------------------+ |
|  | Policy Name    | Keep Daily | Keep Weekly | Keep Monthly     | |
|  |----------------|------------|-------------|------------------|  |
|  | standard       | 7          | 4           | 12               | |
|  | critical       | 30         | 12          | 24               | |
|  | minimal        | 3          | 2           | 3                | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `BackupJobTable` - Job list with status, last/next run, expandable details
- `ScrubSchedule` - Pool scrub configuration with history
- `ReplicationTask` - Source/target pairs with lag indicator
- `RetentionPolicy` - Policy editor with preview of what gets pruned

---

### Media (/media)

Disc ripper control, library management, and auto-rip configuration.

```
+------------------------------------------------------------------+
|  MEDIA                                        [Scan Drives] [+]   |
+------------------------------------------------------------------+
|  [Disc Ripper]  [Library]  [Recent Rips]  [Settings]             |
+------------------------------------------------------------------+
|                                                                    |
|  DISC RIPPER                                                      |
|  +--------------------------------------------------------------+ |
|  |                                                              | |
|  |  Drive: /dev/sr0 (Pioneer BDR-XD07)                         | |
|  |  Status: DISC DETECTED                                      | |
|  |                                                              | |
|  |  +------------------------------------------------------+   | |
|  |  |  Title: The Matrix (1999)                             |   | |
|  |  |  Type: Blu-ray                                        |   | |
|  |  |  Titles: 42 found                                     |   | |
|  |  |  Main feature: Title 1 (2h 16m, 28.4 GB)             |   | |
|  |  |                                                       |   | |
|  |  |  Output: /mnt/media/movies/The Matrix (1999)/         |   | |
|  |  |  Format: MKV (passthrough)                            |   | |
|  |  |  Audio: All tracks                                    |   | |
|  |  |  Subtitles: All tracks                                |   | |
|  |  +------------------------------------------------------+   | |
|  |                                                              | |
|  |  [=================45%=================                  ]   | |
|  |  Ripping title 1/1... ETA 25 min (112 MB/s)                 | |
|  |                                                              | |
|  |        [ RIP DISC ]    [ EJECT ]    [ CANCEL ]               | |
|  |                                                              | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  RECENT RIPS (when Recent tab active)                             |
|  +--------------------------------------------------------------+ |
|  | Title                  | Date       | Size  | Format | Time  | |
|  |------------------------|------------|-------|--------|-------|  |
|  | The Matrix (1999)      | 2024-01-15 | 28 GB | MKV    | 52m   | |
|  | Blade Runner 2049      | 2024-01-14 | 45 GB | MKV    | 1h 8m | |
|  | Dune Part Two          | 2024-01-13 | 52 GB | MKV    | 1h 22m| |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  LIBRARY STATS (when Library tab active)                          |
|  +--------------------------------------------------------------+ |
|  | Movies: 847  |  TV Shows: 124  |  Total: 18.4 TB            | |
|  | Blu-rays: 412  |  DVDs: 435  |  4K UHD: 89                  | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  SETTINGS (when Settings tab active)                              |
|  +--------------------------------------------------------------+ |
|  | Auto-rip:       [ON]  Automatically rip when disc inserted  | |
|  | Output path:    /mnt/media/rips/                             | |
|  | Default format: MKV (passthrough)                            | |
|  | Min length:     30 min (skip bonus features)                 | |
|  | Notifications:  [ON]  Alert when rip completes               | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `DriveStatus` - Real-time drive state with disc info
- `RipProgress` - Progress bar with ETA, speed, current operation
- `RipButton` - Big primary action button (accent color)
- `RecentRips` - Table of completed rips with details
- `LibraryStats` - Summary cards for media collection
- `AutoRipToggle` - Toggle switch with explanation text

---

### System (/system)

System info, services, updates, power controls, and AI configuration.

```
+------------------------------------------------------------------+
|  SYSTEM                                               [Refresh]   |
+------------------------------------------------------------------+
|  [Overview]  [Services]  [Updates]  [Power]  [AI Settings]       |
+------------------------------------------------------------------+
|                                                                    |
|  SYSTEM OVERVIEW                                                  |
|  +--------------------------------------------------------------+ |
|  | Hostname:    mk-server                                       | |
|  | OS:          MK OS 1.0 (Debian 12 base)                      | |
|  | Kernel:      6.6.10-amd64                                    | |
|  | Uptime:      47 days 3 hours                                 | |
|  | CPU:         AMD Ryzen 9 7950X (16C/32T)                     | |
|  | RAM:         64 GB DDR5-5600 (32 GB used)                    | |
|  | Boot drive:  Samsung 980 Pro 500GB (NVME)                    | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  SERVICES (when Services tab active)                              |
|  +--------------------------------------------------------------+ |
|  | Service        | Status   | CPU  | RAM   | Uptime  | Actions | |
|  |----------------|----------|------|-------|---------|---------|  |
|  | docker         | Running  | 2%   | 4.2G  | 47d     | [...]   | |
|  | samba          | Running  | 0%   | 128M  | 47d     | [...]   | |
|  | nfs-server     | Running  | 0%   | 64M   | 47d     | [...]   | |
|  | wireguard      | Running  | 0%   | 12M   | 47d     | [...]   | |
|  | mk-api         | Running  | 1%   | 256M  | 2d      | [...]   | |
|  | nginx          | Running  | 0%   | 48M   | 47d     | [...]   | |
|  | cron           | Running  | 0%   | 8M    | 47d     | [...]   | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  UPDATES (when Updates tab active)                                |
|  +--------------------------------------------------------------+ |
|  | Available updates: 12 packages                               | |
|  |                                                              | |
|  | Package          | Current  | Available | Priority           | |
|  |------------------|----------|-----------|---------------------|  |
|  | linux-image      | 6.6.8    | 6.6.10    | Security           | |
|  | docker-ce        | 24.0.7   | 25.0.1    | Feature            | |
|  | mk-server        | 1.0.2    | 1.0.3     | Bugfix             | |
|  |                                                              | |
|  |        [ UPDATE ALL ]    [ UPDATE SELECTED ]                 | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  POWER (when Power tab active)                                    |
|  +--------------------------------------------------------------+ |
|  |                                                              | |
|  |   [ REBOOT ]      [ SHUTDOWN ]      [ SCHEDULE ]            | |
|  |                                                              | |
|  |   Last boot: 2024-01-01 08:00                               | |
|  |   UPS: APC 1500VA - 98% (6h runtime)                        | |
|  |                                                              | |
|  +--------------------------------------------------------------+ |
|                                                                    |
|  AI SETTINGS (when AI Settings tab active)                        |
|  +--------------------------------------------------------------+ |
|  | Provider:     [OpenAI v] [Anthropic v] [Local v]             | |
|  | Model:        gpt-4o / claude-sonnet / llama3                | |
|  | API Key:      sk-...****                    [Change]         | |
|  | Temperature:  0.7  [=======|===]                             | |
|  | Max tokens:   4096                                           | |
|  | System prompt: [Edit custom system prompt...]                | |
|  |                                                              | |
|  | Context:      [x] Include system metrics                     | |
|  |               [x] Include recent alerts                      | |
|  |               [x] Include page context                       | |
|  |               [ ] Include full command history               | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

**Components:**
- `SystemInfo` - Key-value display of system details
- `ServiceTable` - Live service list with start/stop/restart actions
- `UpdateList` - Available updates with priority badges
- `PowerControls` - Reboot/Shutdown buttons with confirmation
- `AISettings` - Provider/model/key configuration form

---

### Chat Panel (Right Sidebar)

Always-available AI assistant that understands your server.

```
+-------------------------------+
|  MK CHAT            [_] [X]  |
+-------------------------------+
|                               |
|  +-------------------------+  |
|  | MK                      |  |
|  | Hi! I'm monitoring your |  |
|  | server. Everything looks|  |
|  | healthy. What can I     |  |
|  | help with?              |  |
|  +-------------------------+  |
|                               |
|  +-------------------------+  |
|  |              You        |  |
|  | How's disk sda doing?   |  |
|  | It was running hot      |  |
|  | yesterday.              |  |
|  +-------------------------+  |
|                               |
|  +-------------------------+  |
|  | MK                      |  |
|  | sda (WD Red 12TB) is at |  |
|  | 38C now - back to       |  |
|  | normal. Yesterday it    |  |
|  | peaked at 55C during    |  |
|  | the scrub. SMART status |  |
|  | is still PASS. Want me  |  |
|  | to set up a temp alert? |  |
|  |                         |  |
|  | [Set alert at 50C]      |  |
|  | [Show SMART details]    |  |
|  | [View disk history]     |  |
|  +-------------------------+  |
|                               |
|  MK is typing...             |
|                               |
+-------------------------------+
|  [Type a message...]   [->]  |
+-------------------------------+
|  Context: Dashboard           |
|  Suggestions:                 |
|  "Show me pool health"        |
|  "Start a backup now"         |
|  "Any alerts I should know?"  |
+-------------------------------+
```

**Features:**
- Collapsible right panel (384px wide)
- Persists conversation across page navigation
- Context-aware suggestions change based on current page
- Typing indicator with animated dots
- Action buttons inline with responses (one-click execution)
- Markdown rendering in responses (code blocks, lists, bold)
- Scroll-to-bottom on new messages
- Keyboard shortcut: Ctrl+/ to toggle

**Chat bubble styling:**
- User messages: right-aligned, bg `#1a2a3a`, rounded-lg
- MK messages: left-aligned, bg `#0a1a2a`, rounded-lg
- Action buttons: accent border, hover fill
- Timestamps: text-muted, small, below bubble

---

## API Endpoints (FastAPI Backend)

All endpoints are prefixed with `/api/v1`. Authentication via session token
(obtained from PIN login).

### Auth

```
POST   /api/v1/auth/login          { pin: "1234" } -> { token, expires }
POST   /api/v1/auth/logout         Invalidate session
GET    /api/v1/auth/status         Check if session is valid
```

### Dashboard

```
GET    /api/v1/dashboard/summary    System health overview (CPU, RAM, disk, network)
GET    /api/v1/dashboard/alerts     Active alerts list
GET    /api/v1/dashboard/activity   Recent activity log (paginated)
POST   /api/v1/dashboard/dismiss    Dismiss an alert by ID
```

### Storage

```
GET    /api/v1/storage/pools                List all ZFS pools
POST   /api/v1/storage/pools                Create a new pool
GET    /api/v1/storage/pools/{name}         Pool details
DELETE /api/v1/storage/pools/{name}         Destroy pool
GET    /api/v1/storage/datasets             List datasets
POST   /api/v1/storage/datasets             Create dataset
PUT    /api/v1/storage/datasets/{name}      Update dataset properties
DELETE /api/v1/storage/datasets/{name}      Destroy dataset
GET    /api/v1/storage/snapshots            List snapshots (filterable)
POST   /api/v1/storage/snapshots            Create snapshot
POST   /api/v1/storage/snapshots/rollback   Rollback to snapshot
DELETE /api/v1/storage/snapshots/{name}     Delete snapshot
GET    /api/v1/storage/disks                List physical disks
GET    /api/v1/storage/disks/{dev}/smart    SMART data for disk
GET    /api/v1/storage/shares               List shares
POST   /api/v1/storage/shares               Create share (SMB/NFS)
PUT    /api/v1/storage/shares/{name}        Update share
DELETE /api/v1/storage/shares/{name}        Delete share
```

### Apps

```
GET    /api/v1/apps/containers              List containers
POST   /api/v1/apps/containers              Run new container
GET    /api/v1/apps/containers/{id}         Container details
POST   /api/v1/apps/containers/{id}/start   Start container
POST   /api/v1/apps/containers/{id}/stop    Stop container
POST   /api/v1/apps/containers/{id}/restart Restart container
DELETE /api/v1/apps/containers/{id}         Remove container
GET    /api/v1/apps/containers/{id}/logs    Container logs (stream)
GET    /api/v1/apps/stacks                  List stacks
POST   /api/v1/apps/stacks                  Deploy stack (compose YAML)
PUT    /api/v1/apps/stacks/{name}           Update stack
DELETE /api/v1/apps/stacks/{name}           Remove stack
GET    /api/v1/apps/vms                     List VMs
POST   /api/v1/apps/vms                     Create VM
POST   /api/v1/apps/vms/{id}/start         Start VM
POST   /api/v1/apps/vms/{id}/stop          Stop VM
DELETE /api/v1/apps/vms/{id}               Delete VM
```

### Network

```
GET    /api/v1/network/interfaces           List network interfaces
PUT    /api/v1/network/interfaces/{name}    Update interface config
GET    /api/v1/network/firewall             List firewall rules
POST   /api/v1/network/firewall             Add rule
PUT    /api/v1/network/firewall/{id}        Update rule
DELETE /api/v1/network/firewall/{id}        Delete rule
POST   /api/v1/network/firewall/reorder     Reorder rules
GET    /api/v1/network/wireguard            List WireGuard interfaces
POST   /api/v1/network/wireguard            Create WG interface
GET    /api/v1/network/wireguard/{name}/peers  List peers
POST   /api/v1/network/wireguard/{name}/peers  Add peer
DELETE /api/v1/network/wireguard/{name}/peers/{id}  Remove peer
GET    /api/v1/network/dns                  Get DNS config
PUT    /api/v1/network/dns                  Update DNS config
GET    /api/v1/network/proxy                List reverse proxy sites
POST   /api/v1/network/proxy                Add proxy site
PUT    /api/v1/network/proxy/{id}           Update proxy site
DELETE /api/v1/network/proxy/{id}           Remove proxy site
```

### Data Protection

```
GET    /api/v1/protection/jobs              List backup jobs
POST   /api/v1/protection/jobs              Create backup job
PUT    /api/v1/protection/jobs/{id}         Update job
DELETE /api/v1/protection/jobs/{id}         Delete job
POST   /api/v1/protection/jobs/{id}/run     Trigger job manually
GET    /api/v1/protection/jobs/{id}/history Job run history
GET    /api/v1/protection/scrubs            List scrub schedules
PUT    /api/v1/protection/scrubs/{pool}     Update scrub schedule
POST   /api/v1/protection/scrubs/{pool}/run Trigger scrub now
GET    /api/v1/protection/replication       List replication tasks
POST   /api/v1/protection/replication       Create replication task
DELETE /api/v1/protection/replication/{id}  Delete replication task
GET    /api/v1/protection/retention         List retention policies
POST   /api/v1/protection/retention         Create retention policy
PUT    /api/v1/protection/retention/{id}    Update policy
```

### Media

```
GET    /api/v1/media/drives                 List optical drives
GET    /api/v1/media/drives/{dev}/disc      Get disc info (title, type, tracks)
POST   /api/v1/media/rip                    Start rip job
GET    /api/v1/media/rip/status             Current rip progress
POST   /api/v1/media/rip/cancel             Cancel current rip
POST   /api/v1/media/eject/{dev}            Eject disc
GET    /api/v1/media/library/stats          Library statistics
GET    /api/v1/media/rips/recent            Recent rip history
GET    /api/v1/media/settings               Get media settings
PUT    /api/v1/media/settings               Update media settings (auto-rip, etc.)
```

### System

```
GET    /api/v1/system/info                  System information
GET    /api/v1/system/services              List systemd services
POST   /api/v1/system/services/{name}/start   Start service
POST   /api/v1/system/services/{name}/stop    Stop service
POST   /api/v1/system/services/{name}/restart Restart service
GET    /api/v1/system/updates               List available updates
POST   /api/v1/system/updates/apply         Apply updates
POST   /api/v1/system/power/reboot          Reboot system
POST   /api/v1/system/power/shutdown        Shutdown system
GET    /api/v1/system/ai/settings           Get AI configuration
PUT    /api/v1/system/ai/settings           Update AI config (provider, key, model)
```

### Chat

```
POST   /api/v1/chat/message                 Send message (HTTP fallback)
GET    /api/v1/chat/history                  Get chat history (paginated)
DELETE /api/v1/chat/history                  Clear chat history
```

---

## WebSocket Protocol

### Connection

```
WebSocket URL: ws://mk.local:8080/ws/chat?token={session_token}
```

### Message Format (Client to Server)

```json
{
  "type": "chat_message",
  "id": "uuid-v4",
  "content": "How's my storage looking?",
  "context": {
    "page": "/storage",
    "selected_pool": "tank"
  }
}
```

### Message Format (Server to Client)

```json
{
  "type": "chat_response",
  "id": "uuid-v4",
  "reply_to": "original-message-uuid",
  "content": "Your tank pool is healthy at 75% capacity...",
  "actions": [
    {
      "label": "View pool details",
      "action": "navigate",
      "target": "/storage?pool=tank"
    },
    {
      "label": "Create snapshot",
      "action": "api_call",
      "method": "POST",
      "endpoint": "/api/v1/storage/snapshots",
      "body": { "dataset": "tank", "name": "manual" }
    }
  ],
  "done": true
}
```

### Streaming Responses

For long responses, the server sends partial messages:

```json
{ "type": "chat_stream", "id": "uuid", "reply_to": "msg-id", "chunk": "Your tank", "done": false }
{ "type": "chat_stream", "id": "uuid", "reply_to": "msg-id", "chunk": " pool is healthy", "done": false }
{ "type": "chat_stream", "id": "uuid", "reply_to": "msg-id", "chunk": "...", "done": true, "actions": [...] }
```

### System Events (Server Push)

```json
{ "type": "alert", "severity": "warning", "message": "Disk sda temp 55C", "timestamp": "..." }
{ "type": "metric_update", "cpu": 47, "ram": 62, "network_in": 120, "network_out": 45 }
{ "type": "job_complete", "job": "daily-media", "status": "success", "duration": "45m" }
{ "type": "container_event", "container": "plex", "event": "restart", "timestamp": "..." }
{ "type": "typing_indicator", "active": true }
```

### Heartbeat

```json
Client: { "type": "ping" }
Server: { "type": "pong", "server_time": "2024-01-15T14:32:00Z" }
```

Heartbeat interval: 30 seconds. Connection considered dead after 3 missed pongs.
Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s).

---

## Frontend File Structure

```
webui/
|-- index.html
|-- package.json
|-- tsconfig.json
|-- tailwind.config.ts
|-- vite.config.ts
|-- postcss.config.js
|
|-- public/
|   |-- favicon.svg
|   |-- mk-logo.svg
|
|-- src/
|   |-- main.tsx                      Entry point
|   |-- App.tsx                       Root component (router + layout)
|   |-- index.css                     Tailwind imports + global styles
|   |
|   |-- components/
|   |   |-- ui/                       shadcn/ui components (auto-generated)
|   |   |   |-- button.tsx
|   |   |   |-- card.tsx
|   |   |   |-- table.tsx
|   |   |   |-- dialog.tsx
|   |   |   |-- badge.tsx
|   |   |   |-- tabs.tsx
|   |   |   |-- input.tsx
|   |   |   |-- toggle.tsx
|   |   |   |-- dropdown-menu.tsx
|   |   |   |-- progress.tsx
|   |   |   |-- tooltip.tsx
|   |   |   |-- scroll-area.tsx
|   |   |   +-- ...
|   |   |
|   |   |-- layout/
|   |   |   |-- TopBar.tsx            Navigation bar
|   |   |   |-- MainLayout.tsx        Page wrapper (nav + content + chat)
|   |   |   |-- ChatPanel.tsx         Right sidebar chat
|   |   |   +-- MobileNav.tsx         Hamburger menu for mobile
|   |   |
|   |   |-- dashboard/
|   |   |   |-- GaugeCard.tsx         CPU/RAM/Disk circular gauge
|   |   |   |-- HealthSummary.tsx     System health list
|   |   |   |-- QuickActions.tsx      Action button grid
|   |   |   |-- AlertsList.tsx        Alert feed
|   |   |   +-- ActivityLog.tsx       Event timeline
|   |   |
|   |   |-- storage/
|   |   |   |-- PoolCard.tsx          Pool with usage bar
|   |   |   |-- DatasetTable.tsx      Dataset list
|   |   |   |-- SnapshotList.tsx      Snapshot management
|   |   |   |-- DiskGrid.tsx          Disk health cards
|   |   |   +-- ShareManager.tsx      SMB/NFS share CRUD
|   |   |
|   |   |-- apps/
|   |   |   |-- ContainerTable.tsx    Container list with live stats
|   |   |   |-- StackCard.tsx         Compose stack view
|   |   |   |-- VMTable.tsx           VM list
|   |   |   +-- DeployDialog.tsx      Deploy new app modal
|   |   |
|   |   |-- network/
|   |   |   |-- InterfaceCard.tsx     Network interface info
|   |   |   |-- FirewallTable.tsx     Firewall rules editor
|   |   |   |-- WireGuardPeers.tsx    VPN peer management
|   |   |   |-- DNSConfig.tsx         DNS settings
|   |   |   +-- ProxySites.tsx        Reverse proxy config
|   |   |
|   |   |-- protection/
|   |   |   |-- BackupJobTable.tsx    Backup job list
|   |   |   |-- ScrubSchedule.tsx     Scrub config
|   |   |   |-- ReplicationTask.tsx   Replication management
|   |   |   +-- RetentionPolicy.tsx   Retention rules
|   |   |
|   |   |-- media/
|   |   |   |-- DriveStatus.tsx       Optical drive state
|   |   |   |-- RipProgress.tsx       Rip progress bar
|   |   |   |-- RecentRips.tsx        Rip history table
|   |   |   |-- LibraryStats.tsx      Media collection stats
|   |   |   +-- AutoRipToggle.tsx     Auto-rip setting
|   |   |
|   |   |-- system/
|   |   |   |-- SystemInfo.tsx        System details card
|   |   |   |-- ServiceTable.tsx      Running services
|   |   |   |-- UpdateList.tsx        Available updates
|   |   |   |-- PowerControls.tsx     Reboot/shutdown buttons
|   |   |   +-- AISettings.tsx        AI provider configuration
|   |   |
|   |   +-- chat/
|   |       |-- ChatBubble.tsx        Single message bubble
|   |       |-- ChatInput.tsx         Message input + send button
|   |       |-- ActionButton.tsx      Inline action button in chat
|   |       |-- TypingIndicator.tsx   Animated typing dots
|   |       +-- ContextSuggestions.tsx Page-aware suggestions
|   |
|   |-- pages/
|   |   |-- DashboardPage.tsx
|   |   |-- StoragePage.tsx
|   |   |-- AppsPage.tsx
|   |   |-- NetworkPage.tsx
|   |   |-- ProtectionPage.tsx
|   |   |-- MediaPage.tsx
|   |   |-- SystemPage.tsx
|   |   +-- LoginPage.tsx
|   |
|   |-- hooks/
|   |   |-- useWebSocket.ts          WebSocket connection manager
|   |   |-- useChat.ts               Chat state and message handling
|   |   |-- useMetrics.ts            Real-time system metrics
|   |   |-- useAuth.ts               Authentication state
|   |   +-- useApi.ts                SWR-based API fetching
|   |
|   |-- stores/
|   |   |-- chatStore.ts             Zustand chat state
|   |   |-- authStore.ts             Auth/session state
|   |   +-- uiStore.ts               UI preferences (theme, chat open)
|   |
|   |-- lib/
|   |   |-- api.ts                   API client (fetch wrapper)
|   |   |-- ws.ts                    WebSocket client class
|   |   |-- utils.ts                 Utility functions
|   |   +-- constants.ts             API URLs, config values
|   |
|   +-- types/
|       |-- api.ts                   API response types
|       |-- chat.ts                  Chat message types
|       |-- storage.ts               Storage domain types
|       |-- apps.ts                  Container/VM types
|       |-- network.ts               Network config types
|       |-- system.ts                System info types
|       +-- media.ts                 Media/rip types
```

---

## What Makes It Better Than TrueNAS UI

| Problem with TrueNAS | MK OS Solution |
|-----------------------|----------------|
| Need 5 clicks to find a setting | Everything important is on one page per domain |
| No AI assistance | AI chat always available, knows your system |
| Alerts buried in notifications | Alerts on dashboard, AI proactively mentions them |
| Dark mode is an afterthought | Dark-first design, every color chosen for dark bg |
| Slow page loads, full reloads | SPA with instant navigation, SWR caching |
| Complex forms for simple tasks | One-click actions, smart defaults |
| No disc ripping integration | Built-in media management for homelab use |
| Generic server management | Designed specifically for homelab power users |
| No real-time updates | WebSocket push for metrics, alerts, job status |
| Mobile experience is painful | Responsive from day one, touch-friendly actions |
| Confusing menu hierarchy | Flat navigation, 7 pages max, no nesting |
| No context-aware help | Chat suggests actions based on current page |

### Key Differentiators

1. **AI Chat as Primary Interface** - Do not just click buttons. Tell MK what you want.
   "Create a backup of my media pool to offsite every night" - done.

2. **No Menu Diving** - 7 top-level pages. Everything within 2 clicks max.
   TrueNAS: Storage > Pools > tank > Datasets > media > Edit > ...
   MK OS: Storage tab > click dataset > edit inline

3. **Smart Alerts** - AI summarizes what needs attention, suggests fixes.
   Not just "disk temp high" but "sda hit 55C during scrub, this is normal
   for your drive model. I will alert you if it stays high after scrub."

4. **One-Click Actions** - Reversible operations need no confirmation.
   Start backup? Click. Restart container? Click. Create snapshot? Click.
   Destructive operations (delete pool) get one simple confirmation.

5. **Dark-First Design** - Not a white UI with dark mode bolted on.
   Every color, contrast ratio, and shadow is designed for dark backgrounds.

6. **Speed** - SPA architecture, SWR caching, WebSocket updates.
   Page transitions are instant. Data updates in real-time. No spinners.

---

## Mobile Responsive Design

### Breakpoints

```
sm:  640px   - Phone landscape
md:  768px   - Tablet portrait
lg:  1024px  - Tablet landscape / small laptop
xl:  1280px  - Desktop
2xl: 1536px  - Large desktop
```

### Mobile Adaptations

- **Navigation**: Top bar collapses to hamburger menu (slide-out drawer)
- **Chat Panel**: Becomes full-screen overlay (slide up from bottom)
- **Tables**: Horizontal scroll with sticky first column, or card view toggle
- **Gauges**: Stack vertically, 2 per row on tablet, 1 on phone
- **Actions**: Bottom sheet instead of dropdown menus
- **Touch targets**: Minimum 44px hit area for all interactive elements

### Layout at Mobile (< 768px)

```
+---------------------------+
| [=] MK OS        [Chat]  |
+---------------------------+
|                           |
|  +-----+  +-----+        |
|  | CPU  |  | RAM |        |
|  | 47%  |  | 62% |        |
|  +-----+  +-----+        |
|                           |
|  +-----+  +-----+        |
|  | NET  |  | DISK|        |
|  | 120M |  | 78% |        |
|  +-----+  +-----+        |
|                           |
|  Health Summary           |
|  * Storage: Healthy       |
|  * Apps: 12/12 running    |
|                           |
|  Alerts (3)               |
|  ! Disk sda temp 55C     |
|  ! Pool 89% capacity     |
|                           |
+---------------------------+
```

### PWA Support

- Service worker for offline shell (show last-known metrics)
- App manifest for "Add to Home Screen"
- Push notifications for critical alerts
- Splash screen with MK logo

---

## Authentication

### Approach: PIN-Based (Homelab Optimized)

Homelabs do not need OAuth, LDAP, or complex auth. A 4-8 digit PIN is enough
for a device on your local network.

### Flow

```
1. User navigates to MK OS
2. If no valid session cookie -> show PIN pad
3. User enters PIN (4-8 digits)
4. Server validates PIN hash (bcrypt)
5. Server returns session token (JWT, 7-day expiry)
6. Token stored in httpOnly cookie
7. All API calls include token via cookie
8. After 7 days (or manual logout) -> back to PIN pad
```

### PIN Pad UI

```
+---------------------------+
|                           |
|       [MK LOGO]          |
|                           |
|    Enter your PIN         |
|                           |
|    +---+---+---+          |
|    | 1 | 2 | 3 |          |
|    +---+---+---+          |
|    | 4 | 5 | 6 |          |
|    +---+---+---+          |
|    | 7 | 8 | 9 |          |
|    +---+---+---+          |
|    |   | 0 | < |          |
|    +---+---+---+          |
|                           |
|    [ * * * * ]            |
|                           |
+---------------------------+
```

### Security Notes

- PIN is hashed with bcrypt (cost 12) on server
- Rate limiting: 5 attempts per minute, lockout for 5 min after 10 failures
- Session tokens are JWTs with 7-day expiry
- HTTPS required in production (self-signed cert auto-generated)
- LAN-only by default (bind to 192.168.x.x, not 0.0.0.0)
- Optional: IP allowlist for extra paranoid setups
- No password recovery - if you forget PIN, reset via CLI on the server

### Configuration

```python
# /etc/mk/auth.toml
[auth]
pin_hash = "$2b$12$..."   # bcrypt hash of PIN
session_expiry = "7d"
max_attempts = 10
lockout_duration = "5m"
bind_address = "0.0.0.0"  # or "192.168.1.10" for LAN-only
require_https = true
```

---

## Implementation Priority

### Phase 1 - Foundation (Week 1-2)
1. Vite + React + TypeScript + Tailwind setup
2. Color system + shadcn/ui theme configuration
3. Layout (TopBar, MainContent, ChatPanel shell)
4. Auth (PIN login, session management)
5. WebSocket connection manager
6. Dashboard page with mock data

### Phase 2 - Core Pages (Week 3-4)
1. Storage page (pools, datasets, disks)
2. Apps page (containers, stacks)
3. Network page (interfaces, firewall)
4. System page (info, services)
5. Real API integration (connect to FastAPI backend)

### Phase 3 - Advanced (Week 5-6)
1. Chat panel (full AI integration)
2. Data Protection page
3. Media page (disc ripper)
4. Real-time WebSocket updates
5. Mobile responsive polish

### Phase 4 - Polish (Week 7-8)
1. PWA support
2. Animations and transitions
3. Error states and loading skeletons
4. Accessibility audit
5. Performance optimization
6. Light theme

---

## Design Tokens Reference

Quick reference for developers implementing components:

```css
/* Spacing */
--spacing-page: 24px;        /* Page padding */
--spacing-card: 16px;        /* Card internal padding */
--spacing-gap: 12px;         /* Gap between cards */
--spacing-tight: 8px;        /* Tight spacing (within components) */

/* Border radius */
--radius-sm: 4px;            /* Buttons, badges */
--radius-md: 8px;            /* Cards, inputs */
--radius-lg: 12px;           /* Modals, panels */
--radius-full: 9999px;       /* Pills, avatars */

/* Font sizes */
--text-xs: 12px;             /* Timestamps, badges */
--text-sm: 14px;             /* Secondary text, table cells */
--text-base: 16px;           /* Body text */
--text-lg: 18px;             /* Card titles */
--text-xl: 20px;             /* Section headers */
--text-2xl: 24px;            /* Page titles */

/* Font weights */
--font-normal: 400;          /* Body text */
--font-medium: 500;          /* Labels, nav links */
--font-semibold: 600;        /* Headings, emphasis */
--font-bold: 700;            /* Page titles */

/* Shadows (dark theme - subtle blue glow) */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);
--shadow-accent: 0 0 20px rgba(0, 212, 255, 0.15);  /* Accent glow */

/* Transitions */
--transition-fast: 150ms ease;
--transition-normal: 250ms ease;
--transition-slow: 350ms ease;

/* Z-index layers */
--z-base: 0;
--z-dropdown: 100;
--z-sticky: 200;
--z-modal: 300;
--z-toast: 400;
--z-tooltip: 500;
```

---

*This blueprint contains everything needed to build the MK OS Web UI from scratch.
Every page, component, color, API endpoint, and interaction pattern is documented.
A developer should be able to implement the complete UI using only this document
as reference.*
