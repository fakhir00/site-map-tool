"""
NLP keyword extraction pipeline.
Extracts primary keywords, LSI phrases, named entities, and heading keywords.
"""

import re
import logging
from typing import List, Iterable, Tuple
from collections import Counter

logger = logging.getLogger(__name__)
_SPACY_MODEL = None

COMMON_SHORT_TOKENS = {
    "ai", "api", "b2b", "b2c", "crm", "erp", "hr", "it", "ppc", "roi",
    "saas", "seo", "sem", "sso", "ui", "ux", "vps", "cms", "cpc", "kpi",
    "3d", "4g", "5g", "2fa", "web3", "url", "urls", "ssl", "xml", "html",
    "css", "js", "json", "csv", "pdf", "qr", "app", "apps", "yes", "no",
    "cmyk", "rgb", "h1", "h2", "h3", "h4", "h5", "h6", "ga4",
}
ALLOWED_INITIAL_CLUSTERS = {
    "bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "ph",
    "pl", "pr", "qu", "sc", "sh", "sk", "sl", "sm", "sn", "sp", "st",
    "sw", "th", "tr", "tw", "wh", "wr",
}

# Stopwords to filter out
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "need", "dare", "ought", "used", "able", "just", "than",
    "then", "so", "if", "as", "that", "which", "who", "whom", "whose",
    "this", "these", "those", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "he", "she", "him", "her",
    "not", "no", "nor", "very", "too", "also", "more", "most",
    "such", "other", "many", "some", "any", "each", "every", "all",
    "both", "few", "more", "most", "other", "such", "only", "own",
    "same", "here", "there", "when", "where", "why", "how", "i", "me", "my",
    "get", "got", "like", "use", "using", "make", "made", "one", "two",
    "new", "well", "good", "great", "best", "way", "time", "year",
    "even", "back", "after", "first", "last", "long", "little",
}
STOPWORDS.discard("no")

GENERIC_UI_WORDS = {
    "add", "area", "button", "cancel", "clear", "click", "close", "copy",
    "current", "delete", "disable", "download", "edit", "enable", "enter",
    "field", "filter", "footer", "form", "full", "header", "home", "items",
    "login", "menu", "modify", "next", "open", "previous", "register",
    "results", "screen", "section", "select", "settings", "share", "submit",
    "text", "title", "view",
}

IGNORED_TOPIC_TERMS = {
    "and", "best", "for", "near", "online", "or", "the", "tool", "tools", "with",
    "calculator", "calculators", "maker", "makers", "converter", "converters",
    "generator", "generators", "creator", "creators", "software", "app", "apps",
    "builder", "builders", "service", "services", "agency", "agencies",
    "company", "companies", "free", "cheap", "guide", "tutorial", "tutorials",
}


def clean_phrase(phrase: str) -> str:
    """Clean and normalize a keyword phrase."""
    phrase = phrase.lower().strip()
    phrase = phrase.encode("ascii", errors="ignore").decode("ascii")
    phrase = phrase.replace("_", " ")
    phrase = re.sub(r'[^a-z0-9\s-]', ' ', phrase)
    phrase = re.sub(r'\s+', ' ', phrase).strip()
    return phrase


def is_valid_keyword(phrase: str, min_len: int = 3, min_words: int = 1) -> bool:
    """Check if a phrase is a valid keyword."""
    if not phrase or len(phrase) < min_len:
        return False
    if len(phrase) > 80:
        return False
    if not re.match(r"^[a-z0-9][a-z0-9\s-]*$", phrase):
        return False
    words = phrase.split()
    if len(words) < min_words:
        return False
    if len(words) > 12:
        return False
    # All words are stopwords
    if all(w in STOPWORDS for w in words):
        return False
    if not any(w not in STOPWORDS and re.search(r"[a-z]", w) for w in words):
        return False
    # Contains mostly numbers
    if sum(c.isdigit() for c in phrase) / len(phrase) > 0.25:
        return False
    # Too many individual chars
    if any(len(w) == 1 for w in words if w.isalpha()):
        return False
    if re.search(r"(.)\1{4,}", phrase):
        return False

    return True


def keyword_terms(phrase: str, min_len: int = 2) -> set[str]:
    """Return searchable terms from a keyword phrase."""
    cleaned = clean_phrase(phrase).replace("-", " ")
    terms = set()
    for word in cleaned.split():
        if word in STOPWORDS or word in IGNORED_TOPIC_TERMS:
            continue
        if len(word) >= min_len or word in COMMON_SHORT_TOKENS:
            terms.add(word)
            if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
                terms.add(word[:-1])
    return terms


def seed_keyword_terms(raw_keywords: Iterable[str] | None) -> set[str]:
    """Extract topic terms from the user's seed keyword list."""
    terms: set[str] = set()
    for keyword in raw_keywords or []:
        for term in keyword_terms(keyword, min_len=2):
            if term not in IGNORED_TOPIC_TERMS:
                terms.add(term)
    return terms


