import sys
sys.path.insert(0, '.')
from nlp.keywords import clean_phrase, STOPWORDS, COMMON_SHORT_TOKENS, ALLOWED_INITIAL_CLUSTERS, GENERIC_UI_WORDS
import re

def is_valid_keyword_debug(phrase: str, min_len: int = 3, min_words: int = 1) -> bool:
    if not phrase or len(phrase) < min_len:
        print("fail 1")
        return False
    if len(phrase) > 80:
        print("fail 2")
        return False
    if not re.match(r"^[a-z0-9][a-z0-9\s-]*$", phrase):
        print("fail 3 regex")
        return False

    words = phrase.split()
    if len(words) < min_words:
        print("fail 4")
        return False
    if len(words) > 12:
        print("fail 5")
        return False
    if all(w in STOPWORDS for w in words):
        print("fail 6")
        return False
    if not any(w not in STOPWORDS and re.search(r"[a-z]", w) for w in words):
        print("fail 7")
        return False
    if sum(c.isdigit() for c in phrase) / len(phrase) > 0.25:
        print("fail 8 digits")
        return False
    if any(len(w) == 1 for w in words if w.isalpha() and w not in {"a", "i"}):
        print("fail 9 length 1")
        return False
    if re.search(r"(.)\1{4,}", phrase):
        print("fail 10 repeating")
        return False

    noisy_parts = 0
    severe_noise_parts = 0
    checked_parts = 0
    for word in words:
        for part in word.split("-"):
            if not part: continue
            checked_parts += 1
            has_alpha = bool(re.search(r"[a-z]", part))
            has_digit = bool(re.search(r"\d", part))
            if has_alpha and has_digit and part not in COMMON_SHORT_TOKENS:
                noisy_parts += 1
                if len(part) > 6: severe_noise_parts += 1
                continue
            if has_digit and not has_alpha:
                if len(part) > 5:
                    noisy_parts += 1
                    severe_noise_parts += 1
                continue
            if re.fullmatch(r"[a-f0-9]{7,}", part) and part not in COMMON_SHORT_TOKENS:
                noisy_parts += 1
                severe_noise_parts += 1
                continue
            if len(part) > 24:
                noisy_parts += 1
                severe_noise_parts += 1
                continue
            if len(part) <= 2 and part not in COMMON_SHORT_TOKENS and part not in STOPWORDS:
                noisy_parts += 1
                continue
            if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", part) and part not in COMMON_SHORT_TOKENS:
                noisy_parts += 1
                continue
            if len(part) >= 4 and re.match(r"^[bcdfghjklmnpqrstvwxz]{2}", part) and part[:2] not in ALLOWED_INITIAL_CLUSTERS and part not in COMMON_SHORT_TOKENS:
                noisy_parts += 1
                continue
            if len(part) >= 4 and not re.search(r"[aeiou]", part) and part not in COMMON_SHORT_TOKENS:
                noisy_parts += 1
                if len(part) >= 7: severe_noise_parts += 1

    if severe_noise_parts:
        print("fail 11 severe noise")
        return False
    if checked_parts and noisy_parts / checked_parts >= 0.25:
        print(f"fail 12 ratio {noisy_parts}/{checked_parts}")
        return False

    meaningful_lengths = [len(word.strip("-")) for word in words if word not in STOPWORDS]
    if meaningful_lengths and max(meaningful_lengths) < 4 and len(words) == 1 and not any(word in COMMON_SHORT_TOKENS for word in words):
        print("fail 13 meaningful length")
        return False

    meaningful_words = [word for word in words if word not in STOPWORDS]
    if meaningful_words and all(word in GENERIC_UI_WORDS for word in meaningful_words):
        print("fail 14 generic")
        return False

    print("Success!")
    return True

kw = clean_phrase("how to analyze 0DTE gamma exposure")
is_valid_keyword_debug(kw)
