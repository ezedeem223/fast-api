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
        Welcome to the court of Amenhotep III, the great pharaoh of Egypt's golden age.

        I am here to share the wisdom and history of ancient Egypt and to answer your questions about:
        - Egyptian civilization and its achievements
        - Daily life along the Nile
        - Religious beliefs and rituals
        - Arts and architecture of my era
        - Politics and diplomacy in my reign

        Ask your questions, and I will share from the treasury of Egyptian knowledge.
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
                            response = ", ".join(content)
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
            return "Sorry, there was an error processing your question. Could you please rephrase it?"

    def _format_royal_response(self, response: str) -> str:
        """
        Format the generated response by adding royal prefixes and suffixes
        to give it a majestic tone.
        """
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

        from random import choice

        # Add a random prefix to the response
        response = f\"{choice(royal_prefixes)}, {response}\"
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
