from flask_babel import Babel
from fastapi import Request

babel = Babel()

LANGUAGES = {"en": "English", "ar": "Arabic"}


@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(LANGUAGES.keys())
