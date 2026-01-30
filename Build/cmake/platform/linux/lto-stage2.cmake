# Linux-specific LTO Stage 2 build settings.
# Requires lto-stage2-common.cmake to be included first.

# Use clang/clang++ from stage 1
set(CMAKE_C_COMPILER "${STAGE1_BIN_DIR}/clang" CACHE FILEPATH "")
set(CMAKE_CXX_COMPILER "${STAGE1_BIN_DIR}/clang++" CACHE FILEPATH "")
set(CMAKE_AR "${STAGE1_BIN_DIR}/llvm-ar" CACHE FILEPATH "")
set(CMAKE_RANLIB "${STAGE1_BIN_DIR}/llvm-ranlib" CACHE FILEPATH "")
