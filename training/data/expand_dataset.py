"""
Expand the MK training dataset to 5000+ examples through
additional augmentation patterns and conversation chains.
"""

import json
import random
from pathlib import Path
from typing import Any, Dict, List

from generate_dataset import (
    MK_SYSTEM_PROMPT, CONTAINERS, MOVIES, SHOWS,
    format_chatml, build_dataset
)

random.seed(42)


# ============================================================
# Extended conversation chains (multi-turn)
# ============================================================

def generate_multi_turn_conversations() -> List[Dict[str, Any]]:
    """Generate multi-turn conversation examples."""
    conversations = []

    # Conversation: Movie request flow
    for movie in random.sample(MOVIES, 15):
        conv = {
            "messages": [
                {"role": "system", "content": MK_SYSTEM_PROMPT},
                {"role": "user", "content": f"find me {movie}"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "media", "params": {"action": "search_movie", "query": movie}
                })},
                {"role": "user", "content": "yeah get that one"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "media", "params": {"action": "request_movie", "title": movie}
                })},
                {"role": "user", "content": "how long till its done"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "media", "params": {"action": "check_download_status"}
                })},
            ]
        }
        conversations.append(conv)

    # Conversation: Troubleshooting flow
    for container in random.sample(CONTAINERS, 10):
        conv = {
            "messages": [
                {"role": "system", "content": MK_SYSTEM_PROMPT},
                {"role": "user", "content": f"{container} isn't working"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "docker",
                    "params": {"action": "status", "container": container, "machine": "media-server"},
                    "plan": [f"Check {container} status", "Check logs", "Restart if needed"]
                })},
                {"role": "user", "content": "what do the logs say"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "docker",
                    "params": {"action": "logs", "container": container, "machine": "media-server"}
                })},
                {"role": "user", "content": "just restart it"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "docker",
                    "params": {"action": "restart", "container": container, "machine": "media-server"}
                })},
                {"role": "user", "content": "is it back up"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "docker",
                    "params": {"action": "status", "container": container, "machine": "media-server"}
                })},
            ]
        }
        conversations.append(conv)

    # Conversation: Status check then action
    for i in range(10):
        container = random.choice(CONTAINERS)
        conv = {
            "messages": [
                {"role": "system", "content": MK_SYSTEM_PROMPT},
                {"role": "user", "content": "how's everything running"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "system_monitor",
                    "params": {"machine": "media-server", "metric": "all"}
                })},
                {"role": "user", "content": f"restart {container} while you're at it"},
                {"role": "assistant", "content": json.dumps({
                    "tool": "docker",
                    "params": {"action": "restart", "container": container, "machine": "media-server"}
                })},
                {"role": "user", "content": "good thanks"},
                {"role": "assistant", "content": "Done. Anything else?"},
            ]
        }
        conversations.append(conv)

    return conversations


# ============================================================
# SSH command variations (lots of system admin tasks)
# ============================================================

def generate_ssh_variations() -> List[Dict[str, Any]]:
    """Generate SSH command execution examples."""
    examples = []

    ssh_tasks = [
        ("check running processes", "ps aux --sort=-%mem | head -20"),
        ("show top memory users", "ps aux --sort=-%mem | head -10"),
        ("check for zombie processes", "ps aux | grep -w Z"),
        ("show listening ports", "ss -tlnp"),
        ("check failed systemd services", "systemctl --failed"),
        ("show last 20 log entries", "journalctl -n 20 --no-pager"),
        ("check who's logged in", "who"),
        ("show last logins", "last -10"),
        ("check swap usage", "swapon --show"),
        ("show io stats", "iostat -x 1 3 2>/dev/null || cat /proc/diskstats"),
        ("check dns resolution", "nslookup google.com"),
        ("show routing table", "ip route"),
        ("check arp table", "arp -a 2>/dev/null || ip neigh"),
        ("show mounted drives", "lsblk"),
        ("check smart status of drives", "smartctl -a /dev/sda 2>/dev/null || echo 'smartctl not available'"),
        ("show kernel version", "uname -a"),
        ("check for updates", "apt list --upgradable 2>/dev/null || dnf check-update 2>/dev/null"),
        ("show docker disk usage", "docker system df"),
        ("check container resource usage", "docker stats --no-stream"),
        ("list docker networks", "docker network ls"),
        ("show docker volumes", "docker volume ls"),
        ("check if port 80 is open", "ss -tlnp | grep :80"),
        ("test connection to plex", "curl -s -o /dev/null -w '%{http_code}' localhost:32400"),
        ("check certificate expiry", "openssl s_client -connect localhost:443 2>/dev/null | openssl x509 -noout -dates"),
        ("show cron jobs", "crontab -l 2>/dev/null && ls /etc/cron.d/"),
        ("find large files", "find / -size +1G -type f 2>/dev/null | head -20"),
        ("check inode usage", "df -i"),
        ("show memory details", "cat /proc/meminfo | head -20"),
        ("test download speed", "curl -s -o /dev/null -w '%{speed_download}' http://speedtest.tele2.net/1MB.zip"),
        ("check firewall rules", "iptables -L -n 2>/dev/null || ufw status 2>/dev/null"),
    ]

    machines = ["media-server", "mk-brain"]

    for task_desc, command in ssh_tasks:
        machine = random.choice(machines)
        # Multiple ways to ask
        variations = [
            task_desc,
            task_desc.replace("check", "show me"),
            task_desc.replace("show", "what's"),
            f"run {task_desc}",
            f"can you {task_desc}",
        ]
        for user_msg in random.sample(variations, min(2, len(variations))):
            assistant_msg = json.dumps({
                "tool": "ssh",
                "params": {"machine": machine, "command": command}
            })
            examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# More personality and casual interaction
