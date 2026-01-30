# Linux-specific LLVM build settings.

# Use system Clang.
set(CMAKE_C_COMPILER clang CACHE FILEPATH "")
set(CMAKE_CXX_COMPILER clang++ CACHE FILEPATH "")

# Hide symbols by default to reduce binary size.
set(CMAKE_C_FLAGS "-fvisibility=hidden" CACHE STRING "")
set(CMAKE_CXX_FLAGS "-fvisibility=hidden" CACHE STRING "")
