# Internal Hybrid Plan (The Invisible Turbo)

## 1) Accelerate validation and data (Rust under the hood)
- ✅ Use `pydantic==2.9.1` built with Rust.
- ✅ Replace `pandas` with `polars` in `requirements.txt` for faster processing.
- ✅ Make `orjson` the default serializer in FastAPI instead of `json`.

## 2) Real-time nervous system (Go)
- ⚪ TODO: Build a Go microservice to manage WebSockets (chat/notifications) and hook it to Redis to receive signals from FastAPI and broadcast in real time.

## 3) ONNX intelligence engine
- ⚪ TODO: Export the `bert-base-arabertv02` model used in `amenhotep.py` to ONNX and run it via ONNX Runtime instead of PyTorch to improve response time.

## 4) Offload heavy computation to Rust
- ⚪ TODO: Implement heavy computational functions in `app/modules/social/economy_service.py` with Rust (PyO3/maturin), build a native Python extension, and call it from the service.
