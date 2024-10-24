from transformers import AutoModelForCausalLM, AutoTokenizer
from fastapi import WebSocket
import torch
import os
from typing import List, Optional
from pydantic import BaseModel
import aiohttp


class AmenhotepAI:
    def __init__(self):
        self.model_name = "bigscience/bloom-1b7"  # نموذج متعدد اللغات يدعم العربية
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
        self.welcome_message = """
        أنت في حضرة الملك أمنحتب الثالث، فرعون الحكمة والمعرفة. 
        اسأل عما شئت، وسيمنحك من أسرار الفراعنة ما تريد.
        """

    async def get_response(self, message: str) -> str:
        # تحضير النص للنموذج
        inputs = self.tokenizer.encode(message, return_tensors="pt")

        # توليد الإجابة
        outputs = self.model.generate(
            inputs,
            max_length=150,
            num_return_sequences=1,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
        )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return response

    def get_welcome_message(self) -> str:
        return self.welcome_message
