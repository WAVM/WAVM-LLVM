# Builds LLVM with ThinLTO.

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
    llvm-tblgen
    clang-tblgen
    llvm-profdata
    llvm-cov
    builtins
    runtimes
    CACHE STRING "")
