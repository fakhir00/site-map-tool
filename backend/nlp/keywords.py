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
_KEYBERT_MODEL = None

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
    "diagram", "diagrams", "chart", "charts",
    "company", "companies", "free", "cheap", "guide", "tutorial", "tutorials",
}

# These words describe broad formats or measurements and are unsafe as the
# only overlap with a more specific seed such as "lunar age calculator".
BROAD_TOPIC_TERMS = {
    "age", "calendar", "date", "day", "month", "year", "system",
}

GENERIC_TOOL_TERMS = {
    "app", "apps", "calculator", "calculators", "creator", "generator",
    "maker", "software", "tool", "tools",
}


def clean_phrase(phrase: str) -> str:
    """Clean and normalize a keyword phrase."""
    phrase = phrase.lower().strip()
    phrase = phrase.encode("ascii", errors="ignore").decode("ascii")
    phrase = phrase.replace("_", " ")
    phrase = re.sub(r'[^a-z0-9\s-]', ' ', phrase)
    phrase = re.sub(r'\s+', ' ', phrase).strip()
    return phrase


def normalize_seed_keywords(raw_keywords: Iterable[str] | None) -> list[str]:
    """Split legacy comma/newline seed input and return clean unique phrases."""
    normalized: list[str] = []
    for raw in raw_keywords or []:
        for part in re.split(r"[,;\n|]+", str(raw)):
            phrase = clean_phrase(part)
            if phrase and is_valid_keyword(phrase, min_words=1) and phrase not in normalized:
                normalized.append(phrase)
    return normalized


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
    if sum(1 for w in words if w.isalpha() and len(w) == 1 and w not in STOPWORDS) > 0:
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
    for keyword in normalize_seed_keywords(raw_keywords):
        for term in keyword_terms(keyword, min_len=2):
            if term not in IGNORED_TOPIC_TERMS:
                terms.add(term)
    return terms


def site_scope_terms(primary_seed: str, audit_data: dict | None = None) -> set[str]:
    """Extract function/subject terms from the EMD seed and positive audit fields."""
    primary_words = set(clean_phrase(primary_seed).split())
    primary_anchors = seed_keyword_terms([primary_seed]) - BROAD_TOPIC_TERMS
    scope = primary_words - primary_anchors - STOPWORDS - GENERIC_TOOL_TERMS
    if not isinstance(audit_data, dict):
        return scope
    for field in ("industry_niche", "core_action", "capabilities", "content_opportunities"):
        raw = audit_data.get(field)
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str):
                continue
            scope.update(
                word for word in clean_phrase(value).split()
                if len(word) > 2
                and word not in primary_anchors
                and word not in STOPWORDS
                and word not in GENERIC_TOOL_TERMS
            )
    return scope


def is_publishable_keyword(
    phrase: str,
    min_words: int = 2,
    topic_terms: set[str] | None = None,
    negative_terms: set[str] | None = None,
) -> bool:
    """Validate final keywords that are safe to store, export, or show."""
    cleaned = clean_phrase(phrase)
    if not is_valid_keyword(cleaned, min_words=min_words):
        return False

    words = cleaned.split()
    # Scraped headings and navigation text often produce fragments such as
    # "age korean age". Repeated meaningful terms in a short phrase are a
    # strong signal that this is an extraction artifact, not a search query.
    meaningful_words = [word for word in words if word not in STOPWORDS]
    if len(meaningful_words) != len(set(meaningful_words)):
        return False
    if len(words) > 8:
        return False
        
    terms = keyword_terms(cleaned, min_len=2)
    
    if negative_terms and (terms & negative_terms):
        return False
        
    if topic_terms:
        overlap = terms & topic_terms
        if not overlap:
            return False
        # If it's a longer phrase, require it to have at least one meaningful core word, 
        # not just a coincidental short word match. We check if the overlap has words > 3 chars
        # or if there's multiple overlapping words.
        if len(terms) >= 3 and len(overlap) == 1:
            single_match = list(overlap)[0]
            if len(single_match) <= 3 and single_match not in COMMON_SHORT_TOKENS:
                return False
                
    return True


