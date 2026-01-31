#!/usr/bin/env python3
"""
Build LLVM from source with WAVM-specific configurations.

This script handles:
  - Cloning LLVM at the commit specified in LLVM_COMMIT
  - Applying patches from the patches/ directory
  - Configuring and building with platform-specific cmake cache files
  - Two-stage LTO bootstrap builds for Linux and macOS

The script supports incremental builds:
  - Skips cloning if LLVM is already at the correct commit
  - Skips entirely if install marker shows correct commit/config
  - Lets ninja handle incremental compilation
  - Use --clean to force a full rebuild

Directory structure (supports multiple configs in same work-dir):
  work-dir/
    llvm-project/           # Shared LLVM source
    build-Debug/            # Config-specific build dirs
    build-LTO-stage1/
    build-LTO-stage2/
    install-Debug/          # Config-specific install dirs (unless --install-dir)
    install-LTO/

Usage:
  # Build Debug config
  python3 build-llvm.py --config Debug --work-dir ~/build/llvm

  # Build multiple configs in same work-dir
  python3 build-llvm.py --config Debug --work-dir ~/build/llvm
  python3 build-llvm.py --config LTO --work-dir ~/build/llvm

  # Force clean rebuild
  python3 build-llvm.py --config Debug --work-dir ~/build/llvm --clean

  # Custom install directory (for GHA compatibility)
  python3 build-llvm.py --config LTO --work-dir . --install-dir ./install
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from enum import Enum, auto
from pathlib import Path

# Force line-buffered stdout for real-time output in CI
sys.stdout.reconfigure(line_buffering=True)


class LTOStages(Enum):
    STAGE1_ONLY = auto()
    ALL = auto()


SCRIPT_DIR = Path(__file__).parent.resolve()
MARKER_FILE = ".wavm-llvm-build"

# Bump this to invalidate all existing builds (e.g., when build logic changes)
BUILD_SCRIPT_VERSION = 1


def run_cmd(cmd, cwd=None, check=True, capture=False):
    """Run a command, printing it first."""
    print(f"+ {' '.join(str(c) for c in cmd)}")
    if capture:
        return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd, check=check)


def get_llvm_commit():
    """Read the LLVM commit from LLVM_COMMIT file."""
    commit_file = SCRIPT_DIR / "LLVM_COMMIT"
    if not commit_file.exists():
        raise RuntimeError(f"LLVM_COMMIT file not found at {commit_file}")
    return commit_file.read_text().strip()


def get_patches_hash():
    """Compute a hash of all patches to detect changes."""
    patches_dir = SCRIPT_DIR / "patches"
    if not patches_dir.exists():
        return ""

    hasher = hashlib.sha256()
    for patch in sorted(patches_dir.glob("*.patch")):
        hasher.update(patch.name.encode())
        hasher.update(patch.read_bytes())
    return hasher.hexdigest()[:16]


def detect_platform():
    """Detect the current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def get_llvm_head_commit(llvm_dir):
    """Get the current HEAD commit of the LLVM checkout."""
    if not llvm_dir.exists():
        return None
    try:
        result = run_cmd(["git", "rev-parse", "HEAD"], cwd=llvm_dir, capture=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def check_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, config, plat):
    """Check if the install directory has a matching build marker.

    Logs the reason if the marker doesn't match.
    """
    marker_path = install_dir / MARKER_FILE
    if not marker_path.exists():
        print(f"Rebuild needed: no build marker at {marker_path}")
        return False

    try:
        marker = json.loads(marker_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Rebuild needed: invalid build marker ({e})")
        return False

    mismatches = []
    if marker.get("build_script_version") != BUILD_SCRIPT_VERSION:
        mismatches.append(f"build script version: {marker.get('build_script_version', '<missing>')} -> {BUILD_SCRIPT_VERSION}")
    if marker.get("commit") != llvm_commit:
        mismatches.append(f"commit: {marker.get('commit', '<missing>')[:12]} -> {llvm_commit[:12]}")
    if marker.get("patches") != patches_hash:
        mismatches.append(f"patches: {marker.get('patches', '<missing>')} -> {patches_hash or '<none>'}")
    if marker.get("cmake") != cmake_hash:
        mismatches.append(f"cmake: {marker.get('cmake', '<missing>')} -> {cmake_hash}")
    if marker.get("config") != config:
        mismatches.append(f"config: {marker.get('config', '<missing>')} -> {config}")
    if marker.get("platform") != plat:
        mismatches.append(f"platform: {marker.get('platform', '<missing>')} -> {plat}")

    if mismatches:
        print(f"Rebuild needed: {', '.join(mismatches)}")
        return False

    return True


def write_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, config, plat):
    """Write a build marker to the install directory."""
    marker_path = install_dir / MARKER_FILE
    marker = {
        "build_script_version": BUILD_SCRIPT_VERSION,
        "commit": llvm_commit,
        "patches": patches_hash,
        "cmake": cmake_hash,
        "config": config,
        "platform": plat,
    }
    marker_path.write_text(json.dumps(marker, indent=2))


