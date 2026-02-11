# Windows toolchain settings: use clang-cl from TOOLCHAIN_BIN_DIR.
# Requires TOOLCHAIN_BIN_DIR to be set before including this file.
# FORCE is needed to override CMake's auto-detected MSVC.

set(CMAKE_C_COMPILER "${TOOLCHAIN_BIN_DIR}/clang-cl.exe" CACHE FILEPATH "" FORCE)
set(CMAKE_CXX_COMPILER "${TOOLCHAIN_BIN_DIR}/clang-cl.exe" CACHE FILEPATH "" FORCE)
set(CMAKE_AR "${TOOLCHAIN_BIN_DIR}/llvm-lib.exe" CACHE FILEPATH "" FORCE)
set(CMAKE_LINKER "${TOOLCHAIN_BIN_DIR}/lld-link.exe" CACHE FILEPATH "" FORCE)
