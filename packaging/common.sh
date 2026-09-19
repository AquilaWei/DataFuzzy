# Shared by build_appimage.sh and build_dmg.sh: third-party licenses + PyInstaller build.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(uv run --frozen python -c \
    "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

build_app() {
    uv run --frozen --group package packaging/licenses.py build/THIRD_PARTY_LICENSES.txt
    uv run --frozen --group package pyinstaller --noconfirm --clean \
        --distpath dist --workpath build/pyinstaller packaging/datafuzzy.spec
}

# Models are downloaded by the user, never shipped.
check_no_models() {
    if find "$@" \( -name '*.onnx' -o -name 'tokenizer.json' \) | grep .; then
        echo "error: model files found in the bundle" >&2
        exit 1
    fi
}