def is_publishable_keyword(
    phrase: str,
    min_words: int = 2,
    topic_terms: set[str] | None = None,
) -> bool:
    """Validate final keywords that are safe to store, export, or show."""
    cleaned = clean_phrase(phrase)
    if not is_valid_keyword(cleaned, min_words=min_words):
        return False
    if topic_terms and not (keyword_terms(cleaned, min_len=2) & topic_terms):
        return False
    return True


def extract_rake_keywords(text: str, max_keywords: int = 20) -> List[Tuple[str, float]]:
    """Extract keywords using RAKE algorithm."""
    try:
        from rake_nltk import Rake

        def sentence_tokenizer(value: str) -> list[str]:
            return [part.strip() for part in re.split(r"[.!?;\n]+", value) if part.strip()]

        def word_tokenizer(value: str) -> list[str]:
            return re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", value)

        rake = Rake(
            min_length=1,
            max_length=4,
            include_repeated_phrases=False,
            sentence_tokenizer=sentence_tokenizer,
            word_tokenizer=word_tokenizer,
        )
        rake.extract_keywords_from_text(text)
        phrases_scores = rake.get_ranked_phrases_with_scores()
        results = []
        for score, phrase in phrases_scores[:max_keywords * 2]:
            cleaned = clean_phrase(phrase)
            if is_valid_keyword(cleaned) and len(cleaned.split()) <= 5:
                results.append((cleaned, float(score)))
                if len(results) >= max_keywords:
                    break
        return results
    except Exception as e:
        logger.warning(f"RAKE extraction failed: {e}")
        return []


def extract_statistical_keywords(text: str, max_keywords: int = 20) -> List[Tuple[str, float]]:
    """Dependency-free keyword fallback based on frequent clean n-grams."""
    cleaned = clean_phrase(text)
    words = [
        word
        for word in cleaned.split()
        if word not in STOPWORDS and len(word) > 2 and not word.isdigit()
    ]
    candidates: Counter[str] = Counter()

    for size in (3, 2, 1):
        for i in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[i : i + size])
            if is_valid_keyword(phrase, min_words=1):
                candidates[phrase] += size

    return [(phrase, float(score)) for phrase, score in candidates.most_common(max_keywords)]


def extract_keybert_keywords(text: str, max_keywords: int = 15) -> List[Tuple[str, float]]:
    """Extract keywords using KeyBERT (semantic similarity)."""
    try:
        from keybert import KeyBERT
        # Truncate to avoid OOM
        truncated = text[:8000]
        kw_model = KeyBERT(model="all-MiniLM-L6-v2")
        keywords = kw_model.extract_keywords(
            truncated,
            keyphrase_ngram_range=(1, 3),
            stop_words="english",
            use_mmr=True,
            diversity=0.5,
            top_n=max_keywords,
        )
        results = []
        for phrase, score in keywords:
            cleaned = clean_phrase(phrase)
            if is_valid_keyword(cleaned):
                results.append((cleaned, float(score)))
        return results
    except Exception as e:
        logger.warning(f"KeyBERT extraction failed: {e}")
        return []


def extract_spacy_entities(text: str) -> List[Tuple[str, str]]:
    """Extract named entities using spaCy."""
    try:
        nlp = _get_spacy_model()
        doc = nlp(text[:50000])  # Limit input size
        entities = []
        seen = set()
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PRODUCT", "GPE", "PERSON", "WORK_OF_ART", "LAW", "EVENT"):
                cleaned = clean_phrase(ent.text)
                if cleaned and cleaned not in seen and len(cleaned) > 2:
                    seen.add(cleaned)
                    entities.append((cleaned, ent.label_))
        return entities[:20]
    except Exception as e:
        logger.warning(f"spaCy NER failed: {e}")
        return []


def extract_noun_chunks(text: str) -> List[str]:
    """Extract noun phrases using spaCy."""
    try:
        nlp = _get_spacy_model()
        doc = nlp(text[:30000])
        chunks = []
        seen = set()
        for chunk in doc.noun_chunks:
            cleaned = clean_phrase(chunk.text)
            # Filter stopword-heavy chunks
            words = cleaned.split()
            meaningful = [w for w in words if w not in STOPWORDS]
            if len(meaningful) >= 1 and len(cleaned) >= 5 and cleaned not in seen:
                seen.add(cleaned)
                chunks.append(cleaned)
        return chunks[:25]
    except Exception as e:
        logger.warning(f"Noun chunk extraction failed: {e}")
        return []


def _get_spacy_model():
    global _SPACY_MODEL
    if _SPACY_MODEL is None:
        import spacy

        _SPACY_MODEL = spacy.load("en_core_web_sm")
    return _SPACY_MODEL


def _intent_stem(word: str) -> str:
    # Handle common SEO pluralizations/gerunds natively without heavy libraries
    w = word.lower()
    if w.endswith("ies"): return w[:-3] + "y"
    if w.endswith("ing"): return w[:-3]
    if w.endswith("es"): return w[:-2]
    if w.endswith("s"): return w[:-1]
    return w


