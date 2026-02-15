# LTO Stage 1 build settings.
# Builds the toolchain (clang, lld, llvm-ar, etc.) without LTO.

set(CMAKE_BUILD_TYPE Release CACHE STRING "")
set(LLVM_ENABLE_PROJECTS "clang;clang-tools-extra;lld" CACHE STRING "")
set(LLVM_ENABLE_RUNTIMES "compiler-rt" CACHE STRING "")

# Build/install the toolchain plus compiler-rt runtimes (needed for sanitizer builds).
set(LLVM_DISTRIBUTION_COMPONENTS
    clang
    clang-resource-headers
    lld
    llvm-ar
    llvm-ranlib
    llvm-libtool-darwin
    llvm-lib
    llvm-tblgen
    clang-tblgen
    builtins
    runtimes
    CACHE STRING "")
