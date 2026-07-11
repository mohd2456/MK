"""Homelab Knowledge — Pre-built knowledge for MK's brain.

This module loads MK's brain with everything it needs to know about:
- Network topology (private network, IPs, routing)
- File transfer between machines
- Media file structure (movies, shows, Plex naming)
- Disk ripping workflow
- Home server/homelab best practices
- Service relationships

Call load_homelab_knowledge(graph) to inject all this into MK's brain.
"""

from __future__ import annotations

from mk.brain.graph import KnowledgeGraph


def load_homelab_knowledge(graph: KnowledgeGraph) -> None:
    """Load all homelab knowledge into the graph.

    Args:
        graph: The knowledge graph to populate
    """
    _load_network_knowledge(graph)
    _load_file_transfer_knowledge(graph)
    _load_media_structure_knowledge(graph)
    _load_disk_ripping_knowledge(graph)
    _load_homelab_services_knowledge(graph)
    _load_plex_knowledge(graph)


def _load_network_knowledge(graph: KnowledgeGraph) -> None:
    """Network topology and private network knowledge."""

    # Network concepts
    graph.add_node(
        "private_network",
        kind="network",
        description="Isolated local network for fast file transfers between homelab machines",
        purpose="Transfer files between machines without using internet bandwidth",
        router="old_router",
        speed="1gbps",
        internet="no",
    )

    graph.add_node(
        "main_network",
        kind="network",
        description="Primary network with internet access for API calls and downloads",
        purpose="Internet access, API calls, Telegram, downloads",
        internet="yes",
    )

    graph.add_node(
        "old_router",
        kind="hardware",
        description="Dedicated router for private network file transfers",
        speed="1gbps",
        purpose="Private LAN for inter-machine transfers",
    )

    # Network rules
    graph.add_node(
        "network_rule_transfer",
        kind="rule",
        rule="Always use private network (old router) for file transfers between machines",
        reason="Faster, doesn't use internet bandwidth, more secure",
    )

    graph.add_node(
        "network_rule_api",
        kind="rule",
        rule="Use main network for API calls, Telegram, and external downloads",
        reason="Needs internet access",
    )

    graph.add_node(
        "network_rule_dual",
        kind="rule",
        rule="Both PCs connect to BOTH networks - main for internet, private for transfers",
        reason="Each machine has two network connections",
    )

    # Relationships
    graph.add_edge("mk-brain", "private_network", "connected_to")
    graph.add_edge("mk-brain", "main_network", "connected_to")
    graph.add_edge("media-server", "private_network", "connected_to")
    graph.add_edge("media-server", "main_network", "connected_to")
    graph.add_edge("private_network", "old_router", "uses")

    # Transfer commands
    graph.add_node(
        "transfer_file",
        kind="command",
        description="Transfer a file between machines over private network",
        tool="ssh",
        command_template="scp -o 'BindAddress={source_private_ip}' {source_path} {target_user}@{target_private_ip}:{target_path}",
        alternative="rsync -avz --progress {source_path} {target_user}@{target_private_ip}:{target_path}",
        note="Always use private network IPs for transfers",
    )

    graph.add_node(
        "sync_folder",
        kind="command",
        description="Sync a folder between machines (only transfers changes)",
        tool="ssh",
        command_template="rsync -avz --progress --delete {source_path}/ {target_user}@{target_private_ip}:{target_path}/",
        note="--delete removes files on target that don't exist on source",
    )


