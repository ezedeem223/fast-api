# Proper environment variable handling
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# RSA keys handling
RSA_PUBLIC_KEY = os.getenv('RSA_PUBLIC_KEY') or open('path/to/your/public/key.pem').read()
RSA_PRIVATE_KEY = os.getenv('RSA_PRIVATE_KEY') or open('path/to/your/private/key.pem').read()

# Example of correct os.getenv usage
SOME_CONFIG_VALUE = os.getenv('SOME_CONFIG_VALUE', 'default_value')

# Your other settings go here
