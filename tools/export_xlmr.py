# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#     "optimum[onnxruntime]==2.1.0",
#     "onnx==1.23.2",
#     "onnxruntime==1.30.0",
#     "transformers==4.57.6",
#     "torch==2.14.1",
#     "sentencepiece==0.2.2",  # the tokenizer is converted from sentencepiece.bpe.model
#     "protobuf==7.36.2",
# ]
# ///
"""Convert Davlan/xlm-roberta-large-ner-hrl to int8 ONNX for the "mixed-xlmr-ner" model.

    uv run tools/export_xlmr.py [out_dir]

Upstream only ships PyTorch weights, so we publish our conversion as assets of the
GitHub release `models-v1`; then run tools/update_manifest.py. Needs ~5 GB of disk.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = "Davlan/xlm-roberta-large-ner-hrl"
REVISION = "1f929ffad9b7353f9c84b0b3f579fc3bb0b3685e"
PREFIX = "xlm-roberta-large-ner-hrl"


def main() -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from optimum.exporters.onnx import main_export
    from transformers import AutoTokenizer

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "models/export")
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        main_export(REPO, tmp, task="token-classification", revision=REVISION)
        # main_export leaves out tokenizer.json when given a revision.
        AutoTokenizer.from_pretrained(REPO, revision=REVISION).save_pretrained(tmp)
        # fp32 is 2.2 GB; int8 weights are 561 MB with no loss on our name tests.
        quantize_dynamic(f"{tmp}/model.onnx", out / f"{PREFIX}-int8.onnx",
                         weight_type=QuantType.QInt8)
        shutil.copy(f"{tmp}/tokenizer.json", out / f"{PREFIX}-tokenizer.json")
        shutil.copy(f"{tmp}/config.json", out / f"{PREFIX}-config.json")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
