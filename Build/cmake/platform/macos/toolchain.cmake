# macOS toolchain settings: use clang/clang++ from TOOLCHAIN_BIN_DIR.
# Requires TOOLCHAIN_BIN_DIR to be set before including this file.

set(CMAKE_C_COMPILER "${TOOLCHAIN_BIN_DIR}/clang" CACHE FILEPATH "")
set(CMAKE_CXX_COMPILER "${TOOLCHAIN_BIN_DIR}/clang++" CACHE FILEPATH "")
set(CMAKE_AR "${TOOLCHAIN_BIN_DIR}/llvm-ar" CACHE FILEPATH "")
set(CMAKE_RANLIB "${TOOLCHAIN_BIN_DIR}/llvm-ranlib" CACHE FILEPATH "")

# macOS uses libtool instead of ar for static libraries.
set(CMAKE_LIBTOOL "${TOOLCHAIN_BIN_DIR}/llvm-libtool-darwin" CACHE FILEPATH "")

# Use lld (ld64 flavor) from the toolchain.
set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
