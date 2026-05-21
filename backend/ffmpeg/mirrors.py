"""Reliable FFmpeg download mirrors."""

import platform
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class Mirror:
    url: str
    os: str  # windows | darwin | linux | any
    arch: str  # x86_64 | arm64 | any
    package_type: str  # zip | tar.xz | tar.gz | dmg
    description: str


# Prioritized mirror list
MIRRORS: List[Mirror] = [
    # Windows - Gyan builds (most reliable)
    Mirror(
        url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        os="windows",
        arch="x86_64",
        package_type="zip",
        description="Gyan Windows essentials build",
    ),
    # Windows - BtbN builds (GitHub, good fallback)
    Mirror(
        url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        os="windows",
        arch="x86_64",
        package_type="zip",
        description="BtbN Windows GPL build",
    ),
    # macOS - Homebrew-style static build
    Mirror(
        url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
        os="darwin",
        arch="x86_64",
        package_type="zip",
        description="Evermeet macOS static build (Intel)",
    ),
    Mirror(
        url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
        os="darwin",
        arch="arm64",
        package_type="zip",
        description="Evermeet macOS static build (Apple Silicon)",
    ),
    # Linux - Static builds from John Van Sickle
    Mirror(
        url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        os="linux",
        arch="x86_64",
        package_type="tar.xz",
        description="John Van Sickle Linux amd64 static",
    ),
    Mirror(
        url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
        os="linux",
        arch="arm64",
        package_type="tar.xz",
        description="John Van Sickle Linux arm64 static",
    ),
]


def get_mirrors_for_system() -> List[Mirror]:
    """Return mirrors applicable to the current system."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture
    if machine in ("amd64", "x86_64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "any"

    applicable = []
    for mirror in MIRRORS:
        os_match = mirror.os == system or mirror.os == "any"
        arch_match = mirror.arch == arch or mirror.arch == "any"
        if os_match and arch_match:
            applicable.append(mirror)

    return applicable


def get_mirror_urls() -> List[str]:
    """Return just the URLs for the current system."""
    return [m.url for m in get_mirrors_for_system()]
