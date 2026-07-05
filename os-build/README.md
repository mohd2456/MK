# MK OS Build System

Build scripts for creating a minimal Linux image that boots directly into MK.

## Philosophy

- **No GUI.** No desktop. No browser. No bloat.
- **Boot up -> MK is talking to you.**
- **The terminal IS MK. MK IS the terminal.**

The resulting image contains only:
- Linux kernel + essential userspace
- Networking (systemd-networkd with DHCP)
- Python 3.9+ runtime
- Node.js 22 runtime (for Telegram gateway)
- MK AI Operating System

## Files

| File | Purpose |
|------|---------|
| `build.sh` | Main build script - orchestrates the entire process |
| `Dockerfile` | Docker-based build environment for reproducibility |
| `mk.service` | systemd service file - starts MK on boot |
| `mk-shell.sh` | Shell wrapper - replaces bash as login shell |
| `motd` | Message of the day - MK branding on login |

## Building

### Using Docker (Recommended)

```bash
# Build the OS image
./build.sh

# Or specify output directory
./build.sh --output /path/to/output --arch amd64
```

### Manual Build

Requires: `debootstrap`, `squashfs-tools`, `xorriso`

```bash
sudo ./build.sh
```

## Output

The build produces a compressed rootfs archive:
```
output/mk-os-0.1.0-amd64.tar.gz
```

This can be:
- Written to a USB drive for bare-metal boot
- Used as a base for a VM image
- Deployed to a container environment

## Customization

### Adding Services

Edit `mk.service` to adjust resource limits, environment variables,
or startup behavior.

### Network Configuration

The default config uses DHCP on all ethernet interfaces.
Edit the systemd-networkd configuration in `build.sh` for static IPs.

### Target Hardware

Default build targets x86_64. For ARM (Raspberry Pi, etc.):
```bash
./build.sh --arch arm64
```

## Security

- MK runs with systemd hardening (ProtectSystem, NoNewPrivileges)
- Resource limits prevent runaway processes
- Only authorized Telegram chat IDs can communicate with MK
- Secrets are encrypted at rest
