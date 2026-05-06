from flask import current_app


def detect_danger_keywords(text: str):
    """
    텍스트에서 위험 키워드를 찾아 (발견된_키워드_리스트, has_danger) 를 반환합니다.
    config.py 의 DANGER_KEYWORDS 목록을 참조합니다.
    """
    if not text:
        return [], False

    keywords = current_app.config.get('DANGER_KEYWORDS', [])
    found    = [kw for kw in keywords if kw in text]
    return found, len(found) > 0
