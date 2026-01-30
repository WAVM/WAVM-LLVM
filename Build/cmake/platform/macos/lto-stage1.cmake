# macOS-specific LTO Stage 1 build settings.

# Disable libLTO.dylib to avoid conflicts with Xcode's linker.
set(LLVM_TOOL_LTO_BUILD OFF CACHE BOOL "")
