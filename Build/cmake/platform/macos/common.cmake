# macOS-specific build settings.

set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "")

# Exclude x86_64h from Darwin builds.
# Apple's lipo considers x86_64 and x86_64h as the same architecture, causing
# "can't be in the same fat output file" errors when building universal binaries.
set(DARWIN_osx_ARCHS "arm64;x86_64" CACHE STRING "")
