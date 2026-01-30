# Windows-specific LTO Stage 2 build settings.
# Requires lto-stage2-common.cmake to be included first.

# Use clang-cl from stage 1 (FORCE needed to override CMake's auto-detected MSVC)
set(CMAKE_C_COMPILER "${STAGE1_BIN_DIR}/clang-cl.exe" CACHE FILEPATH "" FORCE)
set(CMAKE_CXX_COMPILER "${STAGE1_BIN_DIR}/clang-cl.exe" CACHE FILEPATH "" FORCE)

# Use llvm-lib for static libraries (Windows equivalent of ar)
set(CMAKE_AR "${STAGE1_BIN_DIR}/llvm-lib.exe" CACHE FILEPATH "" FORCE)

# Use lld-link for linking
set(CMAKE_LINKER "${STAGE1_BIN_DIR}/lld-link.exe" CACHE FILEPATH "" FORCE)
