#!/usr/bin/env bash
# Run the test suite in a throwaway linux/arm64 container capped at 8 GB RAM / 4 CPUs,
# approximating an M2 MacBook with 8 GB. The container and image are removed afterwards.
# Needs QEMU user emulation on x86 hosts (Fedora: `sudo dnf install qemu-user-static`).
set -euo pipefail
cd "$(dirname "$0")/.."

ENGINE="${ENGINE:-docker}"
IMAGE="datafuzzy-test-arm64:$$"
trap '"$ENGINE" rmi -f "$IMAGE" >/dev/null 2>&1 || true' EXIT

"$ENGINE" build --platform linux/arm64 -f tools/Dockerfile.test -t "$IMAGE" .
"$ENGINE" run --rm --platform linux/arm64 --memory=8g --cpus=4 "$IMAGE" \
    sh -c 'uname -m && uv run pytest "$@"' _ "$@"
