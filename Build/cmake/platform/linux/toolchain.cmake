# Linux toolchain settings: use clang/clang++ from TOOLCHAIN_BIN_DIR.
# Requires TOOLCHAIN_BIN_DIR to be set before including this file.

set(CMAKE_C_COMPILER "${TOOLCHAIN_BIN_DIR}/clang" CACHE FILEPATH "" FORCE)
set(CMAKE_CXX_COMPILER "${TOOLCHAIN_BIN_DIR}/clang++" CACHE FILEPATH "" FORCE)
set(CMAKE_AR "${TOOLCHAIN_BIN_DIR}/llvm-ar" CACHE FILEPATH "" FORCE)
set(CMAKE_RANLIB "${TOOLCHAIN_BIN_DIR}/llvm-ranlib" CACHE FILEPATH "" FORCE)

# Use lld from the toolchain. The host GNU ld may not support the target
# architecture when cross-compiling.
set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "-fuse-ld=lld" CACHE STRING "")
