# LTO Stage 1 build settings.
# Builds the toolchain (clang, lld, llvm-ar, etc.) without LTO.

set(CMAKE_BUILD_TYPE Release CACHE STRING "")
set(LLVM_ENABLE_PROJECTS "clang;lld" CACHE STRING "")

# Only build/install the minimal toolchain needed to compile stage 2.
set(LLVM_DISTRIBUTION_COMPONENTS
    clang
    clang-resource-headers
    lld
    llvm-ar
    llvm-ranlib
    llvm-libtool-darwin
    llvm-lib
    CACHE STRING "")
