#!/usr/bin/env python3
"""
Build LLVM from source with WAVM-specific configurations.

This script handles:
  - Cloning LLVM at the commit specified in LLVM_COMMIT
  - Applying patches from the patches/ directory
  - Configuring and building with platform-specific cmake cache files
  - Two-stage LTO builds (stage 1 toolchain + LTO stage 2)
  - Auto-building the stage 1 toolchain for all non-stage1 configs
  - Cross-compilation to different architectures

The script supports incremental builds:
  - Skips cloning if LLVM is already at the correct commit
  - Skips entirely if build marker shows correct commit/config
  - Lets ninja handle incremental compilation
  - Use --clean to force a full rebuild

Directory structure (supports multiple configs in same work-dir):
  work-dir/
    llvm-project/           # Shared LLVM source
    build-Debug/            # Config-specific build dirs
    build-Debug-arm64/      # Cross-compiled build dirs
    build-stage1/           # Stage 1 toolchain (auto-built for all non-stage1 configs)
    build-LTO/
    install-Debug-x64/      # Config+arch-specific install dirs (unless --install-dir)
    install-Debug-arm64/    # Cross-compiled install dirs
    install-LTO-x64/

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

  # Cross-compile for arm64 (stage 1 toolchain is auto-built)
  python3 build-llvm.py --config Debug --work-dir . --install-dir ./install \
    --target-arch arm64
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def unbuffered_print(msg: str) -> None:
    """Print a message and flush stdout for real-time output in CI."""
    print(msg)
    sys.stdout.flush()


SCRIPT_DIR = Path(__file__).parent.resolve()
MARKER_FILE = ".wavm-llvm-build"

# Bump this to invalidate all existing builds (e.g., when build logic changes)
BUILD_SCRIPT_VERSION = 9

# Cross-compilation target definitions: (platform, arch) -> cmake -D variables.
CROSS_TARGETS: dict[tuple[str, str], dict[str, str]] = {
    ("linux", "arm64"): {
        "CROSS_COMPILER_TRIPLE": "aarch64-linux-gnu",
        "CROSS_TRIPLE": "aarch64-linux-gnu",
        "CROSS_PROCESSOR": "aarch64",
        "CROSS_SYSTEM_NAME": "Linux",
    },
    ("windows", "arm64"): {
        "CROSS_COMPILER_TRIPLE": "arm64-pc-windows-msvc",
        "CROSS_TRIPLE": "aarch64-pc-windows-msvc",
        "CROSS_PROCESSOR": "ARM64",
        "CROSS_SYSTEM_NAME": "Windows",
    },
    ("macos", "x64"): {
        "CROSS_COMPILER_TRIPLE": "x86_64-apple-macos",
        "CROSS_TRIPLE": "x86_64-apple-darwin",
        "CROSS_PROCESSOR": "x86_64",
        "CROSS_OSX_ARCHITECTURES": "x86_64",
    },
}


def get_runtime_cross_triple(plat: str, host_arch: str) -> Optional[str]:
    """Get the triple for cross-architecture runtime builds.

    For configs that build compiler-rt (stage1, LTO), this enables building
    runtimes for both the host and cross-compilation target architectures,
    so the toolchain can be used for cross-compiled sanitizer builds.

    Returns the triple string, or None if not needed (macOS handles both
    architectures via Darwin universal builds).
    """
    if plat == "macos":
        return None
    other_arch = "arm64" if host_arch == "x64" else "x64"
    cross = CROSS_TARGETS.get((plat, other_arch))
    return cross["CROSS_TRIPLE"] if cross else None


def run_cmd(cmd: list[str], cwd: Optional[Path] = None, check: bool = True,
            capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command, printing it first."""
    unbuffered_print(f"+ {' '.join(cmd)}")
    if capture:
        return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd, check=check)  # type: ignore[return-value]


def get_llvm_commit() -> str:
    """Read the LLVM commit from LLVM_COMMIT file."""
    commit_file = SCRIPT_DIR / "LLVM_COMMIT"
    if not commit_file.exists():
        raise RuntimeError(f"LLVM_COMMIT file not found at {commit_file}")
    return commit_file.read_text().strip()


