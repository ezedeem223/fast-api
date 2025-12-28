"""
Utility to export the Amenhotep (bert-base-arabertv02) model to ONNX for faster inference.

Usage:
    python scripts/export_amenhotep_onnx.py --out data/amenhotep/amenhotep.onnx

Requires: torch, transformers, onnx, onnxruntime.
"""

import argparse
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer


def export_model(output_path: str) -> None:
    model_name = "aubmindlab/bert-base-arabertv02"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    dummy = tokenizer(
        "test sentence for onnx export",
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=32,
    )
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"], dummy["token_type_ids"]),
            output_path,
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["last_hidden_state", "pooler_output"],
            dynamic_axes={"input_ids": {0: "batch", 1: "seq"}},
            opset_version=14,
        )
    print(f"Exported ONNX model to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/amenhotep/amenhotep.onnx")
    args = parser.parse_args()
    export_model(args.out)


if __name__ == "__main__":
    main()