def _load_file_transfer_knowledge(graph: KnowledgeGraph) -> None:
    """Knowledge about moving files between machines."""

    graph.add_node(
        "file_transfer_rules",
        kind="knowledge",
        rule_1="Always use rsync for large transfers (resumable, shows progress)",
        rule_2="Use scp for single small files",
        rule_3="Use private network IPs, never public/main network for local transfers",
        rule_4="For media files, transfer to the correct Plex folder structure",
        rule_5="After transfer, verify file integrity with md5sum if critical",
        rule_6="Set correct permissions after transfer: chown plex:plex for media files",
    )

    graph.add_node(
        "rsync",
        kind="tool_knowledge",
        description="Best tool for transferring files between homelab machines",
        usage="rsync -avz --progress source destination",
        flags_a="Archive mode (preserves permissions, timestamps)",
        flags_v="Verbose (shows what's being transferred)",
        flags_z="Compress during transfer",
        flags_progress="Shows transfer speed and ETA",
        flags_delete="Remove files on destination not on source (mirror mode)",
        resume="Rsync automatically resumes interrupted transfers",
    )

    graph.add_node(
        "scp",
        kind="tool_knowledge",
        description="Simple file copy over SSH",
        usage="scp source_file user@host:/destination/path",
        when_to_use="Single files, quick one-off transfers",
        limitation="Can't resume, no progress for multiple files",
    )

    # Remote editing
    graph.add_node(
        "remote_edit",
        kind="command",
        description="Edit a file on another machine from MK",
        method_1="SSH + sed: ssh user@host 'sed -i \"s/old/new/g\" /path/to/file'",
        method_2="SSH + cat + write: Read file, modify, write back",
        method_3="Copy to MK, edit, copy back (for complex edits)",
        tool="ssh",
    )

    graph.add_node(
        "remote_config_edit",
        kind="command",
        description="Edit config files on the media server from MK",
        steps="1. Read current file via SSH cat, 2. Modify content, 3. Write back via SSH",
        docker_configs="/opt/docker/",
        plex_config="/opt/docker/plex/config/",
        sonarr_config="/opt/docker/sonarr/config/",
        radarr_config="/opt/docker/radarr/config/",
    )


def _load_media_structure_knowledge(graph: KnowledgeGraph) -> None:
    """Knowledge about media file organization for Plex."""

    # Plex folder structure
    graph.add_node(
        "media_structure",
        kind="knowledge",
        description="How media files are organized for Plex",
        base_path="/data/media",
        movies_path="/data/media/movies",
        tv_path="/data/media/tv",
        music_path="/data/media/music",
        anime_path="/data/media/anime",
    )

    # Movie naming
    graph.add_node(
        "movie_naming",
        kind="knowledge",
        description="How to name movie files for Plex",
        format="Movie Title (Year)/Movie Title (Year).ext",
        example_1="Dune Part Two (2024)/Dune Part Two (2024).mkv",
        example_2="Oppenheimer (2023)/Oppenheimer (2023).mkv",
        example_3="The Batman (2022)/The Batman (2022).mkv",
        subtitle_format="Movie Title (Year)/Movie Title (Year).en.srt",
        extras_folder="Movie Title (Year)/extras/",
        note="Each movie gets its own folder. Year is required for Plex matching.",
    )

    # TV show naming
    graph.add_node(
        "tv_naming",
        kind="knowledge",
        description="How to name TV show files for Plex",
        format="Show Name/Season XX/Show Name - SXXEXX - Episode Title.ext",
        example_1="Severance/Season 02/Severance - S02E01 - Hello Ms Cobel.mkv",
        example_2="The Last of Us/Season 01/The Last of Us - S01E01 - When You're Lost in the Darkness.mkv",
        example_3="The Bear/Season 03/The Bear - S03E01 - Tomorrow.mkv",
        season_folder="Always use 'Season XX' format (Season 01, Season 02)",
        specials="Show Name/Specials/ for specials (S00E01)",
        note="Show folder → Season folder → Episode files",
    )

    # File formats
    graph.add_node(
        "media_formats",
        kind="knowledge",
        description="Preferred media file formats",
        video_best="MKV (Matroska) — supports all codecs, multiple audio/subtitle tracks",
        video_alt="MP4 — more compatible but fewer features",
        audio_best="FLAC for music, AAC/AC3/EAC3 for video audio tracks",
        subtitle_best="SRT (simple) or PGS/ASS (styled)",
        codec_best="H.265/HEVC for 4K (smaller files), H.264 for compatibility",
        resolution_4k="3840x2160",
        resolution_1080p="1920x1080",
        resolution_720p="1280x720",
    )

    # File placement after download
    graph.add_node(
        "media_placement",
        kind="knowledge",
        description="Where to put media files after download/rip",
        new_movies="Move to /data/media/movies/Title (Year)/Title (Year).mkv",
        new_tv="Move to /data/media/tv/Show/Season XX/Show - SXXEXX.mkv",
        downloads_folder="/data/downloads/ (temporary — move to media after)",
        rule="Never leave media in downloads. Always move to proper structure.",
        permissions="chown -R plex:plex /data/media/",
        after_move="Plex auto-detects new files. Or trigger scan: curl plex-api/library/scan",
    )


