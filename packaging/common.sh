# Shared by build_appimage.sh and build_dmg.sh: third-party licenses + PyInstaller build.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(uv run --frozen python -c \
    "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
# The app's name has one definition: APP_NAME in src/datafuzzy/ot/__init__.py.
APP_NAME=$(uv run --frozen python -c "from datafuzzy.ot import APP_NAME; print(APP_NAME)")
APP_SLUG=$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]')

build_app() {
    uv run --frozen --group package packaging/licenses.py build/THIRD_PARTY_LICENSES.txt
    uv run --frozen --group package pyinstaller --noconfirm --clean \
        --distpath dist --workpath build/pyinstaller packaging/theranote.spec
}

# Models are downloaded by the user, never shipped.
check_no_models() {
    if find "$@" \( -name '*.onnx' -o -name '*.onnx_data' -o -name 'tokenizer.json' \) | grep .; then
        echo "error: model files found in the bundle" >&2
        exit 1
    fi
}
