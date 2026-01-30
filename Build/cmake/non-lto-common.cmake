# Common settings for non-LTO configurations.
# These configs build LLVM as a library only, without tools like clang.

set(LLVM_INCLUDE_TOOLS OFF CACHE BOOL "")
