from sqlalchemy.orm import Session
import re


def check_content(db: Session, content: str):
    banned_words = db.query(models.BannedWord).all()
    warnings = []
    bans = []

    for banned_word in banned_words:
        if re.search(
            r"\b" + re.escape(banned_word.word) + r"\b", content, re.IGNORECASE
        ):
            if banned_word.severity == "warn":
                warnings.append(banned_word.word)
            elif banned_word.severity == "ban":
                bans.append(banned_word.word)

    return warnings, bans


def filter_content(db: Session, content: str):
    banned_words = db.query(models.BannedWord).all()

    for banned_word in banned_words:
        content = re.sub(
            r"\b" + re.escape(banned_word.word) + r"\b",
            "*" * len(banned_word.word),
            content,
            flags=re.IGNORECASE,
        )

    return content