def get_patches_hash() -> str:
    """Compute a hash of all patches to detect changes."""
    patches_dir = SCRIPT_DIR / "patches"
    if not patches_dir.exists():
        return ""

    hasher = hashlib.sha256()
    for patch in sorted(patches_dir.glob("*.patch")):
        hasher.update(patch.name.encode())
        hasher.update(patch.read_bytes())
    return hasher.hexdigest()[:16]


def detect_platform() -> str:
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


def detect_host_arch() -> str:
    """Detect the host architecture, normalized to x64/arm64."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {machine}")


def get_llvm_head_commit(llvm_dir: Path) -> Optional[str]:
    """Get the current HEAD commit of the LLVM checkout."""
    if not llvm_dir.exists():
        return None
    try:
        result = run_cmd(["git", "rev-parse", "HEAD"], cwd=llvm_dir, capture=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def cmake_path(path: Path) -> str:
    """Convert a path to CMake-safe format (forward slashes).

    On Windows, backslashes in paths are interpreted as escape sequences
    by CMake, so we need to convert them to forward slashes.
    """
    return str(path).replace("\\", "/")


@dataclass
class CMakeConfig:
    """CMake configuration: cache files and -D variables that define what gets built.

    This is the single representation of a cmake configuration, used for both
    build invalidation (via cmake_hash) and command-line generation (via cmake_args).
    """
    cache_files: list[Path] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)

    def cmake_hash(self) -> str:
        """Compute a hash of the configuration for build invalidation."""
        hasher = hashlib.sha256()
        for cache_file in self.cache_files:
            hasher.update(f"file:{cache_file.name}\n".encode())
            if cache_file.exists():
                hasher.update(cache_file.read_bytes())
            else:
                hasher.update(b"<missing>")
        for key in sorted(self.variables):
            hasher.update(f"var:{key}={self.variables[key]}\n".encode())
        return hasher.hexdigest()[:16]

    def cmake_args(self) -> list[str]:
        """Return -D and -C arguments for cmake, with -D before -C.

        -D variables must precede -C cache files because the cache files
        reference the variables.
        """
        args: list[str] = []
        for key, value in self.variables.items():
            args.append(f"-D{key}={value}")
        for cache_file in self.cache_files:
            args.extend(["-C", cmake_path(cache_file)])
        return args


def get_cmake_config(plat: str, config: str, toolchain_bin_dir: Optional[Path] = None,
                      cross_vars: Optional[dict[str, str]] = None) -> CMakeConfig:
    """Build the complete CMake configuration for a build.

    This is the single source of truth for cmake configuration.
    The returned CMakeConfig drives both hashing and command-line generation.

    Args:
        plat: Target platform (linux, macos, windows)
        config: Build configuration
        toolchain_bin_dir: Path to stage 1 toolchain bin directory
        cross_vars: Dict of -D variables for cross.cmake (cross-compilation
            or multi-arch runtime targets)
    """
    cmake_dir = SCRIPT_DIR / "Build" / "cmake"
    cache_files: list[Path] = []
    variables: dict[str, str] = {}

    # Common cache file for all builds
    cache_files.append(cmake_dir / "common.cmake")

    # Platform common cache file (always included)
    cache_files.append(cmake_dir / "platform" / plat / "common.cmake")

    # Non-LTO library-only configs share additional common settings
    if config in ("Debug", "Checked", "RelWithDebInfo", "Sanitized"):
        cache_files.append(cmake_dir / "non-lto-common.cmake")

    # Config-specific cache file
    config_file = cmake_dir / "config" / f"{config}.cmake"
    if not config_file.exists():
        raise RuntimeError(f"Unknown config: {config} (no {config_file})")
    cache_files.append(config_file)

    # Platform-specific config override (e.g., platform/macos/stage1.cmake)
    plat_config = cmake_dir / "platform" / plat / f"{config}.cmake"
    if plat_config.exists():
        cache_files.append(plat_config)

    # Stage 1 toolchain (used for all non-stage1 configs)
    if toolchain_bin_dir:
        toolchain_file = cmake_dir / "platform" / plat / "toolchain.cmake"
        if toolchain_file.exists():
            cache_files.append(toolchain_file)
        variables["TOOLCHAIN_BIN_DIR"] = cmake_path(toolchain_bin_dir)

    # Cross-compilation and/or multi-arch runtime targets
    if cross_vars:
        variables.update(cross_vars)
        cache_files.append(cmake_dir / "cross.cmake")

    return CMakeConfig(cache_files=cache_files, variables=variables)


def check_build_marker(install_dir: Path, llvm_commit: str, patches_hash: str,
                        cmake_hash: str, config: str, plat: str) -> bool:
    """Check if the install directory has a matching build marker.

    Logs the reason if the marker doesn't match.
    """
    marker_path = install_dir / MARKER_FILE
    if not marker_path.exists():
        unbuffered_print(f"Rebuild needed: no build marker at {marker_path}")
        return False

    try:
        marker = json.loads(marker_path.read_text())
    except json.JSONDecodeError as e:
        unbuffered_print(f"Rebuild needed: invalid build marker ({e})")
        return False

    mismatches: list[str] = []
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
        unbuffered_print(f"Rebuild needed: {', '.join(mismatches)}")
        return False

    return True


def write_build_marker(install_dir: Path, llvm_commit: str, patches_hash: str,
                        cmake_hash: str, config: str, plat: str) -> None:
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


def clone_or_update_llvm(work_dir: Path, llvm_commit: str) -> Path:
    """Clone LLVM or update to the correct commit if needed."""
    llvm_dir = work_dir / "llvm-project"

    current_commit = get_llvm_head_commit(llvm_dir)
    if current_commit == llvm_commit:
        unbuffered_print(f"LLVM already at commit {llvm_commit[:12]}, skipping clone")
        return llvm_dir

    if llvm_dir.exists():
        unbuffered_print(f"LLVM at wrong commit ({current_commit[:12] if current_commit else 'unknown'}), removing...")
        shutil.rmtree(llvm_dir)

    unbuffered_print(f"\n=== Cloning LLVM (commit: {llvm_commit[:12]}) ===")
    run_cmd(["git", "clone", "--depth=1", "https://github.com/llvm/llvm-project.git"], cwd=work_dir)
    run_cmd(["git", "fetch", "--depth=1", "origin", llvm_commit], cwd=llvm_dir)
    run_cmd(["git", "checkout", llvm_commit], cwd=llvm_dir)

    return llvm_dir


def apply_patches(llvm_dir: Path) -> None:
    """Apply patches from the patches/ directory.

    Always reverts llvm-project to clean state before applying patches.
    This is robust against interrupted builds and patch changes.
    """
    patches_dir = SCRIPT_DIR / "patches"
    if not patches_dir.exists():
        unbuffered_print("No patches directory found, skipping patches")
        return

    patches = sorted(patches_dir.glob("*.patch"))
    if not patches:
        unbuffered_print("No patches found, skipping")
        return

    # Always revert to clean state first - this handles:
    # - Patches that were partially applied before an abort
    # - Patches that changed since last build
    # - Multiple configs sharing the same llvm-project
    unbuffered_print("\n=== Reverting llvm-project to clean state ===")
    run_cmd(["git", "checkout", "--", "."], cwd=llvm_dir)
    run_cmd(["git", "clean", "-fd"], cwd=llvm_dir)

    unbuffered_print(f"\n=== Applying {len(patches)} patches ===")
    for patch in patches:
        unbuffered_print(f"Applying: {patch.name}")
        run_cmd(["git", "apply", str(patch)], cwd=llvm_dir)


def configure_cmake(llvm_dir: Path, build_dir: Path, config: str,
                     cmake_config: CMakeConfig,
                     install_dir: Optional[Path] = None) -> None:
    """Configure LLVM with cmake."""
    unbuffered_print(f"\n=== Configuring {config} ===")

    cmake_cmd = [
        "cmake",
        "--fresh",
        "-S", cmake_path(llvm_dir / "llvm"),
        "-B", cmake_path(build_dir),
        "-G", "Ninja",
    ]
    if install_dir:
        cmake_cmd.append(f"-DCMAKE_INSTALL_PREFIX={cmake_path(install_dir)}")
    cmake_cmd.extend(cmake_config.cmake_args())
    run_cmd(cmake_cmd)


def ensure_stage1_toolchain(work_dir: Path, llvm_dir: Path, plat: str, clean: bool,
                             llvm_commit: str, patches_hash: str,
                             cmake_config: CMakeConfig) -> Path:
    """Build the stage 1 toolchain if needed, return its bin directory.

    Unlike other configs, stage 1 is not installed — we use the build directory
    directly. This avoids issues with llvm-min-tblgen (needed for cross-compilation)
    not having an install target in LLVM.
    """
    build_dir = work_dir / "build-stage1"
    cmake_hash = cmake_config.cmake_hash()

    if clean and build_dir.exists():
        unbuffered_print(f"Removing {build_dir}")
        shutil.rmtree(build_dir)

    if check_build_marker(build_dir, llvm_commit, patches_hash, cmake_hash, "stage1", plat):
        unbuffered_print("\n=== Stage 1 already built, skipping ===")
    else:
        configure_cmake(llvm_dir, build_dir, "stage1", cmake_config)

        unbuffered_print("\n=== Building Stage 1 ===")
        run_cmd(["ninja", "-C", str(build_dir), "distribution"])

        write_build_marker(build_dir, llvm_commit, patches_hash, cmake_hash, "stage1", plat)

    return build_dir / "bin"


def build_single_stage(work_dir: Path, llvm_dir: Path, plat: str, config: str,
                        install_dir: Path, clean: bool, cmake_config: CMakeConfig,
                        cross_arch: Optional[str] = None) -> None:
    """Build single-stage configuration."""
    # Append arch to build dir name when cross-compiling to avoid collisions
    build_suffix = f"-{cross_arch}" if cross_arch else ""
    build_dir = work_dir / f"build-{config}{build_suffix}"

    if clean:
        for d in [build_dir, install_dir]:
            if d.exists():
                unbuffered_print(f"Removing {d}")
                shutil.rmtree(d)

    configure_cmake(llvm_dir, build_dir, config, cmake_config, install_dir=install_dir)

    unbuffered_print(f"\n=== Building {config}{' (' + cross_arch + ')' if cross_arch else ''} ===")
    run_cmd(["ninja", "-C", str(build_dir), "install-distribution"])


def test_toolchain(install_dir: Path, plat: str) -> None:
    """Test the built toolchain by compiling a simple program."""
    unbuffered_print("\n=== Testing toolchain ===")

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

    unbuffered_print("Toolchain test passed!")


def main() -> None:
    host_arch = detect_host_arch()

    parser = argparse.ArgumentParser(description="Build LLVM from source")
    parser.add_argument("--config", required=True,
                        choices=["LTO", "stage1", "RelWithDebInfo", "Debug", "Checked", "Sanitized"],
                        help="Build configuration (stage1 builds only the bootstrap toolchain)")
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="Working directory for build")
    parser.add_argument("--install-dir", type=Path,
                        help="Installation directory (default: work-dir/install-<config>)")
    parser.add_argument("--clean", action="store_true",
                        help="Force clean rebuild (remove build and install dirs)")
    parser.add_argument("--test", action="store_true",
                        help="Test the built toolchain")
    parser.add_argument("--target-arch", choices=["x64", "arm64"],
                        help=f"Target architecture (default: {host_arch}; enables cross-compilation when different)")
    parser.add_argument("--cross-sysroot", type=Path,
                        help="Sysroot path for cross-compilation and cross-architecture runtime builds")

    args = parser.parse_args()

    work_dir: Path = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    plat = detect_platform()
    target_arch: str = args.target_arch or host_arch

    # Determine if cross-compiling
    cross_arch: Optional[str] = target_arch if target_arch != host_arch else None
    if cross_arch:
        cross_target = CROSS_TARGETS.get((plat, target_arch))
        if not cross_target:
            raise RuntimeError(f"No cross-compilation target defined for ({plat}, {target_arch})")
        cross_target = dict(cross_target)  # copy before modifying
        if args.cross_sysroot:
            cross_target["CROSS_SYSROOT"] = str(args.cross_sysroot.resolve())
        elif plat == "linux":
            parser.error("--cross-sysroot is required for Linux cross-compilation")
    else:
        cross_target = None

    # Determine multi-arch runtime targets for compiler-rt builds.
    # This ensures the toolchain has sanitizer runtimes for both architectures.
    # Computed unconditionally so the stage1 cmake hash is the same whether
    # invoked from a native or cross-compiled build.
    runtime_cross_vars: Optional[dict[str, str]] = None
    triple = get_runtime_cross_triple(plat, host_arch)
    if triple:
        if plat == "linux" and not args.cross_sysroot:
            # Linux needs a sysroot for cross-arch runtimes; without one, skip them
            pass
        else:
            runtime_cross_vars = {"CROSS_TRIPLE": triple}
            if args.cross_sysroot:
                runtime_cross_vars["CROSS_SYSROOT"] = str(args.cross_sysroot.resolve())

    llvm_commit = get_llvm_commit()
    patches_hash = get_patches_hash()

    # Build cmake configs.
    # Stage1 always gets runtime_cross_vars (for multi-arch compiler-rt).
    stage1_config = get_cmake_config(plat, "stage1", cross_vars=runtime_cross_vars)

    if args.config == "stage1":
        cmake_hash = stage1_config.cmake_hash()
        install_dir: Optional[Path] = None
    else:
        # Determine cross variables for the build
        if cross_arch:
            build_cross_vars = cross_target
        elif args.config == "LTO":
            # Native LTO builds compiler-rt, so it needs multi-arch runtimes too
            build_cross_vars = runtime_cross_vars
        else:
            build_cross_vars = None

        toolchain_bin_dir = work_dir / "build-stage1" / "bin"
        build_config = get_cmake_config(plat, args.config,
                                         toolchain_bin_dir=toolchain_bin_dir,
                                         cross_vars=build_cross_vars)
        cmake_hash = build_config.cmake_hash()
        install_dir = args.install_dir.resolve() if args.install_dir else work_dir / f"install-{args.config}-{target_arch}"

    unbuffered_print(f"Platform: {plat}")
    unbuffered_print(f"Host arch: {host_arch}")
    unbuffered_print(f"Target arch: {target_arch}")
    if cross_arch:
        unbuffered_print(f"Cross-compiling: {host_arch} -> {cross_arch}")
    unbuffered_print(f"Config: {args.config}")
    unbuffered_print(f"Work directory: {work_dir}")
    if install_dir:
        unbuffered_print(f"Install directory: {install_dir}")
    unbuffered_print(f"LLVM commit: {llvm_commit[:12]}")
    if patches_hash:
        unbuffered_print(f"Patches hash: {patches_hash}")
    unbuffered_print(f"CMake hash: {cmake_hash}")

    # Check if already built with same config (skip for stage1 which has no install dir)
    if install_dir and not args.clean and check_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, args.config, plat):
        unbuffered_print("\n=== Already built, skipping (use --clean to rebuild) ===")
        if args.test:
            test_toolchain(install_dir, plat)
        return

    # Clone or update LLVM
    llvm_dir = clone_or_update_llvm(work_dir, llvm_commit)

    # Apply patches
    apply_patches(llvm_dir)

    # Build
    if args.config == "stage1":
        ensure_stage1_toolchain(work_dir, llvm_dir, plat, args.clean, llvm_commit, patches_hash,
                                 stage1_config)
    else:
        ensure_stage1_toolchain(work_dir, llvm_dir, plat, args.clean, llvm_commit, patches_hash,
                                 stage1_config)
        assert install_dir is not None
        build_single_stage(work_dir, llvm_dir, plat, args.config, install_dir, args.clean,
                            build_config, cross_arch=cross_arch)

    # Write marker for future incremental builds (skip for stage1)
    if install_dir:
        write_build_marker(install_dir, llvm_commit, patches_hash, cmake_hash, args.config, plat)

        if args.test:
            if cross_arch:
                unbuffered_print("Skipping toolchain test (cross-compilation)")
            else:
                test_toolchain(install_dir, plat)

        unbuffered_print("\n=== Build complete ===")
        unbuffered_print(f"Installation: {install_dir}")
    else:
        unbuffered_print("\n=== Build complete ===")
        unbuffered_print(f"Stage 1 toolchain: {work_dir / 'build-stage1' / 'bin'}")


if __name__ == "__main__":
    main()
