"""DataFuzzy: local-first text obfuscation with reversible codes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("datafuzzy")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"