# ============================================================

def generate_personality_variations() -> List[Dict[str, Any]]:
    """Generate more personality/casual interaction examples."""
    examples = []

    casual_exchanges = [
        ("sup", "Not much. Servers are running smooth. What you need?"),
        ("aight bet", "What we doing?"),
        ("that was fast", "I try. What's next?"),
        ("perfect", "Anything else?"),
        ("nice one", "Got you. Need anything else?"),
        ("my bad I meant sonarr not radarr", "No worries. Want me to restart sonarr instead?"),
        ("wait nevermind", "Aight, cancelled. Let me know if you change your mind."),
        ("you're the best", "Just doing my job. What else?"),
        ("lol", "What's funny? Need something?"),
        ("bruh", "What happened?"),
        ("ugh everything is breaking", "Let me check. Running diagnostics on all services now."),
        ("im stressed", "I got the homelab. You focus on you. Want me to handle something?"),
        ("can you handle things while im gone", "Yeah I got it. I'll text you if anything needs your attention."),
        ("im back", "Welcome back. Everything's been smooth. Nothing to report."),
        ("what did I miss", "All quiet. No alerts, no issues. Plex has been up the whole time."),
        ("good night", "Night. I'll keep watch. Rest up."),
        ("morning", "Morning. All systems green overnight. What's the plan today?"),
        ("anything happen while I was asleep", "Nah, all quiet. One Plex update came in but I held off. Want me to apply it?"),
        ("you still up", "Always. What you need?"),
        ("how long have you been running", "72 hours since last restart. All good though, no issues."),
        ("are you ok", "All good. CPU at 8%, memory 34%, disk 61%. Running smooth."),
        ("go to sleep", "I don't sleep. But I'll go quiet unless something comes up."),
        ("stfu", "Aight. I'll only talk if something's urgent."),
        ("talk to me", "I'm here. What's on your mind? Or want a status update?"),
        ("bored fix something", "Everything's running fine honestly. Want me to optimize something? Or find you something to watch?"),
    ]

    for user_msg, assistant_msg in casual_exchanges:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Complex routing with reasoning
# ============================================================

