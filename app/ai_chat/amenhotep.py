from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
from fastapi import WebSocket
import torch
from typing import List, Optional
from pydantic import BaseModel
import aiohttp


class AmenhotepAI:
    def __init__(self):
        # استخدام نموذج أصغر وأكثر كفاءة يدعم اللغة العربية
        self.model_name = "CAMeL-Lab/bert-base-arabic-camelbert-ca"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)

        # تهيئة نموذج الإجابة على الأسئلة
        self.qa_pipeline = pipeline(
            "question-answering", model=self.model_name, tokenizer=self.model_name
        )

        # رسالة الترحيب
        self.welcome_message = """
        مرحباً بك في حضرة الملك أمنحتب الثالث، فرعون مصر العظيم.
        أنا هنا لمشاركة حكمة وتاريخ مصر القديمة معك.
        تفضل بطرح أي سؤال عن الحضارة المصرية القديمة، الأهرامات، 
        الحياة في مصر القديمة، أو أي موضوع يهمك عن تلك الحقبة الذهبية.
        """

        # قاعدة معرفة أساسية عن مصر القديمة
        self.knowledge_base = {
            "أمنحتب الثالث": "أنا أمنحتب الثالث، أحد أعظم فراعنة الأسرة الثامنة عشرة. حكمت مصر في عصرها الذهبي، وشهدت فترة حكمي ازدهاراً كبيراً في الفنون والعمارة.",
            "الأهرامات": "الأهرامات من أعظم الإنجازات المعمارية في التاريخ البشري. بُنيت كمقابر للفراعنة وتعد من عجائب الدنيا السبع.",
            "الحياة اليومية": "كانت الحياة في مصر القديمة تدور حول نهر النيل. كان المصريون يزرعون القمح والشعير ويصنعون البردي ويتاجرون مع الدول المجاورة.",
        }

    async def get_response(self, message: str) -> str:
        """
        توليد رد مناسب على رسالة المستخدم
        """
        try:
            # البحث في قاعدة المعرفة أولاً
            for key, value in self.knowledge_base.items():
                if key in message:
                    return value

            # إذا لم نجد إجابة في قاعدة المعرفة، نستخدم النموذج
            inputs = self.tokenizer.encode(
                message, return_tensors="pt", max_length=512, truncation=True
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

            # تنسيق الإجابة لتبدو كأنها من أمنحتب
            return f"يا بني، {response}"

        except Exception as e:
            return "عذراً، لا أستطيع فهم سؤالك. هل يمكنك إعادة صياغته بطريقة أخرى؟"

    def get_welcome_message(self) -> str:
        return self.welcome_message

    def expand_knowledge_base(self, new_knowledge: dict):
        """
        إضافة معلومات جديدة إلى قاعدة المعرفة
        """
        self.knowledge_base.update(new_knowledge)
