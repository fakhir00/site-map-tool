import re
from nlp.keywords import STOPWORDS, COMMON_SHORT_TOKENS, ALLOWED_INITIAL_CLUSTERS

def check(phrase):
    words = phrase.split()
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
                print("fail 1:", part)
                noisy_parts += 1
                severe_noise_parts += 1
                continue
            if has_digit and part not in COMMON_SHORT_TOKENS:
                print("fail 2:", part)
                noisy_parts += 1
                if not re.fullmatch(r"(19|20)\d{2}", part): severe_noise_parts += 1
                continue
            if re.fullmatch(r"[a-f0-9]{7,}", part) and part not in COMMON_SHORT_TOKENS:
                print("fail 3:", part)
                noisy_parts += 1
                severe_noise_parts += 1
                continue
            if len(part) > 24:
                print("fail 4:", part)
                noisy_parts += 1
                severe_noise_parts += 1
                continue
            if len(part) <= 2 and part not in COMMON_SHORT_TOKENS and part not in STOPWORDS:
                print("fail 5:", part)
                noisy_parts += 1
                continue
            if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", part) and part not in COMMON_SHORT_TOKENS:
                print("fail 6:", part)
                noisy_parts += 1
                continue
            if len(part) >= 4 and re.match(r"^[bcdfghjklmnpqrstvwxz]{2}", part) and part[:2] not in ALLOWED_INITIAL_CLUSTERS and part not in COMMON_SHORT_TOKENS:
                print("fail 7:", part)
                noisy_parts += 1
                continue
            if len(part) >= 4 and not re.search(r"[aeiou]", part) and part not in COMMON_SHORT_TOKENS:
                print("fail 8:", part)
                noisy_parts += 1
                if len(part) >= 7: severe_noise_parts += 1

    if severe_noise_parts: print("fail severe")
    if checked_parts and noisy_parts / checked_parts >= 0.25: print("fail ratio:", noisy_parts, checked_parts)
    
import sys
sys.path.insert(0, '.')
check("how to analyze 0dte gamma exposure")