def _load_disk_ripping_knowledge(graph: KnowledgeGraph) -> None:
    """Knowledge about ripping discs and handling ripped files."""

    graph.add_node(
        "disk_ripping",
        kind="knowledge",
        description="Process for ripping Blu-ray/DVD discs",
        tool_bluray="MakeMKV (rips Blu-ray to MKV, preserves all tracks)",
        tool_dvd="MakeMKV or HandBrake",
        tool_encode="HandBrake (re-encode to H.265 for smaller files)",
        output_format="MKV",
    )

    graph.add_node(
        "rip_workflow",
        kind="knowledge",
        description="Steps after a disc is ripped",
        step_1="Disc ripped → raw MKV lands in /data/rips/ (large file, 20-50GB for Blu-ray)",
        step_2="Rename file to Plex format: 'Title (Year).mkv'",
        step_3="Optional: Re-encode with HandBrake to H.265 (shrinks 50GB → 10-15GB)",
        step_4="Create proper folder: /data/media/movies/Title (Year)/",
        step_5="Move final file to the folder",
        step_6="Set permissions: chown plex:plex",
        step_7="Trigger Plex library scan or wait for auto-detect",
        step_8="Verify in Plex (metadata, poster, subtitles matched)",
        step_9="Delete raw rip from /data/rips/ to free space",
        rips_folder="/data/rips/",
        note="Raw rips are HUGE. Always clean up after processing.",
    )

    graph.add_node(
        "rip_commands",
        kind="command",
        description="Commands MK uses after a rip is done",
        rename="mv '/data/rips/title_t00.mkv' '/data/rips/Movie Title (2024).mkv'",
        create_folder="mkdir -p '/data/media/movies/Movie Title (2024)'",
        move="mv '/data/rips/Movie Title (2024).mkv' '/data/media/movies/Movie Title (2024)/'",
        permissions="chown -R plex:plex '/data/media/movies/Movie Title (2024)'",
        scan_plex="curl -s 'http://localhost:32400/library/sections/1/refresh?X-Plex-Token=$PLEX_TOKEN'",
        cleanup="rm -f '/data/rips/title_t00.mkv'",
        check_space="df -h /data/",
    )

    graph.add_node(
        "handbrake_presets",
        kind="knowledge",
        description="HandBrake encoding presets for homelab",
        preset_4k="H.265 MKV 2160p60 (for 4K Blu-rays)",
        preset_1080p="H.265 MKV 1080p30 (for regular Blu-rays)",
        preset_small="H.265 MKV 720p30 (for DVDs or space-saving)",
        quality_rf="RF 18-22 (lower = better quality, bigger file)",
        audio="Passthrough original audio track (don't re-encode audio)",
        subtitles="Passthrough all subtitle tracks",
        cli="HandBrakeCLI -i input.mkv -o output.mkv --preset 'H.265 MKV 1080p30'",
    )


