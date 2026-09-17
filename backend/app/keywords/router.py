import uuid
import io
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import csv
from datetime import datetime, timedelta
from app.database import get_db
from app.models import User, Project, Keyword, KeywordUrl, Url, KeywordBank
from app.schemas import KeywordOut, KeywordListResponse, KeywordSourceOut, SaveKeywordRequest, KeywordBulkSaveRequest, KeywordBankBulkActionRequest, KeywordBulkDeleteRequest
from app.auth.jwt import get_current_user
from app.config import settings
from nlp.keywords import is_publishable_keyword, seed_keyword_terms
from nlp.openrouter import ai_generated_source, generate_ai_keywords

router = APIRouter(prefix="/api/projects", tags=["keywords"])
bank_router = APIRouter(prefix="/api/keyword-bank", tags=["keywords"])


@router.get("/{project_id}/keywords", response_model=KeywordListResponse)
async def list_keywords(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    sort_by: str = Query(
        "frequency",
        enum=["frequency", "phrase", "created_at", "search_volume_asc", "search_volume_desc"],
    ),
    keyword_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)

    q = select(Keyword).where(Keyword.project_id == project_id)
    if keyword_type:
        q = q.where(Keyword.keyword_type == keyword_type)
    if search:
        search_terms = [t.strip() for t in search.split() if t.strip()]
        for term in search_terms:
            q = q.where(Keyword.phrase.ilike(f"%{term}%"))

    result = await db.execute(q)
    filtered_keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword)
    ]

    if sort_by == "frequency":
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", -k.frequency))
    elif sort_by == "phrase":
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", k.phrase))
    elif sort_by == "search_volume_asc":
        filtered_keywords.sort(key=lambda k: (k.search_volume is None, k.search_volume or 0))
    elif sort_by == "search_volume_desc":
        filtered_keywords.sort(key=lambda k: (k.search_volume is None, -(k.search_volume or 0)))
    else:
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", -k.created_at.timestamp()))

    total = len(filtered_keywords)
    start = (page - 1) * page_size
    keywords = filtered_keywords[start:start + page_size]

    sources_by_keyword = await _keyword_sources_map(db, [kw.id for kw in keywords], limit_per_keyword=10)
    items = []
    for kw in keywords:
        sources = sources_by_keyword.get(kw.id, [])
        kw_out = KeywordOut.model_validate(kw)
        kw_out.source_urls = [source.url for source in sources]
        kw_out.sources = sources
        items.append(kw_out)

    return KeywordListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.post("/{project_id}/keywords/generate")
