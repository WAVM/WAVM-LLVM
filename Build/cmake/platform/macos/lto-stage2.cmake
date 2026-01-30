# macOS-specific LTO Stage 2 build settings.
# Requires lto-stage2-common.cmake to be included first.

# Use clang/clang++ from stage 1
set(CMAKE_C_COMPILER "${STAGE1_BIN_DIR}/clang" CACHE FILEPATH "")
set(CMAKE_CXX_COMPILER "${STAGE1_BIN_DIR}/clang++" CACHE FILEPATH "")
set(CMAKE_AR "${STAGE1_BIN_DIR}/llvm-ar" CACHE FILEPATH "")
set(CMAKE_RANLIB "${STAGE1_BIN_DIR}/llvm-ranlib" CACHE FILEPATH "")

# macOS uses libtool instead of ar for static libraries.
set(CMAKE_LIBTOOL "${STAGE1_BIN_DIR}/llvm-libtool-darwin" CACHE FILEPATH "")

# Exclude x86_64h from Darwin builds.
# Apple's lipo considers x86_64 and x86_64h as the same architecture, causing
# "can't be in the same fat output file" errors when building universal binaries.
set(DARWIN_osx_ARCHS "arm64;x86_64" CACHE STRING "")
