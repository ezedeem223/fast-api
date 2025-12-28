# app/ai_chat/amenhotep.py

"""Amenhotep AI chat with ONNX acceleration and embedding cache.

Behavior:
- Prefers ONNXRuntime when an exported model exists; falls back to PyTorch otherwise.
- Caches embeddings with TTL and max-size eviction to avoid recomputation.
- Loads/saves a lightweight knowledge base from disk for quick responses.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional dependency
    ort = None

from app.core.config import settings


class AmenhotepAI:
    """
    Transformer-based assistant tailored for Arabic queries.

    Prefers ONNXRuntime for embeddings when an exported model is present,
    gracefully falling back to PyTorch generation otherwise. Embeddings are
    cached with TTL and size bounds to avoid repeated computation for the
    same prompts.
    """

    def __init__(
        self,
        *,
        onnx_path: Optional[str] = None,
        cache_ttl: int = 3600,
        cache_max_size: int = 256,
    ):
        huggingface_token = settings.HUGGINGFACE_API_TOKEN
        self.model_name = "aubmindlab/bert-base-arabertv02"
        self.onnx_path = onnx_path or os.getenv(
            "AMENHOTEP_ONNX_PATH", "data/amenhotep/amenhotep.onnx"
        )
        self.cache_ttl = cache_ttl
        self.cache_max_size = cache_max_size
        self._embedding_cache: Dict[str, tuple[list, float]] = {}

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, token=huggingface_token, use_fast=True
        )

        # ONNX first, then PyTorch fallback
        self.onnx_session = None
        self.use_onnx = False
        if ort and os.path.exists(self.onnx_path):
            try:
                self.onnx_session = ort.InferenceSession(
                    self.onnx_path,
                    providers=["CPUExecutionProvider"],
                )
                self.use_onnx = True
            except Exception:
                self.onnx_session = None
                self.use_onnx = False

        if not self.use_onnx:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                token=huggingface_token,
                device_map="auto" if torch.cuda.is_available() else None,
            )
        else:
            self.model = None

        self.qa_pipeline = pipeline(
            "question-answering",
            model=self.model_name,
            tokenizer=self.tokenizer,
            device=0 if torch.cuda.is_available() else -1,
        )

        os.makedirs("data/amenhotep", exist_ok=True)
        self.knowledge_base = self._load_knowledge_base()
        self.welcome_message = self._get_welcome_message()
        self.session_context = {}

    async def generate_response(self, message: str, user_id: int = 0) -> str:
        """Backward-compatible alias used by tests."""
        return await self.get_response(user_id=user_id, message=message)

    async def get_response(self, user_id: int, message: str) -> str:
        """
        Generate a response based on user input by leveraging the session context,
        the knowledge base, and the language model.
        """
        try:
            # Update conversation history for the user
            if user_id not in self.session_context:
                self.session_context[user_id] = []
            self.session_context[user_id].append({"role": "user", "content": message})

            # Check if the input message matches any topic in the knowledge base
            for category in self.knowledge_base:
                for topic, content in self.knowledge_base[category].items():
                    if topic.lower() in message.lower():
                        if isinstance(content, dict):
                            response = " ".join(content.values())
                        elif isinstance(content, list):
                            response = ", ".join(content)
                        else:
                            response = str(content)
                        break
                else:
                    continue
                break
            else:
                # Ensure embeddings are cached (reused for repeated text).
                _ = self._get_cached_embedding(message)

                inputs = self.tokenizer.encode(
                    message
                    + " ".join(
                        [m["content"] for m in self.session_context[user_id][-3:]]
                    ),
                    return_tensors="pt",
                    max_length=512,
                    truncation=True,
                )

                outputs = self._generate_with_model(inputs)
                response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

            formatted_response = self._format_royal_response(response)

            self.session_context[user_id].append(
                {"role": "assistant", "content": formatted_response}
            )

            if len(self.session_context[user_id]) > 10:
                self.session_context[user_id] = self.session_context[user_id][-10:]

            return formatted_response

        except Exception as e:
            print(f"Error generating response: {e}")
            return "Sorry, there was an error processing your question. Could you please rephrase it?"

    def _load_knowledge_base(self) -> dict:
        """Load the knowledge base from a JSON file or return defaults."""
        knowledge_file = "data/amenhotep/knowledge_base.json"
        try:
            if os.path.exists(knowledge_file):
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading knowledge base: {e}")

        return {
            "general": {
                "Amenhotep III": {
                    "info": "I am Amenhotep III, ninth pharaoh of the 18th dynasty of ancient Egypt (c. 1388-1351 BCE).",
                    "achievements": "My era saw unprecedented prosperity in arts and architecture, including the famed Colossi of Memnon.",
                    "politics": "I pursued successful diplomacy and maintained peace through alliances and political marriages.",
                },
                "daily_life": {
                    "agriculture": "The Nile was the backbone of ancient Egyptian life, with annual floods enabling agriculture.",
                    "food": "Diets included bread, beer, vegetables, fish, and meat on special occasions.",
                    "professions": "Society included scribes, farmers, artisans, priests, soldiers, and merchants.",
                },
            },
            "religion": {
                "gods": ["Ra", "Osiris", "Isis", "Horus", "Anubis", "Thoth"],
                "rituals": "Religious rituals were a core part of daily life.",
                "temples": "Temples served as key religious, administrative, and economic centers.",
            },
        }

    def _save_knowledge_base(self):
        """Save the updated knowledge base to a JSON file."""
        try:
            with open("data/amenhotep/knowledge_base.json", "w", encoding="utf-8") as f:
                json.dump(self.knowledge_base, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving knowledge base: {e}")

    def _get_welcome_message(self) -> str:
        """Return a detailed welcome message in Arabic."""
        return """
        Welcome to the court of Amenhotep III, the great pharaoh of Egypt's golden age.

        I am here to share the wisdom and history of ancient Egypt and to answer your questions about:
        - Egyptian civilization and its achievements
        - Daily life along the Nile
        - Religious beliefs and rituals
        - Arts and architecture of my era
        - Politics and diplomacy in my reign

        Ask your questions, and I will share from the treasury of Egyptian knowledge.
        """

    def _format_royal_response(self, response: str) -> str:
        """Format the generated response by adding royal prefixes and suffixes."""
        from random import choice

        royal_prefixes = [
            "My child",
            "Listen closely",
            "Allow me to tell you",
            "Know this",
            "As the sages say",
        ]

        royal_suffixes = [
            "This is what the gods have taught us",
            "So it was in my reign",
            "This is the wisdom of the pharaohs",
            "As our scribes carved on temple walls",
        ]

        response = f"{choice(royal_prefixes)}, {response}"
        if not any(suffix in response for suffix in royal_suffixes):
            response = f"{response}. {choice(royal_suffixes)}."
        return response

    def expand_knowledge_base(self, new_knowledge: dict):
        """Expand the current knowledge base with new information and save it."""
        for category, content in new_knowledge.items():
            if category in self.knowledge_base:
                self.knowledge_base[category].update(content)
            else:
                self.knowledge_base[category] = content

        self._save_knowledge_base()

    def get_session_summary(self, user_id: int) -> dict:
        """
        Provide a summary of the conversation session, including the number of messages
        and topics discussed.
        """
        if user_id not in self.session_context:
            return {"message_count": 0, "topics": []}

        messages = self.session_context[user_id]
        topics = set()
        for msg in messages:
            for category in self.knowledge_base:
                for topic in self.knowledge_base[category]:
                    if topic.lower() in msg["content"].lower():
                        topics.add(topic)
        return {"message_count": len(messages), "topics": list(topics)}

    def _generate_with_model(self, inputs):
        """Generate tokens using PyTorch (fallback when ONNX is not used)."""
        if self.model is None:
            raise RuntimeError("PyTorch model is not initialized")
        outputs = self.model.generate(
            inputs,
            max_length=200,
            num_return_sequences=1,
            no_repeat_ngram_size=2,
            do_sample=True,
            top_k=50,
            top_p=0.95,
            temperature=0.7,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        return outputs

    def _get_cached_embedding(self, text: str) -> list:
        """Return cached embedding with TTL and size bounds."""
        now = time.time()
        cached = self._embedding_cache.get(text)
        if cached:
            embedding, ts = cached
            if now - ts <= self.cache_ttl:
                return embedding

        embedding = self._embed_text(text)
        if len(self._embedding_cache) >= self.cache_max_size:
            oldest_key = min(self._embedding_cache.items(), key=lambda item: item[1][1])[0]
            self._embedding_cache.pop(oldest_key, None)
        self._embedding_cache[text] = (embedding, now)
        return embedding

    def _embed_text(self, text: str) -> list:
        """Compute embeddings using ONNX when available, else PyTorch."""
        if self.use_onnx and self.onnx_session:
            inputs = self.tokenizer(
                text,
                return_tensors="np",
                truncation=True,
                max_length=128,
            )
            outputs = self.onnx_session.run(None, dict(inputs))
            return outputs[0][0].tolist()

        if not self.model:
            raise RuntimeError("Neither ONNX nor PyTorch model is available")

        with torch.no_grad():
            encoded = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=128,
            )
            outputs = self.model(**encoded)
            hidden = outputs.last_hidden_state.mean(dim=1).squeeze(0)
            return hidden.cpu().tolist()

    def export_to_onnx(self, output_path: Optional[str] = None) -> str:
        """Export the underlying model to ONNX for faster inference."""
        if not output_path:
            output_path = self.onnx_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        model = getattr(self, "model", None) or AutoModelForCausalLM.from_pretrained(
            self.model_name
        )
        dummy = self.tokenizer(
            "export",
            return_tensors="pt",
            truncation=True,
            max_length=32,
        )
        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy.get("attention_mask")),
            output_path,
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
            },
            opset_version=14,
        )
        return output_path