def generate_intent_hash(phrase: str) -> str:
    """
    Strips stop words and normalizes the phrase into an alphabetically sorted 
    string of stemmed root words. This guarantees that "options trading strategies" 
    and "trading option strategy" hash to the exact same intent!
    """
    words = re.findall(r'[a-z0-9]+', phrase.lower())
    filtered = [w for w in words if w not in STOPWORDS and w not in GENERIC_UI_WORDS]
    stemmed = [_intent_stem(w) for w in filtered]
    
    # Sort alphabetically to ignore word order
    stemmed.sort()
    return " ".join(stemmed)


def get_intent_word_set(phrase: str) -> set[str]:
    """Returns the set of stemmed words for a phrase, ignoring stop words."""
    words = re.findall(r'[a-z0-9]+', phrase.lower())
    return {_intent_stem(w) for w in words if w not in STOPWORDS and w not in GENERIC_UI_WORDS}


def check_intent_cannibalization(phrase1: str, phrase2: str) -> bool:
    """
    Checks if two phrases mathematically cannibalize each other using 
    Set Subsets and Jaccard Similarity on their stemmed word bases.
    """
    set1 = get_intent_word_set(phrase1)
    set2 = get_intent_word_set(phrase2)
    
    if not set1 or not set2:
        return False
        
    # Check if one is a perfect mathematical subset of the other
    if set1.issubset(set2) or set2.issubset(set1):
        return True
        
    # Jaccard Similarity (Intersection over Union)
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    jaccard = len(intersection) / len(union)
    
    if jaccard >= 0.6:
        return True
        
    return False


def extract_heading_keywords(h1: str, h2s: List[str], h3s: List[str]) -> List[str]:
    """Extract keywords from page headings."""
    keywords = []
    all_headings = []
    if h1:
        all_headings.append(h1)
    all_headings.extend(h2s or [])
    all_headings.extend(h3s or [])

    seen = set()
    for heading in all_headings:
        # Clean and extract n-grams from heading
        cleaned = clean_phrase(heading)
        words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]

        # Add individual meaningful words
        for word in words:
            if word not in seen and is_valid_keyword(word, min_words=1):
                seen.add(word)
                keywords.append(word)

        # Add bigrams and trigrams
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if bigram not in seen and is_valid_keyword(bigram, min_words=2):
                seen.add(bigram)
                keywords.append(bigram)
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            if trigram not in seen and is_valid_keyword(trigram, min_words=2):
                seen.add(trigram)
                keywords.append(trigram)

    return keywords


class KeywordResult:
    """Structured result from keyword extraction."""
    def __init__(self):
        self.primary: List[Tuple[str, float]] = []       # (phrase, score)
        self.lsi: List[Tuple[str, float]] = []            # (phrase, score)
        self.entities: List[Tuple[str, str]] = []         # (phrase, entity_type)
        self.heading_keywords: List[str] = []


def extract_keywords_from_page(
    text: str,
    h1: str = None,
    h2s: List[str] = None,
    h3s: List[str] = None,
    use_keybert: bool = True,
    use_spacy: bool = True,
) -> KeywordResult:
    """
    Full keyword extraction pipeline for a single page.
    """
    result = KeywordResult()

    if not text or len(text) < 100:
        return result

    # 1. Primary keywords via RAKE
    result.primary = extract_rake_keywords(text, max_keywords=15)
    if not result.primary:
        result.primary = extract_statistical_keywords(text, max_keywords=15)

    # 2. LSI keywords via KeyBERT (semantic)
    if use_keybert and len(text) > 200:
        result.lsi = extract_keybert_keywords(text, max_keywords=10)

    # 3. Named entities via spaCy
    if use_spacy:
        result.entities = extract_spacy_entities(text)

    # 4. Heading keywords
    result.heading_keywords = extract_heading_keywords(h1, h2s or [], h3s or [])

    return result


VOLUME_RANK = {"High": 3, "Medium": 2, "Low": 1}

def cluster_keywords_by_intent(keywords: list[dict], similarity_threshold: float = 0.80) -> list[list[dict]]:
    """
    Groups keywords by semantic search intent using statistical set math (Jaccard).
    Replaces heavy PyTorch ML logic to stay under 512MB RAM constraints.
    """
    if len(keywords) <= 1:
        return [[kw] for kw in keywords]

    clusters = []
    for kw in keywords:
        phrase = kw["phrase"]
        added = False
        for cluster in clusters:
            for member in cluster:
                if check_intent_cannibalization(phrase, member["phrase"]):
                    cluster.append(kw)
                    added = True
                    break
            if added:
                break
        if not added:
            clusters.append([kw])

    return clusters


def pick_cluster_representative(cluster: list[dict]) -> dict:
    """
    Selects the single best keyword from a same-intent cluster:
    highest volume tier first, then the more natural/shorter phrasing as a tiebreak.
    """
    return sorted(
        cluster,
        key=lambda kw: (VOLUME_RANK.get(kw.get("volume", "Low"), 0), -len(kw["phrase"])),
        reverse=True,
    )[0]