async def generate_keywords(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    if not project.target_keywords:
        raise HTTPException(status_code=400, detail="Project has no target keywords to generate from")
        
    from nlp.openrouter import generate_core_domain_terms
    from nlp.keywords import normalize_seed_keywords, seed_keyword_terms
    seed_keywords = normalize_seed_keywords(project.target_keywords)
    
    semantic_res = await generate_core_domain_terms(seed_keywords, project.audit_summary)
    topic_terms = set(semantic_res.get("core_terms", []))
    negative_terms = set(semantic_res.get("negative_terms", []))
    if not topic_terms:
        topic_terms = seed_keyword_terms(seed_keywords)
        
    ai_keywords = await generate_ai_keywords(
        seed_keywords,
        topic_terms=topic_terms,
        negative_terms=negative_terms,
        audit_summary=project.audit_summary,
        apply_gap_filter=False,
        target_count=min(60, settings.AI_KEYWORD_GENERATION_BATCH_SIZE),
    )
    # Get existing keyword phrases in this project to avoid duplicates
    q_existing = select(Keyword.phrase).where(Keyword.project_id == project.id)
    result = await db.execute(q_existing)
    existing_phrases = {row[0] for row in result.all()}
    
    # Keep the semantic terms derived from the audit. Replacing them with
    # seed-only terms here discarded useful context during manual generation.
    q_own_urls = select(Url.url).where(Url.project_id == project.id, Url.source_type == "own")
    result = await db.execute(q_own_urls)
    own_urls = result.scalars().all()
    
    from workers.pipeline import _url_keyword_candidates
    own_phrases: set[str] = set()
    for url in own_urls:
        own_phrases.update(_url_keyword_candidates(url, topic_terms, negative_terms, include_single_terms=True))
    
    # Combine both sets for filtering
    all_excluded = existing_phrases | own_phrases
    ai_keywords = [kw for kw in ai_keywords if kw["phrase"] not in all_excluded]

    collected = {kw["phrase"]: kw for kw in ai_keywords}
    target_total = max(100, settings.MIN_KEYWORDS_PER_SCAN)
    for _ in range(max(1, settings.AI_KEYWORD_GENERATION_MAX_BATCHES - 1)):
        if len(existing_phrases) + len(collected) >= target_total:
            break
        batch = await generate_ai_keywords(
            seed_keywords,
            topic_terms=topic_terms,
            negative_terms=negative_terms,
            audit_summary=project.audit_summary,
            apply_gap_filter=False,
            target_count=settings.AI_KEYWORD_GENERATION_BATCH_SIZE,
            exclude_phrases=all_excluded | set(collected),
            evidence_phrases=sorted(existing_phrases),
        )
        for item in batch:
            if item["phrase"] not in all_excluded:
                collected[item["phrase"]] = item

    ai_keywords = list(collected.values())
        
    # Get or create an AI source URL
    ai_url_str, ai_source_domain = ai_generated_source()
    q_url = select(Url).where(Url.project_id == project.id, Url.url == ai_url_str)
    result = await db.execute(q_url)
    ai_url = result.scalar_one_or_none()
    
    if not ai_url:
        ai_url = Url(
            project_id=project.id,
            url=ai_url_str,
            source_type="ai",
            source_domain=ai_source_domain,
            status="scraped",
        )
        db.add(ai_url)
        await db.flush()
        
    candidate_phrases = [item["phrase"] for item in ai_keywords]
    keyword_result = await db.execute(select(Keyword).where(
        Keyword.project_id == project.id,
        Keyword.phrase.in_(candidate_phrases),
    ))
    keywords_by_phrase = {keyword.phrase: keyword for keyword in keyword_result.scalars().all()}
    new_keywords = []
    for kw_data in ai_keywords:
        phrase = kw_data["phrase"]
        if phrase not in keywords_by_phrase:
            keyword = Keyword(
                project_id=project.id,
                phrase=phrase,
                keyword_type=kw_data["type"],
                frequency=1,
            )
            db.add(keyword)
            keywords_by_phrase[phrase] = keyword
            new_keywords.append(keyword)
    if new_keywords:
        await db.flush()

    candidate_ids = [keywords_by_phrase[phrase].id for phrase in candidate_phrases]
    linked_result = await db.execute(select(KeywordUrl.keyword_id).where(
        KeywordUrl.url_id == ai_url.id,
        KeywordUrl.keyword_id.in_(candidate_ids),
    ))
    linked_ids = set(linked_result.scalars().all())
    db.add_all([
        KeywordUrl(keyword_id=keyword_id, url_id=ai_url.id)
        for keyword_id in candidate_ids if keyword_id not in linked_ids
    ])
    added_count = len(new_keywords)
            
    project.total_keywords = (
        await db.execute(select(func.count(Keyword.id)).where(Keyword.project_id == project.id))
    ).scalar_one()
    await db.commit()
    return {"message": f"Generated {added_count} new keywords", "generated": added_count}


@router.post("/{project_id}/keywords/seo-enrich")
async def enrich_keywords_seo(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enrich keywords with SEO data (search volume, difficulty, AI recommendation) via DeepSeek."""
    project = await _assert_owns_project(project_id, current_user.id, db)

    from nlp.deepseek_seo import enrich_keywords_with_seo_data, is_deepseek_configured
    if not is_deepseek_configured():
        raise HTTPException(status_code=503, detail="DeepSeek API is not configured. Add DEEPSEEK_API_KEY to your environment.")

    from nlp.keywords import normalize_seed_keywords
    seed_keywords = normalize_seed_keywords(project.target_keywords) if project.target_keywords else []

    # Fetch keywords that don't have search_volume yet
    result = await db.execute(
        select(Keyword.id, Keyword.phrase).where(
            Keyword.project_id == project.id,
            Keyword.search_volume.is_(None),
        )
    )
    unenriched = result.all()

    if not unenriched:
        return {"message": "All keywords already have SEO data", "enriched": 0}

    phrases = [row[1] for row in unenriched]
    phrase_to_id = {row[1].strip().lower(): row[0] for row in unenriched}

    seo_data = enrich_keywords_with_seo_data(
        phrases,
        seed_keywords,
        audit_summary=project.audit_summary,
    )

    from sqlalchemy import update as sa_update
    enriched_count = 0
    for phrase_lower, data in seo_data.items():
        kw_id = phrase_to_id.get(phrase_lower)
        if kw_id:
            await db.execute(
                sa_update(Keyword).where(Keyword.id == kw_id).values(
                    search_volume=data.get("search_volume"),
                    difficulty=data.get("difficulty"),
                    seo_recommendation=data.get("recommendation"),
                )
            )
            enriched_count += 1

    await db.commit()
    return {"message": f"Enriched {enriched_count} keywords with SEO data", "enriched": enriched_count}


@router.post("/{project_id}/keywords/top-picks")
async def generate_top_picks(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    if not project.target_keywords:
        raise HTTPException(status_code=400, detail="Project has no target keywords to generate from")
        
    # 1. Fetch existing keyword phrases
    q_existing = select(Keyword.phrase).where(Keyword.project_id == project.id)
    result = await db.execute(q_existing)
    existing_phrases = [row[0] for row in result.all()]
    
    if len(existing_phrases) < 5:
        raise HTTPException(status_code=400, detail="Not enough keywords found yet. Please run a competitor scan or generate keywords first.")

    # 2. Ask AI to pick top keywords FROM existing phrases
    from nlp.openrouter import generate_core_domain_terms, generate_ai_top_picks
    from nlp.keywords import normalize_seed_keywords, seed_keyword_terms
    seed_keywords = normalize_seed_keywords(project.target_keywords)
    
    semantic_res = await generate_core_domain_terms(seed_keywords, project.audit_summary)
    topic_terms = set(semantic_res.get("core_terms", []))
    negative_terms = set(semantic_res.get("negative_terms", []))
    if not topic_terms:
        topic_terms = seed_keyword_terms(seed_keywords)
        
    ai_keywords = await generate_ai_top_picks(
        seed_keywords,
        existing_phrases,
        topic_terms=topic_terms,
        negative_terms=negative_terms
    )
    if not ai_keywords:
        raise HTTPException(status_code=500, detail="Failed to generate AI top picks")
        
    # Get or create an AI source URL for Top Picks
    from nlp.openrouter import ai_generated_source
    ai_url_str, ai_source_domain = ai_generated_source()
    q_url = select(Url).where(Url.project_id == project.id, Url.url == ai_url_str)
    result = await db.execute(q_url)
    ai_url = result.scalar_one_or_none()
    
    if not ai_url:
        ai_url = Url(
            project_id=project.id,
            url=ai_url_str,
            source_type="ai",
            source_domain="Top Picks",
            status="scraped",
        )
        db.add(ai_url)
        await db.flush()
        
    selected_phrases = [item["phrase"] for item in ai_keywords]
    selected_result = await db.execute(select(Keyword).where(
        Keyword.project_id == project.id,
        Keyword.phrase.in_(selected_phrases),
    ))
    selected_keywords = list(selected_result.scalars().all())
    for keyword in selected_keywords:
        keyword.keyword_type = "top-pick"

    selected_ids = [keyword.id for keyword in selected_keywords]
    linked_result = await db.execute(select(KeywordUrl.keyword_id).where(
        KeywordUrl.url_id == ai_url.id,
        KeywordUrl.keyword_id.in_(selected_ids),
    ))
    linked_ids = set(linked_result.scalars().all())
    db.add_all([
        KeywordUrl(keyword_id=keyword_id, url_id=ai_url.id)
        for keyword_id in selected_ids if keyword_id not in linked_ids
    ])
    updated_count = len(selected_keywords)
            
    await db.commit()
    return {"message": f"Identified {updated_count} existing keywords as top picks", "generated": updated_count}


@router.post("/{project_id}/keywords/hub-spoke")
async def generate_hub_spoke(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    
    # We need to know if the keyword came from an AI recommendation + tier info
    from app.models import Keyword, KeywordUrl, Url
    q_existing = (
        select(
            Keyword.phrase, Keyword.keyword_type, Url.source_domain,
            Keyword.tier, Keyword.article_title, Keyword.h_tags,
            Keyword.merged_from, Keyword.cluster_group_id, Keyword.sub_silo_id,
        )
        .outerjoin(KeywordUrl, Keyword.id == KeywordUrl.keyword_id)
        .outerjoin(Url, KeywordUrl.url_id == Url.id)
        .where(Keyword.project_id == project.id)
        .order_by(Keyword.frequency.desc())
    )
    result = await db.execute(q_existing)
    
    keyword_map = {}
    for phrase, kw_type, domain, tier, article_title, h_tags, merged_from, cluster_group_id, sub_silo_id in result.all():
        if phrase not in keyword_map:
            keyword_map[phrase] = {
                "phrase": phrase, "type": kw_type, "is_ai": False,
                "tier": tier, "article_title": article_title,
                "h_tags": h_tags, "merged_from": merged_from,
                "cluster_group_id": cluster_group_id,
                "sub_silo_id": sub_silo_id,
            }
        if domain == "AI Recommendations":
            keyword_map[phrase]["is_ai"] = True
            
    existing_keywords = list(keyword_map.values())
    
    import re

    # Phase 1: Filter

    h2_map = {}

    from nlp.openrouter import generate_core_domain_terms
    from nlp.keywords import normalize_seed_keywords
    seed_keywords = normalize_seed_keywords(project.target_keywords)
    semantic_res = await generate_core_domain_terms(seed_keywords, project.audit_summary)
    topic_terms = set(semantic_res.get("core_terms", [])) | seed_keyword_terms(seed_keywords)
    negative_terms = set(semantic_res.get("negative_terms", []))
    from nlp.keywords import is_topic_relevant_keyword
    
    clean_candidates = []
    for kw in existing_keywords:
        phrase_lower = kw["phrase"].lower()
        if not is_topic_relevant_keyword(phrase_lower, seed_keywords, topic_terms, negative_terms):
            continue
        
        # Retroactive garbage collection: block any keywords containing negative terms
        phrase_terms = set(re.findall(r'[a-z0-9]+', phrase_lower))
        if phrase_terms & negative_terms:
            continue
            
        if not is_publishable_keyword(phrase_lower, min_words=2):
            continue

        extras = []
        if kw.get("merged_from"):
            extras.extend(kw["merged_from"])
        if kw.get("h_tags"):
            extras.extend(kw["h_tags"])
        if extras:
            h2_map[phrase_lower] = extras
            
        clean_candidates.append(kw)

    if not clean_candidates:
        raise HTTPException(status_code=400, detail="No valid parent keywords found after filtering.")

    # Phase 2: Send to LLM
    # Keep placement decisions (H2 vs FAQ vs entity) inside one coherent plan.
    top_candidates = clean_candidates[:500]
    remaining = clean_candidates[500:]
    
    clean_keywords_for_llm = [
        {"phrase": kw["phrase"], "type": kw["type"], "is_ai": kw["is_ai"]}
        for kw in top_candidates
    ]

    # Phase 3: The AI Skeleton
    from nlp.openrouter import cluster_hub_and_spoke
    main_kw = seed_keywords[0] if seed_keywords else project.name
    clusters = await cluster_hub_and_spoke(clean_keywords_for_llm, main_keyword=main_kw, audit_summary=project.audit_summary)
    if not clusters:
        raise HTTPException(status_code=500, detail="Failed to cluster keywords")
    detailed_architecture = isinstance(clusters.get("master_hub"), dict) and isinstance(clusters.get("spokes"), list)

    # Phase 4: Auto-Map Remaining Keywords
    if remaining and not detailed_architecture and "hubs" in clusters and isinstance(clusters["hubs"], list) and len(clusters["hubs"]) > 0:
        from nlp.keywords import phrase_similarity
        import re
        
        placed_nodes = []
        
        for h_idx, hub in enumerate(clusters["hubs"]):
            # Do not place things randomly into NOISE bin unless explicitly needed
            if "NOISE" in hub.get("hub_title", "").upper():
                continue
                
            layers = hub.get("layers", {})
            for layer_name, spokes in layers.items():
                for spoke in spokes:
                    match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                    if match:
                        placed_nodes.append({
                            "hub_idx": h_idx,
                            "sub_silo_idx": None,
                            "layer_name": layer_name,
                            "target_kw": match.group(1).strip()
                        })
            
            sub_silos = hub.get("sub_silos", [])
            for s_idx, silo in enumerate(sub_silos):
                silo_layers = silo.get("layers", {})
                for layer_name, spokes in silo_layers.items():
                    for spoke in spokes:
                        match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                        if match:
                            placed_nodes.append({
                                "hub_idx": h_idx,
                                "sub_silo_idx": s_idx,
                                "layer_name": layer_name,
                                "target_kw": match.group(1).strip()
                            })

        for kw in remaining:
            phrase = kw["phrase"]
            if not placed_nodes:
                continue
            best_target = max(
                placed_nodes,
                key=lambda node: phrase_similarity(phrase, node["target_kw"]),
            )["target_kw"]
            # The editorial plan is capped at 20 spokes. Keywords outside the
            # model batch enrich the closest existing article instead of
            # silently creating hundreds of extra URLs.
            h2_map.setdefault(best_target.lower(), []).append(phrase)

    # Phase 5: Semantic Deduplication (The Bouncer)
    def semantic_tokenize(phrase: str) -> list[str]:
        slug = re.sub(r'[^\w]+', '-', phrase.lower()).strip('-')
        tokens = slug.split('-')
        
        # Layer 2: Synonym Normalization
        synonym_map = {
            "guide": "tutorial",
            "understanding": "meaning",
            "meanings": "meaning",
            "test": "quiz",
            "software": "maker",
            "tool": "maker",
            "tools": "maker",
            "best": "top",
            "creator": "maker",
            "creators": "maker",
            "builder": "maker",
            "builders": "maker",
            "generator": "maker",
            "generators": "maker",
            "service": "agency",
            "services": "agency",
            "company": "agency",
            "companies": "agency",
            "online": "web"
        }
        
        stopwords = {
            "how", "to", "use", "for", "and", "vs", "the", "of", "a", "an", "is", "what", "with", "in", "on", "at"
        }
        
        filtered = []
        for t in tokens:
            if not t or t in stopwords:
                continue
                
            # Basic stemming: remove trailing 's' (unless it ends in 'ss')
            if t.endswith('s') and not t.endswith('ss') and len(t) > 3:
                t = t[:-1]
                
            # Apply synonym map
            mapped_t = synonym_map.get(t, t)
            filtered.append(mapped_t)
                
        # Layer 1: Sorted to catch swapped words
        return sorted(filtered)

    seen_tokens_map = {}
    
    def clean_hub_title(title: str) -> str:
        title = re.sub(r'^(📍 MASTER HUB:|🪐 SUB-SILO \d+:)\s*', '', title)
        return title.split('—')[0].strip()

    def check_duplicate(phrase: str) -> str | None:
        """Returns the original phrase of the survivor if duplicate, else None."""
        tokens = semantic_tokenize(phrase)
        if not tokens:
            return None
            
        phrase_normalized = " ".join(tokens)
        
        for seen_tokens, survivor_phrase in seen_tokens_map.items():
            seen_normalized = " ".join(seen_tokens)
            
            # Layer 1 & Layer 2: Exact match after swapping and synonyms
            if phrase_normalized == seen_normalized:
                return survivor_phrase
                
            # Layer 3: strong token overlap. Subset matching was too aggressive
            # and collapsed distinct long-tail search intents.
            set1 = set(tokens)
            set2 = set(seen_tokens)
            intersection = set1.intersection(set2)
            union = set1.union(set2)
            if union and (len(intersection) / len(union)) >= 0.80:
                return survivor_phrase
                
        return None

    def add_to_seen(phrase: str):
        tokens = semantic_tokenize(phrase)
        if tokens:
            seen_tokens_map[tuple(tokens)] = phrase

    # The detailed architect has already assigned H2, FAQ, and entity terms.
    # The old card-only dedup pass would desynchronise those assignments.
    if not detailed_architecture and clusters and "hubs" in clusters and isinstance(clusters["hubs"], list):
        def inject_h2s(spoke_str: str, target_kw: str) -> str:
            extras = h2_map.get(target_kw.lower(), [])
            if extras:
                # Deduplicate H2s uniquely to avoid repetitive appends
                unique_extras = list(dict.fromkeys(extras))
                if "[Include:" in spoke_str:
                    spoke_str = re.sub(r'\]\s*$', f", {', '.join(unique_extras)}]", spoke_str)
                else:
                    spoke_str += f" [Include: {', '.join(unique_extras)}]"
            return spoke_str

        surviving_spokes_map = [] # stores dicts: {"node": layer_dict, "layer_name": name, "spoke": str, "target_kw": str}
        
        for hub in clusters["hubs"]:
            if "layers" in hub and isinstance(hub["layers"], dict):
                for layer_name, spokes in hub["layers"].items():
                    hub["layers"][layer_name] = [] # clear for pass 2
                    for spoke in spokes:
                        match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                        if match:
                            target_kw = match.group(1).strip()
                            title = spoke[:match.start()].strip()
                            survivor_target = check_duplicate(target_kw)
                            survivor_title = check_duplicate(title)
                            survivor = survivor_target or survivor_title
                            if not survivor:
                                add_to_seen(target_kw)
                                add_to_seen(title)
                                surviving_spokes_map.append({"node": hub["layers"], "layer_name": layer_name, "spoke": spoke, "target_kw": target_kw})
                            else:
                                if survivor.lower() not in h2_map:
                                    h2_map[survivor.lower()] = []
                                h2_map[survivor.lower()].append(target_kw.title())
                        else:
                            survivor = check_duplicate(spoke)
                            if not survivor:
                                add_to_seen(spoke)
                                surviving_spokes_map.append({"node": hub["layers"], "layer_name": layer_name, "spoke": spoke, "target_kw": spoke})
                            else:
                                if survivor.lower() not in h2_map:
                                    h2_map[survivor.lower()] = []
                                h2_map[survivor.lower()].append(spoke.title())
            
            if "sub_silos" in hub and isinstance(hub["sub_silos"], list):
                for silo in hub["sub_silos"]:
                    if "layers" in silo and isinstance(silo["layers"], dict):
                        for layer_name, spokes in silo["layers"].items():
                            silo["layers"][layer_name] = [] # clear for pass 2
                            for spoke in spokes:
                                match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                                if match:
                                    target_kw = match.group(1).strip()
                                    title = spoke[:match.start()].strip()
                                    survivor_target = check_duplicate(target_kw)
                                    survivor_title = check_duplicate(title)
                                    survivor = survivor_target or survivor_title
                                    if not survivor:
                                        add_to_seen(target_kw)
                                        add_to_seen(title)
                                        surviving_spokes_map.append({"node": silo["layers"], "layer_name": layer_name, "spoke": spoke, "target_kw": target_kw})
                                    else:
                                        if survivor.lower() not in h2_map:
                                            h2_map[survivor.lower()] = []
                                        h2_map[survivor.lower()].append(target_kw.title())
                                else:
                                    survivor = check_duplicate(spoke)
                                    if not survivor:
                                        add_to_seen(spoke)
                                        surviving_spokes_map.append({"node": silo["layers"], "layer_name": layer_name, "spoke": spoke, "target_kw": spoke})
                                    else:
                                        if survivor.lower() not in h2_map:
                                            h2_map[survivor.lower()] = []
                                        h2_map[survivor.lower()].append(spoke.title())

        # Pass 2: Inject all H2s into surviving spokes
        for s in surviving_spokes_map:
            s["node"][s["layer_name"]].append(inject_h2s(s["spoke"], s["target_kw"]))

    from nlp.openrouter import _validate_hub_and_spoke, build_hub_spoke_fallback
    allowed_keywords = {
        ("entity:" if kw.get("type") == "entity" else "") + kw["phrase"]
        for kw in existing_keywords
    }
    validation_error = _validate_hub_and_spoke(
        clusters,
        len(existing_keywords),
        main_keyword=main_kw,
        allowed_keywords=allowed_keywords,
    )
    if validation_error:
        clusters = build_hub_spoke_fallback(clean_candidates, main_kw)
        validation_error = _validate_hub_and_spoke(
            clusters,
            len(clean_candidates),
            main_keyword=main_kw,
            allowed_keywords={
                ("entity:" if kw.get("type") == "entity" else "") + kw["phrase"]
                for kw in clean_candidates
            },
        )
        if validation_error:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to build a constraint-safe hub map: {validation_error}",
            )

    from app.models import HubSpokeCluster
    q_cluster = select(HubSpokeCluster).where(HubSpokeCluster.project_id == project.id)
    res_cluster = await db.execute(q_cluster)
    cluster_record = res_cluster.scalar_one_or_none()
    
    if cluster_record:
        cluster_record.mapping_data = clusters
    else:
        cluster_record = HubSpokeCluster(project_id=project.id, mapping_data=clusters)
        db.add(cluster_record)
        
    await db.commit()
    return {"message": "Clustered successfully", "clusters": clusters}


@router.get("/{project_id}/keywords/hub-spoke")
async def get_hub_spoke(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    
    from app.models import HubSpokeCluster, Keyword
    q_cluster = select(HubSpokeCluster).where(HubSpokeCluster.project_id == project.id)
    res_cluster = await db.execute(q_cluster)
    cluster_record = res_cluster.scalar_one_or_none()
    
    # Build tier metadata for the frontend
    tier_q = (
        select(Keyword.phrase, Keyword.tier, Keyword.article_title,
               Keyword.h_tags, Keyword.merged_from, Keyword.cluster_group_id,
               Keyword.sub_silo_id, Keyword.keyword_type)
        .where(Keyword.project_id == project.id, Keyword.tier.isnot(None))
    )
    tier_result = await db.execute(tier_q)
    tier_metadata = {}
    for phrase, tier, article_title, h_tags, merged_from, cluster_group_id, sub_silo_id, kw_type in tier_result.all():
        tier_metadata[phrase] = {
            "tier": tier,
            "article_title": article_title,
            "h_tags": h_tags,
            "merged_from": merged_from,
            "cluster_group_id": cluster_group_id,
            "sub_silo_id": sub_silo_id,
            "keyword_type": kw_type,
        }
    
    return {
        "clusters": cluster_record.mapping_data if cluster_record else None,
        "tier_metadata": tier_metadata,
    }



@router.get("/{project_id}/keywords/export")
async def export_keywords(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)

    result = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .order_by(Keyword.frequency.desc())
    )
    keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword)
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Keyword Gap",
        "Type",
        "Competitor Pages",
        "Source Domains",
        "Source URLs",
        "Search Volume",
        "Difficulty",
    ])
    sources_by_keyword = await _keyword_sources_map(db, [kw.id for kw in keywords])
    for kw in keywords:
        sources = sources_by_keyword.get(kw.id, [])
        source_domains = sorted(dict.fromkeys(_source_label(source) for source in sources))
        writer.writerow([
            kw.phrase,
            kw.keyword_type,
            kw.frequency,
            "; ".join(source_domains),
            "; ".join(source.url for source in sources),
            kw.search_volume or "",
            kw.difficulty or "",
        ])

    output.seek(0)
    # A regular response releases the DB session immediately. The former sync
    # StreamingResponse kept the connection open while Render sent the file and
    # amplified intermittent hosted-Postgres SSL disconnects.
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=keywords-{project_id}.csv"},
    )


@router.post("/{project_id}/keywords/{keyword_id}/save", status_code=201)
async def save_keyword(
    project_id: uuid.UUID,
    keyword_id: uuid.UUID,
    body: SaveKeywordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)

    kw_result = await db.execute(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.project_id == project_id)
    )
    if not kw_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Keyword not found")

    existing = await db.execute(
        select(KeywordBank).where(
            KeywordBank.user_id == current_user.id,
            KeywordBank.keyword_id == keyword_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Already saved"}

    entry = KeywordBank(user_id=current_user.id, keyword_id=keyword_id, notes=body.notes)
    db.add(entry)
    return {"message": "Keyword saved to bank"}

@router.post("/{project_id}/keywords/bulk-save", status_code=201)
async def bulk_save_keywords(
    project_id: uuid.UUID,
    body: KeywordBulkSaveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)

    # Filter out keywords that don't exist in the project
    kw_result = await db.execute(
        select(Keyword.id).where(Keyword.id.in_(body.keyword_ids), Keyword.project_id == project_id)
    )
    valid_ids = [row[0] for row in kw_result.all()]

    if not valid_ids:
        return {"message": "No valid keywords found"}

    # Find already saved keywords
    existing_result = await db.execute(
        select(KeywordBank.keyword_id).where(
            KeywordBank.user_id == current_user.id,
            KeywordBank.keyword_id.in_(valid_ids)
        )
    )
    existing_ids = {row[0] for row in existing_result.all()}

    # Create new entries
    new_entries = [
        KeywordBank(user_id=current_user.id, keyword_id=kw_id, notes=body.notes)
        for kw_id in valid_ids if kw_id not in existing_ids
    ]
    
    if new_entries:
        db.add_all(new_entries)
        
    return {"message": f"{len(new_entries)} keywords saved to bank"}


@router.post("/{project_id}/keywords/bulk-delete")
async def bulk_delete_keywords(
    project_id: uuid.UUID,
    body: KeywordBulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_owns_project(project_id, current_user.id, db)
    
    if not body.keyword_ids:
        return {"message": "No keywords to delete"}

    # Fetch keywords first to get their phrases so we can remove them from HubSpoke
    q_kw = select(Keyword).where(
        Keyword.id.in_(body.keyword_ids),
        Keyword.project_id == project_id,
    )
    res_kw = await db.execute(q_kw)
    keywords_to_delete = res_kw.scalars().all()
    phrases_to_remove = {k.phrase for k in keywords_to_delete}
    valid_ids = [keyword.id for keyword in keywords_to_delete]

    if not valid_ids:
        return {"message": "No matching keywords to delete"}
    
    # Keyword deletion will cascade to KeywordUrl automatically if configured, 
    # but we can manually delete from Keyword to be safe
    from sqlalchemy import delete
    
    # Delete KeywordUrls first to be completely safe against FK constraints
    await db.execute(
        delete(KeywordUrl).where(KeywordUrl.keyword_id.in_(valid_ids))
    )
    
    # Delete KeywordBank entries associated with these keywords
    await db.execute(
        delete(KeywordBank).where(KeywordBank.keyword_id.in_(valid_ids))
    )
    
    # Finally delete the keywords themselves
    result = await db.execute(
        delete(Keyword).where(
            Keyword.id.in_(valid_ids),
            Keyword.project_id == project_id
        )
    )
    
    # Update HubSpoke mapping to remove deleted phrases
    if phrases_to_remove:
        from app.models import HubSpokeCluster
        import copy
        
        q_cluster = select(HubSpokeCluster).where(HubSpokeCluster.project_id == project_id)
        res_cluster = await db.execute(q_cluster)
        cluster_record = res_cluster.scalar_one_or_none()
        
        if cluster_record and cluster_record.mapping_data:
            data = copy.deepcopy(cluster_record.mapping_data)
            
            # Handle new 3-Layer Schema
            if isinstance(data, dict) and "hubs" in data:
                for hub_item in data["hubs"]:
                    layers = hub_item.get("layers", {})
                    for layer_name, spokes in list(layers.items()):
                        # Keep spokes that DO NOT contain any of the deleted phrases
                        new_spokes = []
                        for spoke in spokes:
                            should_delete = any(f"(Target Keyword: {phrase})" in spoke for phrase in phrases_to_remove)
                            if not should_delete:
                                new_spokes.append(spoke)
                        
                        if new_spokes:
                            layers[layer_name] = new_spokes
                        else:
                            # If a layer is completely empty, keep the layer key but empty array
                            layers[layer_name] = []
                            
            cluster_record.mapping_data = data
            
    await db.commit()
    
    return {"message": f"Successfully deleted {len(valid_ids)} keyword{'s' if len(valid_ids) != 1 else ''}"}


@bank_router.get("")
async def get_keyword_bank(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    two_days_ago = datetime.utcnow() - timedelta(days=2)
    
    result = await db.execute(
        select(KeywordBank, Keyword)
        .join(Keyword, Keyword.id == KeywordBank.keyword_id)
        .where(
            KeywordBank.user_id == current_user.id,
            ~((KeywordBank.is_done == True) & (KeywordBank.done_at < two_days_ago))
        )
        .order_by(KeywordBank.saved_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": str(bank.id),
            "keyword_id": str(kw.id),
            "project_id": str(kw.project_id),
            "phrase": kw.phrase,
            "keyword_type": kw.keyword_type,
            "frequency": kw.frequency,
            "notes": bank.notes,
            "saved_at": bank.saved_at.isoformat(),
            "is_done": bank.is_done,
            "done_at": bank.done_at.isoformat() if bank.done_at else None,
        }
        for bank, kw in rows
        if _is_displayable_keyword(kw)
    ]

from sqlalchemy import update, delete

@bank_router.post("/bulk-action")
async def bulk_action_keyword_bank(
    body: KeywordBankBulkActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.keyword_bank_ids:
        return {"message": "No keywords selected"}
        
    if body.action == "delete":
        await db.execute(
            delete(KeywordBank).where(
                KeywordBank.id.in_(body.keyword_bank_ids),
                KeywordBank.user_id == current_user.id
            )
        )
    elif body.action == "mark_done":
        await db.execute(
            update(KeywordBank).where(
                KeywordBank.id.in_(body.keyword_bank_ids),
                KeywordBank.user_id == current_user.id
            ).values(is_done=True, done_at=datetime.utcnow())
        )
    elif body.action == "mark_not_done":
        await db.execute(
            update(KeywordBank).where(
                KeywordBank.id.in_(body.keyword_bank_ids),
                KeywordBank.user_id == current_user.id
            ).values(is_done=False, done_at=None)
        )
        
    return {"message": f"Action {body.action} completed successfully"}


def _is_displayable_keyword(keyword: Keyword) -> bool:
    return is_publishable_keyword(keyword.phrase, min_words=2)


async def _keyword_sources_map(
    db: AsyncSession,
    keyword_ids: list[uuid.UUID],
    limit_per_keyword: int | None = None,
) -> dict[uuid.UUID, list[KeywordSourceOut]]:
    """Fetch sources for a page or export in one query instead of one per keyword."""
    if not keyword_ids:
        return {}
    result = await db.execute(
        select(KeywordUrl.keyword_id, Url.url, Url.source_type, Url.source_domain)
        .join(Url, Url.id == KeywordUrl.url_id)
        .where(KeywordUrl.keyword_id.in_(keyword_ids))
        .order_by(KeywordUrl.keyword_id, Url.source_domain.asc().nullslast(), Url.url.asc())
    )
    grouped: dict[uuid.UUID, list[KeywordSourceOut]] = {keyword_id: [] for keyword_id in keyword_ids}
    for keyword_id, url, source_type, source_domain in result.all():
        sources = grouped.setdefault(keyword_id, [])
        if limit_per_keyword is not None and len(sources) >= limit_per_keyword:
            continue
        sources.append(KeywordSourceOut(
            url=url,
            source_type=source_type,
            source_domain=source_domain or _source_origin(url),
        ))
    return grouped


def _source_label(source: KeywordSourceOut) -> str:
    return source.source_domain or _source_origin(source.url) or source.url


def _source_origin(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


async def _assert_owns_project(project_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