def is_topic_relevant_keyword(
    phrase: str,
    seed_keywords: Iterable[str] | None,
    topic_terms: set[str] | None,
    negative_terms: set[str] | None = None,
) -> bool:
    """Keep candidates inside the primary entity and functional site scope."""
    cleaned = clean_phrase(phrase)
    phrase_terms = keyword_terms(cleaned, min_len=2)
    raw_terms = set(cleaned.split()) - STOPWORDS
    if not phrase_terms or (negative_terms and phrase_terms & negative_terms):
        # Generic seed words are intentionally removed from keyword_terms, but
        # an exact seed-anchored phrase is still relevant by definition.
        return any(
            re.search(rf"\b{re.escape(clean_phrase(seed))}\b", cleaned)
            for seed in normalize_seed_keywords(seed_keywords)
            if clean_phrase(seed)
        ) and not (negative_terms and set(cleaned.split()) & negative_terms)
    normalized_seeds = normalize_seed_keywords(seed_keywords)
    if any(re.search(rf"\b{re.escape(seed)}\b", cleaned) for seed in normalized_seeds):
        return True

    # Allow exact-match domains without spaces to match their constituent words
    phrase_words = cleaned.split()
    for seed in normalized_seeds:
        seed_words = seed.split()
        if len(seed_words) <= 2:
            seed_compact = re.sub(r"[^a-z0-9]", "", seed)
            for tld in ("com", "net", "org", "co", "io", "app", "us", "uk"):
                if seed.endswith(f" {tld}") or seed == tld:
                    seed_compact = seed_compact[:-len(tld)]
                    break
            if len(seed_compact) > 4:
                for i in range(len(phrase_words)):
                    for j in range(i + 1, len(phrase_words) + 1):
                        if "".join(phrase_words[i:j]) == seed_compact:
                            return True

    # Every Gold Hunter seed is an explicit site-scope signal. Allow a close
    # variation of any seed when it retains both that seed's distinctive entity
    # and its function/subject. This expands useful volume across all 3-5 seeds
    # without letting a generic shared word redefine the EMD topic.
    for seed in normalized_seeds:
        seed_anchors = seed_keyword_terms([seed]) - BROAD_TOPIC_TERMS
        seed_scope = site_scope_terms(seed)
        if seed_anchors and (raw_terms & seed_anchors) and (raw_terms & seed_scope):
            return True
        # Some exact-match tool seeds contain only distinctive entity words plus
        # a generic tool word (for example, "moon nodes calculator"). In that
        # case there is no separate scope word to satisfy the rule above. Keep a
        # close variation when it retains the complete distinctive entity.
        if not seed_scope and seed_anchors and seed_anchors.issubset(phrase_terms):
            return True

    primary_seed = normalized_seeds[:1]
    primary_anchors = seed_keyword_terms(primary_seed) - BROAD_TOPIC_TERMS
    primary_scope = site_scope_terms(primary_seed[0]) if primary_seed else set()
    semantic_anchors = {
        term.removeprefix("__anchor__")
        for term in (topic_terms or set())
        if term.startswith("__anchor__")
    }
    scope_terms = {
        term.removeprefix("__scope__")
        for term in (topic_terms or set())
        if term.startswith("__scope__")
    } | primary_scope
    candidate_anchors = raw_terms & (primary_anchors | semantic_anchors)
    candidate_scope = raw_terms & scope_terms

    # A distinctive EMD/primary entity by itself is not enough: "lunar
    # eclipse" and "circuit court" are different subjects. Requiring a site
    # function as the second edge keeps results within two semantic hops.
    if primary_anchors or semantic_anchors:
        if not scope_terms and primary_anchors and primary_anchors.issubset(phrase_terms):
            return True
        return bool(candidate_anchors and candidate_scope)

    anchors = seed_keyword_terms(normalized_seeds)
    if phrase_terms & anchors:
        return True
    return len(phrase_terms & (topic_terms or set())) >= 2


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
        global _KEYBERT_MODEL
        if _KEYBERT_MODEL is None:
            from keybert import KeyBERT

            _KEYBERT_MODEL = KeyBERT(model="all-MiniLM-L6-v2")

        # Truncate to avoid OOM
        truncated = text[:8000]
        keywords = _KEYBERT_MODEL.extract_keywords(
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
    except ImportError:
        logger.info("KeyBERT not installed, skipping semantic keyword extraction")
        return []
    except Exception as e:
        logger.warning(f"KeyBERT extraction failed: {e}")
        return []


def extract_spacy_entities(text: str) -> List[Tuple[str, str]]:
    """Extract named entities using spaCy."""
    try:
        nlp = _get_spacy_model()
        if nlp is None:
            return []
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
        if nlp is None:
            return []
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
        try:
            import spacy
            _SPACY_MODEL = spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            logger.info("spaCy not installed or model not found, skipping NER")
            return None
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
    # Competitor pages often contain navigation and explanatory prose before
    # their useful long-tail phrases. Fifteen candidates was too shallow.
    result.primary = extract_rake_keywords(text, max_keywords=40)
    if not result.primary:
        result.primary = extract_statistical_keywords(text, max_keywords=40)

    # 2. LSI keywords via KeyBERT (semantic)
    if use_keybert and len(text) > 200:
        result.lsi = extract_keybert_keywords(text, max_keywords=10)

    # 3. Named entities via spaCy
    if use_spacy:
        result.entities = extract_spacy_entities(text)

    # 4. Heading keywords
    result.heading_keywords = extract_heading_keywords(h1, h2s or [], h3s or [])

    return result


# ─── 4-Tier Keyword Clustering ────────────────────────────────

_INTENT_MODEL = None

VOLUME_RANK = {"High": 3, "Medium": 2, "Low": 1}

LEVEL1_THRESHOLD = 0.55   # loose: defines sub-silo membership
LEVEL2_THRESHOLD = 0.85   # tight: candidate for true duplication


def phrase_similarity(phrase1: str, phrase2: str) -> float:
    """Calculate intent similarity using set math (Jaccard) to save RAM."""
    set1 = get_intent_word_set(phrase1)
    set2 = get_intent_word_set(phrase2)
    if not set1 or not set2:
        return 0.0
    if set1.issubset(set2) or set2.issubset(set1):
        return 1.0
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return len(intersection) / len(union)


def cluster_level(keywords: list[dict], threshold: float) -> list[list[dict]]:
    """
    Mathematical average-linkage clustering based on Jaccard similarity threshold.
    Replaces heavy PyTorch AgglomerativeClustering to stay under 512MB RAM constraints.
    """
    if len(keywords) <= 1:
        return [[kw] for kw in keywords]

    clusters = []
    for kw in keywords:
        phrase = kw["phrase"]
        best_cluster = None
        best_sim = -1.0
        
        for cluster in clusters:
            sims = [phrase_similarity(phrase, c["phrase"]) for c in cluster]
            avg_sim = sum(sims) / len(sims)
            if avg_sim > best_sim:
                best_sim = avg_sim
                best_cluster = cluster
                
        if best_sim >= threshold and best_cluster is not None:
            best_cluster.append(kw)
        else:
            clusters.append([kw])
            
    return clusters


def pick_cluster_representative(cluster: list[dict]) -> dict:
    """Highest volume tier wins; tiebreak by shorter/more natural phrasing."""
    return sorted(
        cluster,
        key=lambda kw: (VOLUME_RANK.get(kw.get("volume", "Low"), 0), -len(kw["phrase"])),
        reverse=True,
    )[0]


def pick_broadest_phrase(cluster: list[dict]) -> dict:
    """
    For Tier 2 title selection: picks the broadest framing (usually the shortest phrase).
    Replaces embedding centroid calculations to save RAM.
    """
    return min(cluster, key=lambda kw: len(kw["phrase"]))


def classify_keyword_tiers(keywords: list[dict], call_llm_fn) -> list[dict]:
    """
    Input: keywords already passed through relevance + volume gates.
    Only pass keywords with type in {"primary", "long-tail"}.

    Output: list of tier records:
      {"tier": "merge", "sub_silo": <id>, "cluster": [...], "representative_keyword": {...}}
      {"tier": "subheading_group", "sub_silo": <id>, "cluster": [...], "broadest": {...}}
      {"tier": "related", "sub_silo": <id>, "cluster_group_id": <id>, "members": [...]}
      {"tier": "outlier", "sub_silo": <id>, "keyword": {...}}
    """
    if not keywords:
        return []

    results = []
    level1_clusters = cluster_level(keywords, LEVEL1_THRESHOLD)

    for sub_silo_id, l1_cluster in enumerate(level1_clusters):
        if len(l1_cluster) == 1:
            results.append({
                "tier": "outlier",
                "sub_silo": sub_silo_id,
                "keyword": l1_cluster[0],
            })
            continue

        level2_clusters = cluster_level(l1_cluster, LEVEL2_THRESHOLD)
        used_in_tight_cluster: set[str] = set()

        for l2_cluster in level2_clusters:
            if len(l2_cluster) < 2:
                continue  # handled as "related" below via leftovers

            try:
                verdict = call_llm_fn(l2_cluster)
            except Exception as e:
                logger.warning("LLM cluster verification failed: %s", e)
                verdict = {"verdict": "related_nuance"}

            verdict_type = verdict.get("verdict", "related_nuance") if isinstance(verdict, dict) else "related_nuance"

            if verdict_type == "same_intent":
                results.append({
                    "tier": "merge",
                    "sub_silo": sub_silo_id,
                    "cluster": l2_cluster,
                    "representative_keyword": pick_cluster_representative(l2_cluster),
                })
                used_in_tight_cluster.update(kw["phrase"] for kw in l2_cluster)

            elif verdict_type == "related_nuance":
                results.append({
                    "tier": "subheading_group",
                    "sub_silo": sub_silo_id,
                    "cluster": l2_cluster,
                    "broadest": pick_broadest_phrase(l2_cluster),
                })
                used_in_tight_cluster.update(kw["phrase"] for kw in l2_cluster)

            else:  # "different" — LLM split it
                groups = verdict.get("groups", []) if isinstance(verdict, dict) else []
                phrase_to_kw = {kw["phrase"]: kw for kw in l2_cluster}
                for group in groups:
                    group_kws = [phrase_to_kw[p] for p in group if p in phrase_to_kw]
                    if group_kws:
                        used_in_tight_cluster.update(kw["phrase"] for kw in group_kws)
                # fall through — these remain in the Level-1 cluster as "related" below

        # everything not absorbed into a Tier 1/2 group is "related"
        leftovers = [kw for kw in l1_cluster if kw["phrase"] not in used_in_tight_cluster]
        if leftovers:
            results.append({
                "tier": "related",
                "sub_silo": sub_silo_id,
                "cluster_group_id": f"silo-{sub_silo_id}",
                "members": leftovers,
            })

    return results
