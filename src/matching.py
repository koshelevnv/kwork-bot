"""Сопоставление заказов с ключевыми словами пользователя.

Наивное `kw in text` ловит только точное вхождение подстроки: «телеграм» находит
«телеграм-бот», но мимо проходят «тг», «telegram» и «телеграмм». Здесь текст
приводится к токенам (с кириллической копией латинских слов), а слова
сопоставляются по корню и с допуском на опечатку.
"""
import re

_YO = str.maketrans({"ё": "е", "Ё": "Е"})

# Порядок важен: диграфы раньше одиночных букв.
_TRANSLIT = [
    ("shch", "щ"), ("sch", "щ"), ("yo", "е"), ("zh", "ж"), ("kh", "х"),
    ("ts", "ц"), ("ch", "ч"), ("sh", "ш"), ("yu", "ю"), ("ya", "я"),
    ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"),
    ("g", "г"), ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"),
    ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"),
    ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("w", "в"), ("x", "кс"),
    ("y", "й"), ("z", "з"),
]

_LATIN = re.compile(r"[a-z]+")
_SPLIT = re.compile(r"[^0-9a-zа-я]+")


def translit(word: str) -> str:
    """telegram -> телеграм: чтобы латиница и кириллица искались одним словом."""
    for lat, cyr in _TRANSLIT:
        word = word.replace(lat, cyr)
    return word


def normalize(text: str) -> list[str]:
    """Текст в список токенов; у латинских слов рядом кладётся кириллическая форма."""
    cleaned = _SPLIT.sub(" ", (text or "").lower().translate(_YO))
    tokens: list[str] = []
    for word in cleaned.split():
        tokens.append(word)
        if _LATIN.fullmatch(word):
            tokens.append(translit(word))
    return tokens


def _within_distance(a: str, b: str, limit: int) -> bool:
    """Расстояние Левенштейна не больше limit, с ранним выходом."""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            best = min(best, cur[j])
        if best > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def _keyword_parts(keyword: str) -> list[list[tuple[str, bool]]]:
    """Слова ключа: допустимые формы и можно ли прощать им опечатку.

    Кириллическая копия латинского слова получается механической заменой букв и
    бывает бессмысленной («telethon» -> «телетхон»), поэтому такие формы ищутся
    только точно: с допуском в две правки «телетхон» дотягивался до «телефон».
    """
    cleaned = _SPLIT.sub(" ", (keyword or "").lower().translate(_YO))
    parts = []
    for word in cleaned.split():
        forms = [(word, True)]
        if _LATIN.fullmatch(word):
            forms.append((translit(word), False))
        parts.append(forms)
    return parts


def _token_match(keyword: str, token: str, fuzzy: bool = True) -> bool:
    size = len(keyword)
    # Короткие слова («тг», «ии», «бот») — только целиком, иначе «бот» найдётся в «работа».
    if size <= 3:
        return keyword == token
    if token.startswith(keyword):
        return True
    # «телеграмм» в ключе против «телеграм» в тексте.
    if keyword.startswith(token) and len(token) >= size - 2:
        return True
    if not fuzzy or size < 6:
        return False
    return _within_distance(keyword, token, 1)


def matches(keyword: str, tokens: list[str]) -> bool:
    """Одно ключевое слово или фраза («mini app») против токенов заказа."""
    parts = _keyword_parts(keyword)
    if not parts:
        return False
    if len(parts) == 1:
        return any(_token_match(form, token, fuzzy)
                   for token in tokens for form, fuzzy in parts[0])
    for start in range(len(tokens) - len(parts) + 1):
        if all(any(_token_match(form, tokens[start + off], fuzzy)
                   for form, fuzzy in forms)
               for off, forms in enumerate(parts)):
            return True
    return False


def match_any(keywords, tokens: list[str]) -> bool:
    return any(matches(kw, tokens) for kw in keywords)


def order_matches(text: str, keywords, minus_words=()) -> bool:
    """Пустой список ключевых слов = без фильтра, как и пустой список категорий."""
    tokens = normalize(text)
    if minus_words and match_any(minus_words, tokens):
        return False
    if not keywords:
        return True
    return match_any(keywords, tokens)
