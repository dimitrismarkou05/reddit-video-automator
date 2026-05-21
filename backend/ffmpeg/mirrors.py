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
    backup_url: str = None  # Optional backup URL


# Prioritized mirror list with multiple fallbacks per platform
MIRRORS: List[Mirror] = [
    # ========== WINDOWS MIRRORS ==========
    Mirror(
        url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        os="windows",
        arch="x86_64",
        package_type="zip",
        description="Gyan.dev Windows essentials (Official)",
        backup_url="https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-release-essentials.zip",
    ),
    Mirror(
        url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        os="windows",
        arch="x86_64",
        package_type="zip",
        description="BtbN GitHub Windows GPL",
        backup_url="https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2024-06-18-12-53/ffmpeg-N-114876-gd3de6fe9f1-win64-gpl.zip",
    ),
    Mirror(
        url="https://www.gpgni.com/ffmpeg/builds/ffmpeg-git-full.7z",
        os="windows",
        arch="x86_64",
        package_type="7z",
        description="GPGNI Windows build (alternative)",
    ),
    Mirror(
        url="https://github.com/yt-dlp/ffmpeg-binaries/releases/download/latest/ffmpeg-win64.zip",
        os="windows",
        arch="x86_64",
        package_type="zip",
        description="yt-dlp FFmpeg Windows binaries",
    ),
    
    # ========== macOS INTEL MIRRORS ==========
    Mirror(
        url="https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
        os="darwin",
        arch="x86_64",
        package_type="zip",
        description="Evermeet Intel (static, no redirect)",
        backup_url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    ),
    Mirror(
        url="https://www.osxexperts.net/ffmpeg73intel.zip",
        os="darwin",
        arch="x86_64",
        package_type="zip",
        description="OSXExperts Intel build",
    ),
    Mirror(
        url="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-darwin-x64",
        os="darwin",
        arch="x86_64",
        package_type="binary",
        description="FFmpeg static binary (GitHub)",
    ),
    
    # ========== macOS APPLE SILICON MIRRORS ==========
    Mirror(
        url="https://evermeet.cx/ffmpeg/ffmpeg-7.0.2.zip",
        os="darwin",
        arch="arm64",
        package_type="zip",
        description="Evermeet Apple Silicon (static, no redirect)",
        backup_url="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
    ),
    Mirror(
        url="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-darwin-arm64",
        os="darwin",
        arch="arm64",
        package_type="binary",
        description="FFmpeg static binary Apple Silicon",
    ),
    
    # ========== LINUX X86_64 MIRRORS ==========
    Mirror(
        url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        os="linux",
        arch="x86_64",
        package_type="tar.xz",
        description="John Van Sickle amd64 (Official)",
        backup_url="https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz",
    ),
    Mirror(
        url="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        os="linux",
        arch="x86_64",
        package_type="tar.xz",
        description="BtbN GitHub Linux amd64",
        backup_url="https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2024-06-18-12-53/ffmpeg-N-114876-gd3de6fe9f1-linux64-gpl.tar.xz",
    ),
    Mirror(
        url="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-linux-x64",
        os="linux",
        arch="x86_64",
        package_type="binary",
        description="FFmpeg static binary (GitHub, direct download)",
    ),
    Mirror(
        url="https://github.com/yt-dlp/ffmpeg-binaries/releases/download/latest/ffmpeg-linux64.zip",
        os="linux",
        arch="x86_64",
        package_type="zip",
        description="yt-dlp FFmpeg Linux binaries",
    ),
    
    # ========== LINUX ARM64 MIRRORS ==========
    Mirror(
        url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
        os="linux",
        arch="arm64",
        package_type="tar.xz",
        description="John Van Sickle arm64 (Official)",
    ),
    Mirror(
        url="https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-linux-arm64",
        os="linux",
        arch="arm64",
        package_type="binary",
        description="FFmpeg static binary ARM64",
    ),
    
    # ========== UNIVERSAL FALLBACKS (try these if platform-specific fail) ==========
    Mirror(
        url="https://github.com/FFmpeg/FFmpeg/archive/refs/heads/master.zip",
        os="any",
        arch="any",
        package_type="zip",
        description="FFmpeg source (requires compilation - last resort)",
    ),
]


def get_mirrors_for_system() -> List[Mirror]:
    """Return mirrors applicable to the current system with expanded fallbacks."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture
    if machine in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "any"

    applicable = []
    
    # First, add exact matches
    for mirror in MIRRORS:
        os_match = mirror.os == system or mirror.os == "any"
        arch_match = mirror.arch == arch or mirror.arch == "any"
        if os_match and arch_match:
            applicable.append(mirror)
    
    # Second, add fallback mirrors for the same OS but different arch
    if arch != "any":
        for mirror in MIRRORS:
            os_match = mirror.os == system or mirror.os == "any"
            arch_match = mirror.arch == "any"
            if os_match and arch_match and mirror not in applicable:
                applicable.append(mirror)
    
    # Finally, add any truly universal mirrors
    for mirror in MIRRORS:
        if mirror.os == "any" and mirror.arch == "any" and mirror not in applicable:
            applicable.append(mirror)
    
    # Add backup URLs as separate entries for retry logic
    expanded_mirrors = []
    for mirror in applicable:
        # Add primary URL
        expanded_mirrors.append(mirror)
        # Add backup URL if exists
        if mirror.backup_url:
            expanded_mirrors.append(Mirror(
                url=mirror.backup_url,
                os=mirror.os,
                arch=mirror.arch,
                package_type=mirror.package_type,
                description=f"{mirror.description} (backup)",
            ))
    
    return expanded_mirrors


def get_mirror_urls() -> List[str]:
    """Return just the URLs for the current system."""
    mirrors = get_mirrors_for_system()
    urls = [m.url for m in mirrors]
    
    # Log the number of mirrors found (for debugging)
    print(f"Found {len(urls)} mirror URLs for {platform.system()} {platform.machine()}")
    
    return urls


# Helper function to test mirror connectivity (useful for debugging)
async def test_mirror(mirror: Mirror) -> dict:
    """Test if a mirror URL is reachable."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.head(mirror.url)
            return {
                "url": mirror.url,
                "reachable": response.status_code < 400,
                "status_code": response.status_code,
                "size": response.headers.get("content-length", "unknown"),
                "description": mirror.description,
            }
    except Exception as e:
        return {
            "url": mirror.url,
            "reachable": False,
            "error": str(e),
            "description": mirror.description,
        }