def clone_or_update_llvm(work_dir, llvm_commit):
    """Clone LLVM or update to the correct commit if needed."""
    llvm_dir = work_dir / "llvm-project"

    current_commit = get_llvm_head_commit(llvm_dir)
    if current_commit == llvm_commit:
        print(f"LLVM already at commit {llvm_commit[:12]}, skipping clone")
        return llvm_dir

    if llvm_dir.exists():
        print(f"LLVM at wrong commit ({current_commit[:12] if current_commit else 'unknown'}), removing...")
        shutil.rmtree(llvm_dir)

    print(f"\n=== Cloning LLVM (commit: {llvm_commit[:12]}) ===")
    run_cmd(["git", "clone", "--depth=1", "https://github.com/llvm/llvm-project.git"], cwd=work_dir)
    run_cmd(["git", "fetch", "--depth=1", "origin", llvm_commit], cwd=llvm_dir)
    run_cmd(["git", "checkout", llvm_commit], cwd=llvm_dir)

    return llvm_dir


def apply_patches(llvm_dir):
    """Apply patches from the patches/ directory.

    Always reverts llvm-project to clean state before applying patches.
    This is robust against interrupted builds and patch changes.
    """
    patches_dir = SCRIPT_DIR / "patches"
    if not patches_dir.exists():
        print("No patches directory found, skipping patches")
        return

    patches = sorted(patches_dir.glob("*.patch"))
    if not patches:
        print("No patches found, skipping")
        return

    # Always revert to clean state first - this handles:
    # - Patches that were partially applied before an abort
    # - Patches that changed since last build
    # - Multiple configs sharing the same llvm-project
    print(f"\n=== Reverting llvm-project to clean state ===")
    run_cmd(["git", "checkout", "--", "."], cwd=llvm_dir)
    run_cmd(["git", "clean", "-fd"], cwd=llvm_dir)

    print(f"\n=== Applying {len(patches)} patches ===")
    for patch in patches:
        print(f"Applying: {patch.name}")
        run_cmd(["git", "apply", str(patch)], cwd=llvm_dir)


def get_cmake_config(plat, config, stage=None):
    """Get cmake cache files for a build.

    This is the single source of truth for cmake configuration.
    Used by both configure_cmake() and get_cmake_hash().
    """
    cmake_dir = SCRIPT_DIR / "Build" / "cmake"
    cache_files = []

    # Common cache file for all builds
    cache_files.append(cmake_dir / "common.cmake")

    # Platform common cache file (always included)
    cache_files.append(cmake_dir / "platform" / plat / "common.cmake")

    # Config-specific cache files
    if config == "LTO":
        # Two-stage LTO build (all platforms)
        cache_files.append(cmake_dir / f"lto-stage{stage}-common.cmake")
        # Add platform-specific LTO stage file if it exists
        stage_file = cmake_dir / "platform" / plat / f"lto-stage{stage}.cmake"
        if stage_file.exists():
            cache_files.append(stage_file)
    elif config == "LTO-stage1":
        # Stage 1 only (for split builds)
        cache_files.append(cmake_dir / "lto-stage1-common.cmake")
        stage_file = cmake_dir / "platform" / plat / "lto-stage1.cmake"
        if stage_file.exists():
            cache_files.append(stage_file)
    elif config in ("RelWithDebInfo", "Debug", "Checked", "Sanitized"):
        cache_files.append(cmake_dir / "non-lto-common.cmake")
        cache_files.append(cmake_dir / "config" / f"{config}.cmake")
    else:
        raise RuntimeError(f"Unknown config: {config}")

    return cache_files


