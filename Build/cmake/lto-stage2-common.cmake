# LTO Stage 2 build settings.
# Builds LLVM with LTO using the toolchain from Stage 1.
# Requires STAGE1_BIN_DIR to be set to the Stage 1 bin directory.

if(NOT DEFINED STAGE1_BIN_DIR)
    message(FATAL_ERROR "STAGE1_BIN_DIR must be set to the Stage 1 bin directory")
endif()

set(CMAKE_BUILD_TYPE Release CACHE STRING "")
set(LLVM_ENABLE_PROJECTS "clang;lld" CACHE STRING "")
set(LLVM_ENABLE_RUNTIMES "compiler-rt" CACHE STRING "")
set(LLVM_ENABLE_LTO Thin CACHE STRING "")
set(LLVM_ENABLE_LLD ON CACHE BOOL "")

# Build toolchain components plus LLVM libraries and clang-format for distribution.
set(LLVM_DISTRIBUTION_COMPONENTS
    clang
    clang-resource-headers
    lld
    llvm-ar
    llvm-ranlib
    llvm-libtool-darwin
    llvm-lib
    llvm-headers
    llvm-libraries
    cmake-exports
    clang-format
    builtins
    runtimes
    CACHE STRING "")
