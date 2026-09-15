def check_emd_match(seed: str, cleaned_phrase: str) -> bool:
    import re
    seed_words = seed.split()
    if len(seed_words) <= 2:
        seed_compact = re.sub(r"[^a-z0-9]", "", seed)
        for tld in ("com", "net", "org", "co", "io", "app", "us", "uk"):
            if seed.endswith(f" {tld}") or seed == tld:
                seed_compact = seed_compact[:-len(tld)]
                break
        
        if len(seed_compact) > 4:
            phrase_words = cleaned_phrase.split()
            for i in range(len(phrase_words)):
                for j in range(i + 1, len(phrase_words) + 1):
                    if "".join(phrase_words[i:j]) == seed_compact:
                        return True
    return False

print("1:", check_emd_match("circuitdiagrammaker com", "circuit diagram maker")) # True
print("2:", check_emd_match("dentalpro7", "dental pro 7 review")) # True
print("3:", check_emd_match("dental", "accidental death")) # False
print("4:", check_emd_match("moonnodescalculator", "free moon nodes calculator")) # True