def get_cmake_hash(plat, config):
    """Compute hash of all cmake configuration for this config/platform."""
    hasher = hashlib.sha256()

    # Collect all cache files across all stages, deduplicating with dict
    seen_files = {}
    stages = [1, 2] if config == "LTO" else [None]
    for stage in stages:
        for f in get_cmake_config(plat, config, stage):
            seen_files[f] = None

    # Hash cache file contents
    for cache_file in seen_files:
        hasher.update(f"file:{cache_file.name}\n".encode())
        if cache_file.exists():
            hasher.update(cache_file.read_bytes())
        else:
            hasher.update(b"<missing>")

    return hasher.hexdigest()[:16]


def cmake_path(path):
    """Convert a path to CMake-safe format (forward slashes).

    On Windows, backslashes in paths are interpreted as escape sequences
    by CMake, so we need to convert them to forward slashes.
    """
    return str(path).replace("\\", "/")


def configure_cmake(llvm_dir, build_dir, install_dir, plat, config, stage=None, stage1_bin_dir=None):
    """Configure LLVM with cmake."""
    print(f"\n=== Configuring {'Stage ' + str(stage) if stage else config} ===")

    cmake_cmd = [
        "cmake",
        "--fresh",
        "-S", cmake_path(llvm_dir / "llvm"),
        "-B", cmake_path(build_dir),
        "-G", "Ninja",
        f"-DCMAKE_INSTALL_PREFIX={cmake_path(install_dir)}",
    ]

    # Stage 2 needs STAGE1_BIN_DIR - must come BEFORE cache files that reference it
    if stage == 2 and stage1_bin_dir:
        cmake_cmd.append(f"-DSTAGE1_BIN_DIR={cmake_path(stage1_bin_dir)}")

    # Add cache files
    for cache_file in get_cmake_config(plat, config, stage):
        cmake_cmd.extend(["-C", cmake_path(cache_file)])

    run_cmd(cmake_cmd)


def build_ninja(build_dir, targets=None):
    """Build with ninja."""
    cmd = ["ninja", "-C", str(build_dir)]
    if targets:
        cmd.extend(targets)
    else:
        cmd.append("install")
    run_cmd(cmd)


def build_lto(work_dir, llvm_dir, plat, install_stage2, clean, stages, llvm_commit, patches_hash):
    """Build LTO configuration (two-stage bootstrap).

    stages controls which stages to build:
      - STAGE1_ONLY: Only build the bootstrap toolchain
      - ALL: Build both stages (skipping stage 1 if already present)
    """
    build_stage1 = work_dir / "build-LTO-stage1"
    install_stage1 = work_dir / "install-LTO-stage1"
    build_stage2 = work_dir / "build-LTO-stage2"

    # Compute cmake hash for stage 1 only
    stage1_cmake_hash = get_cmake_hash(plat, "LTO-stage1")

    if clean:
        dirs_to_clean = [build_stage1, install_stage1]
        if stages == LTOStages.ALL:
            dirs_to_clean.extend([build_stage2, install_stage2])
        for d in dirs_to_clean:
            if d and d.exists():
                print(f"Removing {d}")
                shutil.rmtree(d)

    # Stage 1: Build and install toolchain (skip if marker indicates it's already built)
    stage1_valid = check_build_marker(
        install_stage1, llvm_commit, patches_hash, stage1_cmake_hash, "LTO-stage1", plat
    )

    if stage1_valid:
        print(f"\n=== Stage 1 already built, skipping ===")
    else:
        configure_cmake(llvm_dir, build_stage1, install_stage1, plat, "LTO", stage=1)

        print(f"\n=== Building Stage 1 ===")
        build_ninja(build_stage1)

        # Write marker for stage 1
        write_build_marker(install_stage1, llvm_commit, patches_hash, stage1_cmake_hash, "LTO-stage1", plat)

    if stages == LTOStages.STAGE1_ONLY:
        return

    # Stage 2: Build with LTO using stage 1 toolchain
    stage1_bin = install_stage1 / "bin"
    configure_cmake(llvm_dir, build_stage2, install_stage2, plat, "LTO", stage=2, stage1_bin_dir=stage1_bin)

    print("\n=== Building Stage 2 ===")
    build_ninja(build_stage2)


