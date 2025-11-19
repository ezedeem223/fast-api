from pydantic import BaseSettings, SecretStr
import os

class Settings(BaseSettings):
    # Define environment variables with default values or required settings
    app_name: str = "Fast API Application"
    redis_url: str
    rsa_private_key: SecretStr
    rsa_public_key: SecretStr

    class Config:
        env_file = ".env"

settings = Settings()  # Create an instance to load settings

# Handle RSA keys gracefully for production deployments
if os.getenv('ENVIRONMENT') == 'production':
    if not settings.rsa_private_key:
        raise ValueError("RSA private key must be provided in production")
    if not settings.rsa_public_key:
        raise ValueError("RSA public key must be provided in production")

# Use settings.redis_url in your Redis connection logic
