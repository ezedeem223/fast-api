# app/ai_chat/amenhotep.py

from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer
import torch
import json
import os
from app.core.config import settings


class AmenhotepAI:
    """
    A class representing an AI chat system that uses a transformer-based model,
    specifically tailored for Arabic language queries.
    """

    def __init__(self):
        # Retrieve the HuggingFace API token from settings
        huggingface_token = settings.HUGGINGFACE_API_TOKEN

        # Define the model name for a specialized Arabic language model
        self.model_name = "aubmindlab/bert-base-arabertv02"

        # Initialize the tokenizer with the given model
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, token=huggingface_token, use_fast=True
        )

        # Initialize the causal language model with device mapping based on GPU availability
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            token=huggingface_token,
            device_map="auto" if torch.cuda.is_available() else None,
        )

        # Create a question-answering pipeline using the same model and tokenizer
        self.qa_pipeline = pipeline(
            "question-answering",
            model=self.model_name,
            tokenizer=self.tokenizer,
            device=0 if torch.cuda.is_available() else -1,
        )

        # Ensure the data directory exists for storing the knowledge base
        os.makedirs("data/amenhotep", exist_ok=True)

        # Load or create the specialized knowledge base
        self.knowledge_base = self._load_knowledge_base()

        # Prepare a detailed welcome message
        self.welcome_message = self._get_welcome_message()

        # Initialize the session context to keep track of conversation history
        self.session_context = {}

    def _load_knowledge_base(self) -> dict:
        """
        Load the knowledge base from a JSON file or create a default one if not available.
        """
        knowledge_file = "data/amenhotep/knowledge_base.json"
        try:
            if os.path.exists(knowledge_file):
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading knowledge base: {e}")

        # Return a default knowledge base if file does not exist or fails to load
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
        """
        Save the updated knowledge base to a JSON file.
        """
        try:
            with open("data/amenhotep/knowledge_base.json", "w", encoding="utf-8") as f:
                json.dump(self.knowledge_base, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving knowledge base: {e}")

    def _get_welcome_message(self) -> str:
        """
        Return a detailed welcome message in Arabic.
        """
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
                        # If the content is a dictionary, join its values into a string
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
                # Use the language model to generate a response if no matching topic is found
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

            # Format the response in a regal style
            formatted_response = self._format_royal_response(response)

            # Append the assistant's response to the conversation history
            self.session_context[user_id].append(
                {"role": "assistant", "content": formatted_response}
            )

            # Limit the session context to the last 10 messages to manage memory
            if len(self.session_context[user_id]) > 10:
                self.session_context[user_id] = self.session_context[user_id][-10:]

            return formatted_response

        except Exception as e:
            print(f"Error generating response: {e}")
            return "عذراً، حدث خطأ في معالجة سؤالك. هل يمكنك إعادة صياغته بشكل مختلف؟"

    def _format_royal_response(self, response: str) -> str:
        """
        Format the generated response by adding royal prefixes and suffixes
        to give it a majestic tone.
        """
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

        # Add a random prefix to the response
        response = f"{choice(royal_prefixes)}، {response}"
        # Append a random suffix if not already present
        if not any(suffix in response for suffix in royal_suffixes):
            response = f"{response}. {choice(royal_suffixes)}."

        return response

    def expand_knowledge_base(self, new_knowledge: dict):
        """
        Expand the current knowledge base with new information and save it.
        """
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