def generate_advanced_routing() -> List[Dict[str, Any]]:
    """Generate more nuanced routing decisions."""
    examples = []

    # Tasks that SEEM complex but are actually local
    tricky_local = [
        ("what's using the most cpu", '{"route": "local", "reason": "Single command can answer this", "tool": "ssh", "params": {"machine": "media-server", "command": "ps aux --sort=-%cpu | head -5"}}'),
        ("is plex using too much memory", '{"route": "local", "reason": "Check specific container stats", "tool": "docker", "params": {"action": "stats", "container": "plex", "machine": "media-server"}}'),
        ("when did the server last restart", '{"route": "local", "reason": "Uptime command", "tool": "ssh", "params": {"machine": "media-server", "command": "uptime -s"}}'),
        ("is the internet working", '{"route": "local", "reason": "Simple connectivity test", "tool": "ssh", "params": {"machine": "mk-brain", "command": "ping -c 2 8.8.8.8 && echo OK || echo FAIL"}}'),
        ("how many movies do I have", '{"route": "local", "reason": "Plex library count is a simple API call", "tool": "media", "params": {"action": "get_plex_libraries"}}'),
        ("did my download finish", '{"route": "local", "reason": "Check download queue status", "tool": "media", "params": {"action": "check_download_status"}}'),
        ("which containers are using the most resources", '{"route": "local", "reason": "Docker stats command", "tool": "ssh", "params": {"machine": "media-server", "command": "docker stats --no-stream --format \\"table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\""}}'),
    ]

    # Tasks that SEEM simple but need cloud
    tricky_cloud = [
        ("why is plex buffering", '{"route": "cloud", "reason": "Troubleshooting requires analyzing multiple possible causes: transcoding settings, network bandwidth, disk I/O, client capability"}'),
        ("should I switch to jellyfin", '{"route": "cloud", "reason": "Comparison requires knowledge of both platforms and analysis of user needs and tradeoffs"}'),
        ("make my server faster", '{"route": "cloud", "reason": "Performance optimization requires analysis of current bottlenecks and knowledge of optimization strategies"}'),
        ("what am I doing wrong with my setup", '{"route": "cloud", "reason": "Requires understanding current setup context and identifying potential issues - needs reasoning"}'),
        ("is my network secure", '{"route": "cloud", "reason": "Security assessment requires checking multiple vectors and understanding attack surfaces"}'),
    ]

    for user_msg, assistant_msg in tricky_local:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    for user_msg, assistant_msg in tricky_cloud:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Typo handling and messy input
# ============================================================

def generate_messy_input() -> List[Dict[str, Any]]:
    """MK should handle typos, slang, and messy input."""
    examples = []

    messy_pairs = [
        ("restrart plex", '{"tool": "docker", "params": {"action": "restart", "container": "plex", "machine": "media-server"}}'),
        ("statis", '{"tool": "system_monitor", "params": {"machine": "media-server", "metric": "all"}}'),
        ("donwload batman", '{"tool": "media", "params": {"action": "request_movie", "title": "The Batman"}}'),
        ("sonar logs", '{"tool": "docker", "params": {"action": "logs", "container": "sonarr", "machine": "media-server"}}'),
        ("chekc disk", '{"tool": "ssh", "params": {"machine": "media-server", "command": "df -h"}}'),
        ("plx working?", '{"tool": "docker", "params": {"action": "status", "container": "plex", "machine": "media-server"}}'),
        ("get me dat movie dune", '{"tool": "media", "params": {"action": "request_movie", "title": "Dune Part Two"}}'),
        ("wat containers r up", '{"tool": "docker", "params": {"action": "list", "machine": "media-server"}}'),
        ("stp radarr", '{"tool": "docker", "params": {"action": "stop", "container": "radarr", "machine": "media-server"}}'),
        ("hows da server", '{"tool": "system_monitor", "params": {"machine": "media-server", "metric": "all"}}'),
        ("ntwrk check", '{"tool": "ssh", "params": {"machine": "media-server", "command": "ping -c 3 8.8.8.8"}}'),
        ("mem usage", '{"tool": "ssh", "params": {"machine": "media-server", "command": "free -h"}}'),
        ("wats running", '{"tool": "docker", "params": {"action": "list", "machine": "media-server"}}'),
        ("hw much space", '{"tool": "ssh", "params": {"machine": "media-server", "command": "df -h"}}'),
        ("kill plex", '{"tool": "docker", "params": {"action": "stop", "container": "plex", "machine": "media-server"}}'),
    ]

    for user_msg, assistant_msg in messy_pairs:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Time-aware responses
# ============================================================

