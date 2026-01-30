# Windows-specific LLVM build settings.
# CMake defaults to MSVC when vcvarsall.bat environment is set up.

# Disable DIA SDK to avoid optional dependency.
set(LLVM_ENABLE_DIA_SDK OFF CACHE BOOL "")
