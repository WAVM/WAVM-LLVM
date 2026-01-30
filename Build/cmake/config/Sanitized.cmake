# Sanitized configuration settings (for ASAN/UBSAN builds of WAVM).

set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "")
set(LLVM_ENABLE_ASSERTIONS ON CACHE BOOL "")
set(LLVM_USE_SANITIZER "Address;Undefined" CACHE STRING "")
set(LLVM_USE_SANITIZE_COVERAGE ON CACHE BOOL "")
