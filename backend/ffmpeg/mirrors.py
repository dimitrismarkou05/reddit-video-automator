"""Reliable FFmpeg download mirrors."""

import platform
from typing import List, Dict


def get_mirrors_for_system() -> List[Dict]:
    """Return mirrors applicable to the current system with fallbacks."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture
    if machine in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "any"

    all_mirrors = _get_all_mirrors()
    applicable = []

    # Exact OS and arch matches first
    for mirror in all_mirrors:
        os_match = mirror["os"] == system or mirror["os"] == "any"
        arch_match = mirror["arch"] == arch or mirror["arch"] == "any"
        if os_match and arch_match:
            applicable.append(mirror)

    # Then OS match with any arch
    for mirror in all_mirrors:
        if mirror in applicable:
            continue
        os_match = mirror["os"] == system or mirror["os"] == "any"
        arch_match = mirror["arch"] == "any"
        if os_match and arch_match:
            applicable.append(mirror)

    # Finally any universal mirrors
    for mirror in all_mirrors:
        if mirror in applicable:
            continue
        if mirror["os"] == "any" and mirror["arch"] == "any":
            applicable.append(mirror)

    return applicable


def get_mirror_urls() -> List[str]:
    """Return just the URLs for the current system."""
    mirrors = get_mirrors_for_system()
    return [m["url"] for m in mirrors]


def _get_all_mirrors() -> List[Dict]:
    """Prioritized mirror list with multiple fallbacks per platform."""
    return [
        # ========== WINDOWS ==========
        {
            "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            "os": "windows",
            "arch": "x86_64",
            "type": "zip",
            "name": "Gyan.dev Windows (Primary)",
        },
        {
            "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "os": "windows",
            "arch": "x86_64",
            "type": "zip",
            "name": "BtbN GitHub Windows (Secondary)",
        },
        {
            "url": "https://github.com/yt-dlp/ffmpeg-binaries/releases/download/latest/ffmpeg-win64.zip",
            "os": "windows",
            "arch": "x86_64",
            "type": "zip",
            "name": "yt-dlp Windows (Tertiary)",
        },
        # ========== macOS INTEL ==========
        {
            "url": "https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
            "os": "darwin",
            "arch": "x86_64",
            "type": "zip",
            "name": "Evermeet Intel (Primary)",
        },
        {
            "url": "https://www.osxexperts.net/ffmpeg73intel.zip",
            "os": "darwin",
            "arch": "x86_64",
            "type": "zip",
            "name": "OSXExperts Intel (Secondary)",
        },
        # ========== macOS APPLE SILICON ==========
        {
            "url": "https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
            "os": "darwin",
            "arch": "arm64",
            "type": "zip",
            "name": "Evermeet ARM64 (Primary)",
        },
        # ========== LINUX X86_64 ==========
        {
            "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
            "os": "linux",
            "arch": "x86_64",
            "type": "tar.xz",
            "name": "John Van Sickle amd64 (Primary)",
        },
        {
            "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
            "os": "linux",
            "arch": "x86_64",
            "type": "tar.xz",
            "name": "BtbN Linux amd64 (Secondary)",
        },
        {
            "url": "https://github.com/yt-dlp/ffmpeg-binaries/releases/download/latest/ffmpeg-linux64.zip",
            "os": "linux",
            "arch": "x86_64",
            "type": "zip",
            "name": "yt-dlp Linux (Tertiary)",
        },
        # ========== LINUX ARM64 ==========
        {
            "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
            "os": "linux",
            "arch": "arm64",
            "type": "tar.xz",
            "name": "John Van Sickle ARM64 (Primary)",
        },
    ]
