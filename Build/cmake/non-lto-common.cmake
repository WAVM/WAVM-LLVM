# Common settings for non-LTO configurations.
# These configs build LLVM as a library only, without tools like clang.

set(LLVM_INCLUDE_TOOLS OFF CACHE BOOL "")

# Only install LLVM development files.
set(LLVM_DISTRIBUTION_COMPONENTS
    llvm-headers
    llvm-libraries
    cmake-exports
    CACHE STRING "")
