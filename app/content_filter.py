from sqlalchemy.orm import Session
import re
from app import models  # Ensure that your models are correctly imported


def check_content(db: Session, content: str):
    """
    Check the given content for banned words and classify them based on severity.

    Parameters:
        db (Session): SQLAlchemy session to interact with the database.
        content (str): The text content to be checked.

    Returns:
        tuple: Two lists are returned:
            - warnings: A list of banned words that should trigger a warning.
            - bans: A list of banned words that should trigger a ban.

    The function retrieves all banned words from the database, then searches the content
    using regular expressions. It uses word boundaries (\\b) to ensure exact word matches and
    performs a case-insensitive search.
    """
    banned_words = db.query(models.BannedWord).all()
    warnings = []
    bans = []

    for banned_word in banned_words:
        # Construct a regex pattern to match the banned word as a whole word
        pattern = r"\b" + re.escape(banned_word.word) + r"\b"
        if re.search(pattern, content, re.IGNORECASE):
            if banned_word.severity == "warn":
                warnings.append(banned_word.word)
            elif banned_word.severity == "ban":
                bans.append(banned_word.word)

    return warnings, bans


def filter_content(db: Session, content: str):
    """
    Filter the given content by replacing banned words with asterisks.

    Parameters:
        db (Session): SQLAlchemy session to interact with the database.
        content (str): The text content to be filtered.

    Returns:
        str: The content with banned words replaced by asterisks of the same length.

    The function retrieves all banned words from the database and uses regular expressions
    to replace each occurrence with asterisks. This ensures that the structure of the text is maintained
    while the banned words are obscured.
    """
    banned_words = db.query(models.BannedWord).all()

    for banned_word in banned_words:
        # Construct a regex pattern to match the banned word as a whole word
        pattern = r"\b" + re.escape(banned_word.word) + r"\b"
        replacement = "*" * len(banned_word.word)
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    return content
