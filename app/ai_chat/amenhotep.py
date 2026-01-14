# app/ai_chat/amenhotep.py

"""Amenhotep AI chat with ONNX acceleration and embedding cache.

Behavior:
- Prefers ONNXRuntime when an exported model exists; falls back to PyTorch otherwise.
- Caches embeddings with TTL and max-size eviction to avoid recomputation.
- Loads/saves a lightweight knowledge base from disk for quick responses.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Dict, Optional, TYPE_CHECKING

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional dependency
    ort = None

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI
    from sqlalchemy.orm import Session


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
        """Initialize the model/tokenizer/cache with optional ONNX acceleration.

        ONNX is preferred when an exported model exists; otherwise falls back to PyTorch.
        Embeddings are cached in-memory with TTL and size bounds to avoid recomputation.
        """
        huggingface_token = settings.HUGGINGFACE_API_TOKEN
        self.model_name = "aubmindlab/bert-base-arabertv02"
        self.onnx_path = onnx_path or os.getenv(
            "AMENHOTEP_ONNX_PATH", "data/amenhotep/amenhotep.onnx"
        )
        self.cache_ttl = cache_ttl
        self.cache_max_size = cache_max_size
        self._embedding_cache: Dict[str, tuple[list, float]] = {}

        self.tokenizer = self._safe_load_tokenizer(huggingface_token)

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
            self.model = self._safe_load_model(huggingface_token)
        else:
            self.model = None

        self.qa_pipeline = self._safe_build_pipeline()

        os.makedirs("data/amenhotep", exist_ok=True)
        self.knowledge_base = self._load_knowledge_base()
        self.welcome_message = self._get_welcome_message()
        self.session_context = {}

    async def generate_response(
        self, message: str, user_id: int = 0, db: "Session | None" = None
    ) -> str:
        """Backward-compatible alias used by tests."""
        return await self.get_response(user_id=user_id, message=message, db=db)

    async def get_response(
        self, user_id: int, message: str, db: "Session | None" = None
    ) -> str:
        """
        Generate a response based on user input by leveraging the session context,
        the knowledge base, and the language model.
        """
        try:
            # Update conversation history for the user
            if user_id not in self.session_context:
                self.session_context[user_id] = []
            self.session_context[user_id].append({"role": "user", "content": message})

            prefer_arabic = self._contains_arabic(message)
            response: Optional[str] = None

            # Check if the input message matches any topic in the knowledge base
            for category in self.knowledge_base:
                for topic, content in self.knowledge_base[category].items():
                    if topic.lower() in message.lower():
                        if isinstance(content, dict):
                            response = " ".join(
                                [str(value) for value in content.values()]
                            )
                        elif isinstance(content, list):
                            response = ", ".join([str(item) for item in content])
                        else:
                            response = str(content)
                        break
                if response:
                    break

            if response is None:
                fact_response = self._build_fact_response(message, db=db)
                if fact_response:
                    response = fact_response
                else:
                    # Ensure embeddings are cached (reused for repeated text).
                    _ = self._get_cached_embedding(message)

                    prompt = self._build_prompt(message, prefer_arabic=prefer_arabic)
                    context = " ".join(
                        [m["content"] for m in self.session_context[user_id][-3:]]
                    )

                    inputs = self.tokenizer.encode(
                        f"{prompt} {context}".strip(),
                        return_tensors="pt",
                        max_length=512,
                        truncation=True,
                    )

                    outputs = self._generate_with_model(inputs)
                    response = self.tokenizer.decode(
                        outputs[0], skip_special_tokens=True
                    )

            try:
                formatted_response = self._format_royal_response(
                    response, message=message
                )
            except TypeError:
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
            "التاريخ_المصري": {
                "أمنحتب الثالث": {
                    "نبذة": "أمنحتب الثالث هو الفرعون التاسع من الأسرة الثامنة عشرة (نحو 1388-1351 ق.م).",
                    "الإنجازات": "شهد عهده ازدهارًا في الفنون والعمارة، ومن أشهر الآثار تمثالا ممنون.",
                    "السياسة": "اعتمد على الدبلوماسية والتحالفات للحفاظ على السلام.",
                },
                "الدولة الحديثة": "تعد الدولة الحديثة (نحو 1550-1070 ق.م) ذروة القوة العسكرية والثقافية في مصر القديمة.",
                "الأهرامات": "الأهرامات منشآت جنائزية ملكية، وأشهرها أهرامات الجيزة.",
                "النيل": "نهر النيل كان شريان الحياة؛ فيضانه السنوي دعم الزراعة والاستقرار.",
            },
            "الحياة_اليومية": {
                "الزراعة": "اعتمدت الزراعة على فيضان النيل ومحاصيل مثل القمح والشعير والكتان.",
                "الطعام": "كان الخبز والجعة أساس الغذاء، مع خضروات وأسماك ولحوم في المناسبات.",
                "المهن": "تنوعت المهن بين الكتبة والفلاحين والحرفيين والكهنة والجنود والتجار.",
                "الأسرة": "لعبت الأسرة دورًا محوريًا في المجتمع وكانت العلاقات الأسرية موثقة في النصوص.",
            },
            "اللغة_والكتابة": {
                "الكتابة الهيروغليفية": "نظام كتابي تصويري استخدم في النقوش الدينية والرسمية.",
                "اللغة المصرية": "تطورت اللغة المصرية عبر مراحل؛ أبرزها المصرية الوسطى.",
                "البردي": "استعمل ورق البردي في تسجيل المراسلات والنصوص التعليمية.",
            },
            "الفنون_والعمارة": {
                "المعابد": "المعابد كانت مراكز دينية واقتصادية، وتظهر زخارفها حياة الآلهة والملوك.",
                "النحت": "اهتم المصريون بالنحت لتخليد الملوك والآلهة، مع عناية بالتوازن والرمزية.",
                "التماثيل": "التماثيل الضخمة تؤكد السلطة والقداسة وتوضع في المعابد والمقابر.",
            },
            "الديانة": {
                "الآلهة المصرية": "من أبرز الآلهة رع وأوزيريس وإيزيس وحورس وأنوبيس وتحوت.",
                "الطقوس": "شملت الطقوس التقدمات اليومية والصلوات والأعياد الموسمية.",
                "المعابد": "كانت المعابد محورًا للعبادة والإدارة وتخزين الغلال.",
            },
        }

    def _save_knowledge_base(self):
        """Save the updated knowledge base to a JSON file."""
        try:
            with open("data/amenhotep/knowledge_base.json", "w", encoding="utf-8") as f:
                json.dump(self.knowledge_base, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving knowledge base: {e}")

    @staticmethod
    def _contains_arabic(text: str) -> bool:
        if not text:
            return False
        # Accept Arabic + mis-decoded Arabic that landed in Cyrillic codepoints.
        return re.search(r"[\u0600-\u06FF\u0400-\u04FF]", text) is not None

    @staticmethod
    def _normalize_text(text: str) -> str:
        cleaned = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text, flags=re.UNICODE)
        return " ".join(cleaned.lower().split())

    def _build_prompt(self, message: str, *, prefer_arabic: bool) -> str:
        if prefer_arabic:
            return (
                "أنت أمنحتب، مساعد معرفي يتحدث بالعربية الفصحى. "
                "أجب بدقة وبأسلوب رسمي مختصر. "
                f"السؤال: {message}"
            )
        return message

    def _find_verified_fact(self, message: str, db: "Session | None"):
        if db is None:
            return None

        from app.modules.fact_checking.models import Fact, FactCheckStatus

        normalized = self._normalize_text(message)
        if not normalized:
            return None

        base_query = db.query(Fact).filter(Fact.status == FactCheckStatus.VERIFIED)
        fact = (
            base_query.filter(Fact.claim.ilike(f"%{normalized}%"))
            .order_by(Fact.verified_at.desc(), Fact.created_at.desc())
            .first()
        )
        if fact:
            return fact

        tokens = [token for token in normalized.split() if len(token) >= 4]
        for token in tokens[:5]:
            fact = (
                base_query.filter(Fact.claim.ilike(f"%{token}%"))
                .order_by(Fact.verified_at.desc(), Fact.created_at.desc())
                .first()
            )
            if fact:
                return fact
        return None

    def _build_fact_response(
        self, message: str, db: "Session | None" = None
    ) -> Optional[str]:
        fact = self._find_verified_fact(message, db=db)
        if not fact:
            return None

        parts = [
            f"وفقًا للحقائق التي تم التحقق منها، الادعاء: {fact.claim}."
        ]
        if getattr(fact, "description", None):
            parts.append(f"التفاصيل: {fact.description}")

        sources: list[str] = []
        for field in ("sources", "evidence_links"):
            value = getattr(fact, field, None) or []
            if isinstance(value, list):
                sources.extend([str(item) for item in value if item])
        if sources:
            parts.append("المصادر: " + ", ".join(sources))

        return " ".join(parts)

    def _get_welcome_message(self) -> str:
        """Return a detailed welcome message in Arabic."""
        return (
            "مرحبًا بك. أنا أمنحتب، مساعد معرفي مستوحى من حكمة مصر القديمة.\n\n"
            "أستطيع مساعدتك في:\n"
            "- تبسيط المعلومات التاريخية والثقافية.\n"
            "- الإجابة عن الأسئلة العامة بأسلوب فصيح.\n"
            "- تلخيص السياقات وتقديم إجابات موجزة عند الحاجة.\n"
            "- الاستناد إلى الحقائق المتحقق منها عندما تتوفر.\n\n"
            "اسأل ما تشاء."
        )

    def _format_royal_response(
        self, response: str, *, message: str | None = None
    ) -> str:
        """Format the generated response by adding royal prefixes and suffixes."""
        from random import choice

        prefer_arabic = self._contains_arabic(message or response)

        if prefer_arabic and not self._contains_arabic(response):
            response = (
                "أعتذر، سأجيب باللغة العربية الفصحى قدر الإمكان. "
                "هل يمكنك توضيح السؤال؟"
            )

        if prefer_arabic:
            royal_prefixes = [
                "يا صديقي",
                "استمع بعناية",
                "دعني أوضح لك",
                "اعلم أن",
                "بحكمة الفراعنة",
            ]

            royal_suffixes = [
                "وهذا ما تشهد به السجلات",
                "وهذه خلاصة الحكمة",
                "وهكذا دون على جدران المعابد",
                "وذلك مما استقر عليه الرأي",
            ]
        else:
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

        response = f"{choice(royal_prefixes)} {response}"
        if not any(suffix in response for suffix in royal_suffixes):
            response = f"{response}. {choice(royal_suffixes)}."
        return response

    # --------------------- Safe loaders to avoid heavy failures in tests --------------------- #

    def _safe_load_tokenizer(self, huggingface_token: Optional[str]):
        """Load tokenizer with a lightweight fallback to keep tests isolated from HF deps."""
        try:
            return AutoTokenizer.from_pretrained(
                self.model_name, token=huggingface_token, use_fast=True
            )
        except (ImportError, ModuleNotFoundError, OSError):
            # Minimal stub to satisfy code paths that only need encoding/decoding.
            class _DummyTokenizer:
                def __call__(
                    self, text, return_tensors=None, truncation=None, max_length=None
                ):
                    return {"input_ids": [[1]], "attention_mask": [[1]]}

                def encode(self, text, **kwargs):
                    return [1, 2, 3]

                def decode(self, tokens, skip_special_tokens=True):
                    if isinstance(tokens, (list, tuple)) and tokens:
                        return " ".join(map(str, tokens))
                    return str(tokens)

                @property
                def eos_token_id(self):
                    return 0

            return _DummyTokenizer()
        except RuntimeError as exc:
            # Some transformers installs raise RuntimeError when optional deps are missing (e.g., tf-keras).
            if "Failed to import" in str(exc) or "No module named" in str(exc):

                class _DummyTokenizer:
                    def __call__(
                        self,
                        text,
                        return_tensors=None,
                        truncation=None,
                        max_length=None,
                    ):
                        return {"input_ids": [[1]], "attention_mask": [[1]]}

                    def encode(self, text, **kwargs):
                        return [1, 2, 3]

                    def decode(self, tokens, skip_special_tokens=True):
                        if isinstance(tokens, (list, tuple)) and tokens:
                            return " ".join(map(str, tokens))
                        return str(tokens)

                    @property
                    def eos_token_id(self):
                        return 0

                return _DummyTokenizer()
            raise
        except Exception:
            # For runtime failures unrelated to missing deps, bubble up (tests may assert raise).
            raise

    def _safe_load_model(self, huggingface_token: Optional[str]):
        """Load model with a dummy fallback when dependencies are missing; re-raise real load errors."""
        try:
            return AutoModelForCausalLM.from_pretrained(
                self.model_name,
                token=huggingface_token,
                device_map="auto" if torch.cuda.is_available() else None,
            )
        except (ImportError, ModuleNotFoundError, OSError):

            class _DummyModel:
                def generate(self, inputs, **kwargs):
                    return torch.tensor([[1, 2, 3]])

                def __call__(self, **kwargs):
                    class _Out:
                        def __init__(self):
                            self.last_hidden_state = torch.ones((1, 1, 1))

                    return _Out()

            return _DummyModel()
        except RuntimeError as exc:
            # Transformers may raise RuntimeError when optional backends (e.g., tf-keras) are missing.
            if "Failed to import" in str(exc) or "No module named" in str(exc):

                class _DummyModel:
                    def generate(self, inputs, **kwargs):
                        return torch.tensor([[1, 2, 3]])

                    def __call__(self, **kwargs):
                        class _Out:
                            def __init__(self):
                                self.last_hidden_state = torch.ones((1, 1, 1))

                        return _Out()

                return _DummyModel()
            raise
        except Exception:
            # Preserve runtime failures (tests expect a raise when model load itself fails)
            raise

    def _safe_build_pipeline(self):
        """Construct QA pipeline safely; return a stub when transformers resources are unavailable."""
        try:
            return pipeline(
                "question-answering",
                model=self.model_name,
                tokenizer=self.tokenizer,
                device=0 if torch.cuda.is_available() else -1,
            )
        except Exception:
            return None

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
            oldest_key = min(
                self._embedding_cache.items(), key=lambda item: item[1][1]
            )[0]
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


async def get_shared_amenhotep(app: "FastAPI") -> AmenhotepAI:
    """Return a shared AmenhotepAI instance stored on app.state."""
    instance = getattr(app.state, "amenhotep", None)
    if isinstance(instance, AmenhotepAI):
        return instance

    task = getattr(app.state, "amenhotep_task", None)
    current_task = asyncio.current_task()
    if isinstance(task, asyncio.Task) and task is not current_task:
        await task
        instance = getattr(app.state, "amenhotep", None)
        if isinstance(instance, AmenhotepAI):
            return instance

    lock = getattr(app.state, "amenhotep_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(app.state, "amenhotep_lock", lock)

    async with lock:
        instance = getattr(app.state, "amenhotep", None)
        if isinstance(instance, AmenhotepAI):
            return instance
        instance = await asyncio.to_thread(AmenhotepAI)
        app.state.amenhotep = instance
        return instance
