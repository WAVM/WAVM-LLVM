# LTO Stage 1 build settings.
# Builds the toolchain (clang, lld, llvm-ar, etc.) without LTO.

set(CMAKE_BUILD_TYPE Release CACHE STRING "")
set(LLVM_ENABLE_PROJECTS "clang;lld" CACHE STRING "")