def _load_homelab_services_knowledge(graph: KnowledgeGraph) -> None:
    """Knowledge about homelab services and how they work together."""

    # Service relationships
    graph.add_node(
        "sonarr_knowledge",
        kind="knowledge",
        description="Sonarr manages TV show downloads automatically",
        purpose="Monitors for new episodes, sends to download client, renames and moves files",
        api_port=8989,
        config="/opt/docker/sonarr/config/",
        connects_to="transmission (download client), plex (media server)",
        root_folder="/data/media/tv/",
    )

    graph.add_node(
        "radarr_knowledge",
        kind="knowledge",
        description="Radarr manages movie downloads automatically",
        purpose="Search for movies, send to download client, rename and move to library",
        api_port=7878,
        config="/opt/docker/radarr/config/",
        connects_to="transmission (download client), plex (media server)",
        root_folder="/data/media/movies/",
    )

    graph.add_node(
        "transmission_knowledge",
        kind="knowledge",
        description="Transmission is the download client (torrent)",
        purpose="Downloads files requested by Sonarr/Radarr",
        api_port=9091,
        download_dir="/data/downloads/",
        complete_dir="/data/downloads/complete/",
        incomplete_dir="/data/downloads/incomplete/",
    )

    graph.add_node(
        "plex_knowledge",
        kind="knowledge",
        description="Plex serves media to all your devices",
        purpose="Stream movies and shows to TV, phone, anywhere",
        api_port=32400,
        libraries="Movies (/data/media/movies), TV (/data/media/tv)",
        transcoding="Hardware transcoding if available, otherwise software",
        scan_command="curl 'http://localhost:32400/library/sections/all/refresh?X-Plex-Token=$PLEX_TOKEN'",
        config="/opt/docker/plex/config/",
    )

    graph.add_node(
        "overseerr_knowledge",
        kind="knowledge",
        description="Overseerr is the request system — you ask for media here",
        purpose="Request movies/shows, it tells Sonarr/Radarr to grab them",
        api_port=5055,
    )

    # Service chain
    graph.add_edge("overseerr", "sonarr", "requests_from")
    graph.add_edge("overseerr", "radarr", "requests_from")
    graph.add_edge("sonarr", "transmission", "sends_downloads_to")
    graph.add_edge("radarr", "transmission", "sends_downloads_to")
    graph.add_edge("transmission", "plex", "provides_files_to")
    graph.add_edge("sonarr", "plex", "organizes_for")
    graph.add_edge("radarr", "plex", "organizes_for")

    # Docker knowledge
    graph.add_node(
        "docker_knowledge",
        kind="knowledge",
        description="All services run in Docker containers on media-server",
        compose_file="/opt/docker/docker-compose.yml",
        data_volume="/data/",
        config_volume="/opt/docker/",
        restart_all="cd /opt/docker && docker compose restart",
        update_all="cd /opt/docker && docker compose pull && docker compose up -d",
        logs="docker logs --tail 50 <container>",
        stats="docker stats --no-stream",
    )

    # Folder structure on media-server
    graph.add_node(
        "folder_structure",
        kind="knowledge",
        description="Folder layout on media-server",
        root="/data/",
        media="/data/media/ (organized library)",
        movies="/data/media/movies/ (Plex movies library)",
        tv="/data/media/tv/ (Plex TV library)",
        downloads="/data/downloads/ (active downloads)",
        downloads_complete="/data/downloads/complete/ (finished downloads)",
        rips="/data/rips/ (disc rips before processing)",
        backups="/data/backups/ (config backups)",
        docker_configs="/opt/docker/ (all container configs)",
    )


def _load_plex_knowledge(graph: KnowledgeGraph) -> None:
    """Plex-specific knowledge."""

    graph.add_node(
        "plex_api",
        kind="knowledge",
        description="Plex API commands MK can use",
        scan_all="curl 'http://localhost:32400/library/sections/all/refresh?X-Plex-Token=$PLEX_TOKEN'",
        scan_movies="curl 'http://localhost:32400/library/sections/1/refresh?X-Plex-Token=$PLEX_TOKEN'",
        scan_tv="curl 'http://localhost:32400/library/sections/2/refresh?X-Plex-Token=$PLEX_TOKEN'",
        status="curl 'http://localhost:32400/status/sessions?X-Plex-Token=$PLEX_TOKEN'",
        libraries="curl 'http://localhost:32400/library/sections?X-Plex-Token=$PLEX_TOKEN'",
        recently_added="curl 'http://localhost:32400/library/recentlyAdded?X-Plex-Token=$PLEX_TOKEN'",
    )

    graph.add_node(
        "plex_troubleshooting",
        kind="knowledge",
        description="Common Plex issues and fixes",
        buffering="Check: 1. Network speed 2. Transcoding (direct play better) 3. Disk I/O 4. RAM usage",
        not_finding_media="Check: 1. File naming matches Plex format 2. Permissions (plex:plex) 3. Run library scan 4. Check library root path",
        metadata_wrong="Fix: 1. Rename file correctly 2. Plex Match (fix match) 3. Refresh metadata",
        transcoding_slow="Fix: 1. Use direct play when possible 2. Hardware transcoding 3. Pre-encode to compatible format",
    )