def build_single_stage(work_dir, llvm_dir, plat, config, install_dir, clean):
    """Build single-stage configuration."""
    build_dir = work_dir / f"build-{config}"

    if clean:
        for d in [build_dir, install_dir]:
            if d.exists():
                print(f"Removing {d}")
                shutil.rmtree(d)

    configure_cmake(llvm_dir, build_dir, install_dir, plat, config)

    print(f"\n=== Building {config} ===")
    build_ninja(build_dir)


def test_toolchain(install_dir, plat):
    """Test the built toolchain by compiling a simple program."""
    print("\n=== Testing toolchain ===")

    test_c = install_dir / "test.cpp"
    test_exe = install_dir / ("test.exe" if plat == "windows" else "test")

    test_c.write_text('''#include <stdio.h>
#include <vector>
int main() {
    std::vector<int> v = {1, 2, 3};
    printf("Toolchain test passed! Vector size: %zu\\n", v.size());
    return 0;
}
''')

    clang = install_dir / "bin" / ("clang++.exe" if plat == "windows" else "clang++")

    compile_cmd = [str(clang), "-o", str(test_exe), str(test_c)]

    if plat == "macos":
        sysroot = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        compile_cmd.extend(["-isysroot", sysroot])

    run_cmd(compile_cmd)
    run_cmd([str(test_exe)])

    test_c.unlink()
    test_exe.unlink()

    print("Toolchain test passed!")


def main():
    parser = argparse.ArgumentParser(description="Build LLVM from source")
    parser.add_argument("--config", required=True,
                        choices=["LTO", "LTO-stage1", "RelWithDebInfo", "Debug", "Checked", "Sanitized"],
                        help="Build configuration (LTO-stage1 builds only the bootstrap toolchain)")
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="Working directory for build")
    parser.add_argument("--install-dir", type=Path,
                        help="Installation directory (default: work-dir/install-<config>)")
    parser.add_argument("--platform", choices=["linux", "macos", "windows"],
                        help="Target platform (auto-detected if not specified)")
    parser.add_argument("--clean", action="store_true",
                        help="Force clean rebuild (remove build and install dirs)")
    parser.add_argument("--test", action="store_true",
                        help="Test the built toolchain")

    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    plat = args.platform or detect_platform()
    llvm_commit = get_llvm_commit()
    patches_hash = get_patches_hash()
    cmake_hash = get_cmake_hash(plat, args.config)

    # LTO-stage1 doesn't produce an install directory
    if args.config == "LTO-stage1":
        install_dir = None
    else:
        install_dir = args.install_dir.resolve() if args.install_dir else work_dir / f"install-{args.config}"

    print(f"Platform: {plat}")
    print(f"Config: {args.config}")
    print(f"Work directory: {work_dir}")
    if install_dir:
        print(f"Install directory: {install_dir}")
    print(f"LLVM commit: {llvm_commit[:12]}")
    if patches_hash:
        print(f"Patches hash: {patches_hash}")
    print(f"CMake hash: {cmake_hash}")

    # Check if already built with same config (skip for LTO-stage1 which has no install dir)
    if install_dir and not args.clean and check_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, args.config, plat):
        print(f"\n=== Already built, skipping (use --clean to rebuild) ===")
        if args.test:
            test_toolchain(install_dir, plat)
        return

    # Clone or update LLVM
    llvm_dir = clone_or_update_llvm(work_dir, llvm_commit)

    # Apply patches
    apply_patches(llvm_dir)

    # Build
    if args.config == "LTO-stage1":
        build_lto(work_dir, llvm_dir, plat, None, args.clean, LTOStages.STAGE1_ONLY, llvm_commit, patches_hash)
    elif args.config == "LTO":
        build_lto(work_dir, llvm_dir, plat, install_dir, args.clean, LTOStages.ALL, llvm_commit, patches_hash)
    else:
        build_single_stage(work_dir, llvm_dir, plat, args.config, install_dir, args.clean)

    # Write marker for future incremental builds (skip for LTO-stage1)
    if install_dir:
        write_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, args.config, plat)

        if args.test:
            test_toolchain(install_dir, plat)

        print(f"\n=== Build complete ===")
        print(f"Installation: {install_dir}")
    else:
        print(f"\n=== Build complete ===")
        print(f"Stage 1 toolchain: {work_dir / 'install-LTO-stage1' / 'bin'}")


if __name__ == "__main__":
    main()
