# Cross-compilation and multi-arch runtime settings.
#
# This file handles two scenarios:
#
# 1. Multi-arch runtimes (CROSS_TRIPLE without CROSS_COMPILER_TRIPLE):
#    Native builds that also build compiler-rt for a second architecture,
#    so the toolchain supports cross-compiled sanitizer builds.
#
# 2. Cross-compilation (CROSS_TRIPLE with CROSS_COMPILER_TRIPLE):
#    Building LLVM targeting a different architecture, including runtimes
#    for both host and target.
#
# Variables set by build-llvm.py via -D arguments:
#   CROSS_TRIPLE                - Target triple (LLVM-normalized)
#   CROSS_SYSROOT               (optional) - Sysroot path
#   CROSS_COMPILER_TRIPLE       (cross-compilation only) - Compiler target triple
#   CROSS_PROCESSOR             (cross-compilation only) - CMAKE_SYSTEM_PROCESSOR
#   CROSS_SYSTEM_NAME           (cross-compilation only, optional) - CMAKE_SYSTEM_NAME
#   CROSS_OSX_ARCHITECTURES     (cross-compilation only, optional) - macOS arch override

# --- Cross-architecture runtime targets ---
# Build compiler-rt builtins and runtimes for both host and target architectures.
# macOS is excluded: Darwin builds both architectures via universal builds.
# Skipped when tools are disabled: the runtimes build depends on clang targets.

if(DEFINED CROSS_TRIPLE AND NOT DEFINED CROSS_OSX_ARCHITECTURES
        AND (NOT DEFINED LLVM_INCLUDE_TOOLS OR LLVM_INCLUDE_TOOLS))
    if(DEFINED CROSS_COMPILER_TRIPLE)
        # Cross build: only build runtimes for the explicit cross target.
        # "default" would redundantly target the same architecture and fails
        # because LLVM's ExternalProject overrides the linker flags.
        set(LLVM_BUILTIN_TARGETS "${CROSS_TRIPLE}" CACHE STRING "")
        set(LLVM_RUNTIME_TARGETS "${CROSS_TRIPLE}" CACHE STRING "")
    else()
        # Native build with multi-arch runtimes: build for both host and cross.
        set(LLVM_BUILTIN_TARGETS "default;${CROSS_TRIPLE}" CACHE STRING "")
        set(LLVM_RUNTIME_TARGETS "default;${CROSS_TRIPLE}" CACHE STRING "")
    endif()

    if(DEFINED CROSS_SYSROOT)
        set(BUILTINS_${CROSS_TRIPLE}_CMAKE_SYSROOT "${CROSS_SYSROOT}" CACHE PATH "")
        set(RUNTIMES_${CROSS_TRIPLE}_CMAKE_SYSROOT "${CROSS_SYSROOT}" CACHE PATH "")
    endif()

    # Use lld for cross-arch runtimes — the host system linker may not
    # support the target architecture.
    set(RUNTIMES_${CROSS_TRIPLE}_CMAKE_SHARED_LINKER_FLAGS "-fuse-ld=lld" CACHE STRING "")
    set(RUNTIMES_${CROSS_TRIPLE}_CMAKE_EXE_LINKER_FLAGS "-fuse-ld=lld" CACHE STRING "")
endif()

# --- Cross-compilation settings ---
# Configure the main build to target a different architecture.

if(DEFINED CROSS_COMPILER_TRIPLE)
    set(CMAKE_SYSTEM_PROCESSOR "${CROSS_PROCESSOR}" CACHE STRING "")
    set(CMAKE_C_COMPILER_TARGET "${CROSS_COMPILER_TRIPLE}" CACHE STRING "")
    set(CMAKE_CXX_COMPILER_TARGET "${CROSS_COMPILER_TRIPLE}" CACHE STRING "")

    set(LLVM_HOST_TRIPLE "${CROSS_TRIPLE}" CACHE STRING "")
    set(LLVM_NATIVE_TOOL_DIR "${TOOLCHAIN_BIN_DIR}" CACHE PATH "")

    if(DEFINED CROSS_SYSTEM_NAME)
        set(CMAKE_SYSTEM_NAME "${CROSS_SYSTEM_NAME}" CACHE STRING "")
    endif()

    if(DEFINED CROSS_SYSROOT)
        set(CMAKE_SYSROOT "${CROSS_SYSROOT}" CACHE PATH "")
        # Prevent find_program from searching the sysroot for host tools.
        # CMake normally sets this automatically in cross-compilation mode, but
        # linux-to-linux cross builds have the same CMAKE_SYSTEM_NAME on both
        # host and target, so CMake doesn't detect cross-compilation.
        set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER CACHE STRING "")
    endif()

    if(DEFINED CROSS_OSX_ARCHITECTURES)
        set(CMAKE_OSX_ARCHITECTURES "${CROSS_OSX_ARCHITECTURES}" CACHE STRING "")
    endif()
endif()