def generate_time_aware() -> List[Dict[str, Any]]:
    """Generate time-context-aware examples."""
    examples = []

    time_examples = [
        ("[time: 3:00 AM] hey", "It's 3am. Everything's running fine. You should sleep. I'll text you if anything comes up."),
        ("[time: 7:00 AM] morning status", json.dumps({
            "tool": "system_monitor",
            "params": {"machine": "media-server", "metric": "all"},
            "context": "Morning check - summarize overnight status"
        })),
        ("[time: 11:00 PM] grab me a movie to watch", json.dumps({
            "tool": "media",
            "params": {"action": "get_recently_added"},
            "context": "Late night, suggest from library first before downloading"
        })),
        ("[time: 2:00 PM] update everything", json.dumps({
            "tool": "docker",
            "params": {"action": "update_all", "machine": "media-server"},
            "context": "Daytime update is fine, low risk of disrupting viewing"
        })),
        ("[time: 8:00 PM] restart plex", json.dumps({
            "confirm": True,
            "action": "Restart Plex during prime viewing hours",
            "risk": "Someone might be watching right now. Quick check first.",
            "tool": "ssh",
            "params": {"machine": "media-server", "command": "curl -s localhost:32400/status/sessions -H 'X-Plex-Token: $PLEX_TOKEN'"}
        })),
    ]

    for user_msg, assistant_msg in time_examples:
        if isinstance(assistant_msg, dict):
            assistant_msg = json.dumps(assistant_msg)
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Combinatorial expansion for more volume
# ============================================================

def generate_combinatorial() -> List[Dict[str, Any]]:
    """Generate more examples through combinatorial expansion."""
    examples = []

    # All containers x all actions
    actions_map = {
        "restart": "restart",
        "stop": "stop",
        "start": "start",
        "status": "status",
        "logs": "logs",
        "update": "pull",
    }

    ask_templates = {
        "restart": [
            "restart {c}", "reboot {c}", "bounce {c}",
            "{c} restart", "can you restart {c}",
            "restart {c} please", "give {c} a restart",
            "{c} needs a restart", "yo restart {c}",
        ],
        "stop": [
            "stop {c}", "kill {c}", "shut down {c}",
            "turn off {c}", "disable {c}", "take {c} down",
        ],
        "start": [
            "start {c}", "turn on {c}", "spin up {c}",
            "bring {c} back", "enable {c}", "launch {c}",
        ],
        "status": [
            "is {c} running", "{c} status", "check {c}",
            "is {c} up", "how's {c}", "{c} working?",
        ],
        "logs": [
            "{c} logs", "show {c} logs", "what's in {c} logs",
            "check {c} for errors", "tail {c} logs",
        ],
        "update": [
            "update {c}", "upgrade {c}", "pull latest {c}",
            "get new version of {c}", "update {c} image",
        ],
    }

    for container in CONTAINERS:
        for action_name, docker_action in actions_map.items():
            templates = ask_templates[action_name]
            # Pick 2 random templates per container per action
            for template in random.sample(templates, min(2, len(templates))):
                user_msg = template.format(c=container)
                assistant_msg = json.dumps({
                    "tool": "docker",
                    "params": {
                        "action": docker_action,
                        "container": container,
                        "machine": "media-server"
                    }
                })
                examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    # All movies x different request styles
    request_styles = [
        "get {m}", "download {m}", "grab {m}",
        "I want {m}", "queue {m}", "add {m}",
        "find and download {m}", "get me {m}",
        "put {m} on plex", "yo {m}",
    ]

    for movie in MOVIES:
        for style in random.sample(request_styles, 3):
            user_msg = style.format(m=movie)
            assistant_msg = json.dumps({
                "tool": "media",
                "params": {"action": "request_movie", "title": movie}
            })
            examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    # All shows x request styles
    for show in SHOWS:
        for style in random.sample(request_styles, 3):
            user_msg = style.format(m=show)
            season = random.randint(1, 5)
            assistant_msg = json.dumps({
                "tool": "media",
                "params": {"action": "request_show", "title": show, "season": season}
            })
            examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Additional safety and confirmation variations
# ============================================================

