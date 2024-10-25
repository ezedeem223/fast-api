# في ملف app/ai_chat/amenhotep.py

from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
import torch
from typing import List, Optional
import json
import os
from datetime import datetime
import aiohttp
from ..config import settings


class AmenhotepAI:
    def __init__(self):
        # تحميل نموذج أكبر وأكثر تخصصًا للغة العربية
        huggingface_token = settings.HUGGINGFACE_API_TOKEN
        self.model_name = "aubmindlab/bert-base-arabertv02"
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, token=huggingface_token, use_fast=True
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            token=huggingface_token,
            device_map="auto" if torch.cuda.is_available() else None,
        )

        # تحسين الإعدادات للحصول على إجابات أكثر دقة
        self.qa_pipeline = pipeline(
            "question-answering",
            model=self.model_name,
            tokenizer=self.tokenizer,
            device=0 if torch.cuda.is_available() else -1,
        )

        # التأكد من وجود مجلد البيانات
        os.makedirs("data/amenhotep", exist_ok=True)

        # تحميل أو إنشاء قاعدة المعرفة المتخصصة
        self.knowledge_base = self._load_knowledge_base()

        # تحسين رسالة الترحيب
        self.welcome_message = self._get_welcome_message()

        # إضافة سياق الجلسة
        self.session_context = {}

    def _load_knowledge_base(self) -> dict:
        """تحميل قاعدة المعرفة من ملف JSON أو إنشاء واحدة جديدة"""
        knowledge_file = "data/amenhotep/knowledge_base.json"
        try:
            if os.path.exists(knowledge_file):
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading knowledge base: {e}")

        # قاعدة معرفة افتراضية محسنة
        return {
            "عام": {
                "أمنحتب الثالث": {
                    "معلومات": "أنا أمنحتب الثالث، تاسع فراعنة الأسرة الثامنة عشرة في مصر القديمة. حكمت خلال العصر المصري الحديث، في الفترة من حوالي 1388 إلى 1351 قبل الميلاد.",
                    "إنجازات": "شهد عصري ازدهاراً غير مسبوق في الفنون والعمارة. أمرت ببناء العديد من المعابد والتماثيل، بما في ذلك تماثيل ممنون الشهيرة.",
                    "سياسة": "اتبعت سياسة دبلوماسية ناجحة وحافظت على السلام من خلال التحالفات والزيجات السياسية.",
                },
                "الحياة اليومية": {
                    "الزراعة": "كان نهر النيل محور الحياة المصرية القديمة، حيث اعتمد المصريون على فيضانه السنوي للزراعة.",
                    "الطعام": "كان النظام الغذائي يتكون من الخبز والجعة والخضروات والأسماك واللحوم في المناسبات الخاصة.",
                    "المهن": "كان المجتمع يضم كتبة ومزارعين وحرفيين وكهنة وجنود وتجار.",
                },
            },
            "الدين": {
                "آلهة": ["رع", "أوزيريس", "إيزيس", "حورس", "أنوبيس", "تحوت"],
                "طقوس": "كانت الطقوس الدينية جزءاً أساسياً من الحياة اليومية",
                "معابد": "كانت المعابد مراكز دينية وإدارية واقتصادية مهمة",
            },
        }

    def _save_knowledge_base(self):
        """حفظ قاعدة المعرفة المحدثة"""
        try:
            with open("data/amenhotep/knowledge_base.json", "w", encoding="utf-8") as f:
                json.dump(self.knowledge_base, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving knowledge base: {e}")

    def _get_welcome_message(self) -> str:
        """رسالة ترحيب أكثر تفصيلاً وشخصية"""
        return """
        مرحباً بك في حضرة الملك أمنحتب الثالث، فرعون مصر العظيم في عصرها الذهبي.

        أنا هنا لأشارك معك حكمة وتاريخ مصر القديمة، ولأجيب على استفساراتك عن:
        • الحضارة المصرية وإنجازاتها العظيمة
        • الحياة اليومية في مصر القديمة
        • المعتقدات الدينية والطقوس
        • الفنون والعمارة في عصري
        • السياسة والدبلوماسية في عهدي
        
        تفضل بطرح أسئلتك، وسأشارك معك من كنوز المعرفة المصرية القديمة.
        """

    async def get_response(self, user_id: int, message: str) -> str:
        """
        تحسين عملية توليد الردود باستخدام سياق المحادثة
        """
        try:
            # تحديث سياق المحادثة
            if user_id not in self.session_context:
                self.session_context[user_id] = []
            self.session_context[user_id].append({"role": "user", "content": message})

            # البحث في قاعدة المعرفة أولاً
            for category in self.knowledge_base:
                for topic, content in self.knowledge_base[category].items():
                    if topic.lower() in message.lower():
                        if isinstance(content, dict):
                            response = " ".join(content.values())
                        elif isinstance(content, list):
                            response = "، ".join(content)
                        else:
                            response = str(content)
                        break
                else:
                    continue
                break
            else:
                # استخدام النموذج للإجابة على الأسئلة غير الموجودة في قاعدة المعرفة
                inputs = self.tokenizer.encode(
                    message
                    + " ".join(
                        [m["content"] for m in self.session_context[user_id][-3:]]
                    ),
                    return_tensors="pt",
                    max_length=512,
                    truncation=True,
                )

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

                response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

            # تنسيق الرد بأسلوب ملكي
            formatted_response = self._format_royal_response(response)

            # تحديث سياق المحادثة
            self.session_context[user_id].append(
                {"role": "assistant", "content": formatted_response}
            )

            # الحفاظ على سياق محدود
            if len(self.session_context[user_id]) > 10:
                self.session_context[user_id] = self.session_context[user_id][-10:]

            return formatted_response

        except Exception as e:
            print(f"Error generating response: {e}")
            return "عذراً، حدث خطأ في معالجة سؤالك. هل يمكنك إعادة صياغته بشكل مختلف؟"

    def _format_royal_response(self, response: str) -> str:
        """تنسيق الرد بأسلوب ملكي"""
        royal_prefixes = [
            "يا بني",
            "اسمع يا هذا",
            "دعني أخبرك",
            "اعلم",
            "كما يقول الحكماء",
        ]

        royal_suffixes = [
            "هذا ما علمتنا إياه الآلهة",
            "هكذا كان في عهدي",
            "هذه حكمة الفراعنة",
            "كما دونه كتبتنا على جدران المعابد",
        ]

        from random import choice

        response = f"{choice(royal_prefixes)}، {response}"
        if not any(suffix in response for suffix in royal_suffixes):
            response = f"{response}. {choice(royal_suffixes)}."

        return response

    def expand_knowledge_base(self, new_knowledge: dict):
        """توسيع قاعدة المعرفة وحفظها"""
        for category, content in new_knowledge.items():
            if category in self.knowledge_base:
                self.knowledge_base[category].update(content)
            else:
                self.knowledge_base[category] = content

        self._save_knowledge_base()

    def get_session_summary(self, user_id: int) -> dict:
        """الحصول على ملخص لجلسة المحادثة"""
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
