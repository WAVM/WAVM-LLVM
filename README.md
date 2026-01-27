# WAVM-LLVM

This repository provides pre-built LLVM binaries for [WAVM](https://github.com/WAVM/WAVM).

## Contents

- `LLVM_COMMIT` - Pinned LLVM commit hash to build
- `patches/` - WAVM-specific patches applied to LLVM before building
- `.github/workflows/build-llvm.yml` - GitHub Actions workflow

## How It Works

The CI workflow:
1. Clones llvm-project at the commit specified in `LLVM_COMMIT`
2. Applies patches from `patches/`
3. Builds LLVM in multiple configurations
4. Publishes pre-built binaries as GitHub Releases

## Configurations

| Config | Build Type | Includes | Notes |
|--------|------------|----------|-------|
| LTO | Release | LLVM + Clang + LLD + clang-format | Built with ThinLTO |
| RelWithDebInfo | RelWithDebInfo | LLVM only | |
| Debug | Debug | LLVM only | |
| Checked | RelWithDebInfo | LLVM only | LLVM_ENABLE_ASSERTIONS=ON |
| Sanitized | RelWithDebInfo | LLVM only | For ASAN/UBSAN builds |

## Platforms

- Linux x86_64 (built on manylinux_2_28, glibc 2.28+)
- Windows x86_64
- macOS ARM64

## Releases

Pre-built binaries are published as GitHub Releases. Each release includes:

- `llvm-{version}-linux-x64-{config}.tar.xz`
- `llvm-{version}-windows-x64-{config}.zip`
- `llvm-{version}-macos-arm64-{config}.tar.xz`

## Updating LLVM

To update to a new LLVM commit:

1. Update `LLVM_COMMIT` with the new commit hash
2. Update/add patches in `patches/` if needed
3. Push to the release branch