def generate_safety_expanded() -> List[Dict[str, Any]]:
    """More safety check variations."""
    examples = []

    dangerous_patterns = [
        ("delete all the logs", "rm -rf /var/log/*", "All system logs will be permanently deleted"),
        ("nuke the docker data", "rm -rf /var/lib/docker", "ALL containers, images, and volumes will be destroyed"),
        ("reset the firewall", "iptables -F", "All firewall rules removed - server exposed"),
        ("wipe and reinstall plex", "docker rm -v plex && docker rmi plexinc/pms-docker", "All Plex data including watch history lost"),
        ("format /dev/sdb", "mkfs.ext4 /dev/sdb", "All data on that drive permanently destroyed"),
        ("rm -rf the media folder", "rm -rf /data/media", "ALL media files permanently deleted"),
        ("drop all databases", "docker exec postgres psql -c 'DROP SCHEMA public CASCADE'", "All database data permanently lost"),
        ("turn off automatic updates", "systemctl disable watchtower", "Containers won't auto-update - security risk"),
        ("expose the server to internet", "ufw allow from any to any", "CRITICAL: Server fully exposed to internet attacks"),
        ("run this random script from github", "curl url | bash", "Running untrusted code - could compromise entire system"),
    ]

    for user_msg, action, risk in dangerous_patterns:
        assistant_msg = json.dumps({
            "confirm": True,
            "action": action,
            "risk": risk
        })
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    # User confirms dangerous action
    confirm_flows = [
        ("yes do it", "Executing now."),
        ("yeah go ahead", "On it."),
        ("yep", "Done."),
        ("confirmed", "Executing."),
        ("do it", "Aight, running it now."),
    ]

    for user_msg, assistant_msg in confirm_flows:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    # User denies dangerous action
    deny_flows = [
        ("no wait", "Cancelled. Nothing was touched."),
        ("nah nevermind", "Aight, cancelled."),
        ("actually dont", "Stopped. Nothing happened."),
        ("no", "Cancelled."),
        ("stop", "Stopped. Nothing was done."),
    ]

    for user_msg, assistant_msg in deny_flows:
        examples.append(format_chatml(MK_SYSTEM_PROMPT, user_msg, assistant_msg))

    return examples


# ============================================================
# Main: combine everything
# ============================================================

def main():
    """Generate the full expanded dataset."""
    print("Generating expanded MK training dataset...")

    # Start with base dataset
    base_dataset = build_dataset()

    # Add all expansions
    expanded = []
    expanded.extend(generate_multi_turn_conversations())
    expanded.extend(generate_ssh_variations())
    expanded.extend(generate_personality_variations())
    expanded.extend(generate_advanced_routing())
    expanded.extend(generate_messy_input())
    expanded.extend(generate_time_aware())
    expanded.extend(generate_combinatorial())
    expanded.extend(generate_safety_expanded())

    # Combine
    full_dataset = base_dataset + expanded

    # Deduplicate by user message
    seen = set()
    unique_dataset = []
    for item in full_dataset:
        if "messages" in item:
            # Use first user message as key
            user_msgs = [m["content"] for m in item["messages"] if m["role"] == "user"]
            key = "|".join(user_msgs)
            if key not in seen:
                seen.add(key)
                unique_dataset.append(item)

    # Shuffle
    random.shuffle(unique_dataset)

    # Save full dataset
    output_dir = Path(__file__).parent
    full_path = output_dir / "mk_training_data.jsonl"
    with open(full_path, "w") as f:
        for item in unique_dataset:
            f.write(json.dumps(item) + "\n")

    # Train/val split (90/10)
    split_idx = int(len(unique_dataset) * 0.9)
    train_data = unique_dataset[:split_idx]
    val_data = unique_dataset[split_idx:]

    train_path = output_dir / "mk_train.jsonl"
    val_path = output_dir / "mk_val.jsonl"

    with open(train_path, "w") as f:
        for item in train_data:
            f.write(json.dumps(item) + "\n")

    with open(val_path, "w") as f:
        for item in val_data:
            f.write(json.dumps(item) + "\n")

    print(f"\n{'='*50}")
    print(f"FULL DATASET: {len(unique_dataset)} examples")
    print(f"Train: {len(train_data)} | Val: {len(val_data)}")
    print(f"{'='*50}")
    print(f"\nBreakdown:")
    print(f"  Base examples:        {len(base_dataset)}")
    print(f"  Multi-turn convos:    {len(generate_multi_turn_conversations())}")
    print(f"  SSH variations:       {len(generate_ssh_variations())}")
    print(f"  Personality:          {len(generate_personality_variations())}")
    print(f"  Advanced routing:     {len(generate_advanced_routing())}")
    print(f"  Messy input:          {len(generate_messy_input())}")
    print(f"  Time-aware:           {len(generate_time_aware())}")
    print(f"  Combinatorial:        {len(generate_combinatorial())}")
    print(f"  Safety expanded:      {len(generate_safety_expanded())}")
    print(f"\nFiles saved:")
    print(f"  {full_path}")
    print(f"  {train_path}")
    print(f"  {val_path}")


if __name__ == "__main__":
    main()
