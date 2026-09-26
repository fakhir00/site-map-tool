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
    page_size: int = Query(50, ge=1, le=200),
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

    # One SEO architecture agent now owns relevance, keyword disposition,
    # page intent, cannibalization checks, and the final hub-spoke map.
    from app.models import HubSpokeCluster
    from nlp.hub_spoke_agent import ArchitectureAgentError, build_site_architecture
    result = await db.execute(
        select(
            Keyword.phrase,
            Keyword.keyword_type,
            Keyword.search_volume,
            Keyword.difficulty,
            Keyword.frequency,
        )
        .where(Keyword.project_id == project.id)
        .order_by(Keyword.frequency.desc(), Keyword.created_at.asc())
        .limit(5000)
    )
    records = [{
        "phrase": phrase,
        "type": keyword_type,
        "search_volume": search_volume,
        "difficulty": difficulty,
        "frequency": frequency,
    } for phrase, keyword_type, search_volume, difficulty, frequency in result.all()]
    if not records:
        raise HTTPException(status_code=400, detail="This project has no keywords to architect.")
    main_kw = (project.target_keywords or [project.name])[0]
    from app.hub_spoke.context import context_with_owned_pages
    architecture_context = await context_with_owned_pages(db, project.id, project.audit_summary or "")
    try:
        clusters = await build_site_architecture(
            records,
            context=architecture_context,
            primary_keyword=main_kw,
            target_spokes=25,
            site_domain=project.own_domain or project.domain,
        )
    except ArchitectureAgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    cluster_result = await db.execute(select(HubSpokeCluster).where(HubSpokeCluster.project_id == project.id))
    cluster_record = cluster_result.scalar_one_or_none()
    if cluster_record:
        cluster_record.mapping_data = clusters
    else:
        db.add(HubSpokeCluster(project_id=project.id, mapping_data=clusters))
    await db.commit()
    return {"message": "SEO architecture created", "clusters": clusters}
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
            len({source.url for source in sources if source.source_type == "competitor"}),
            "; ".join(source_domains),
            "; ".join(source.url for source in sources),
            kw.search_volume if kw.search_volume is not None else "",
            kw.difficulty if kw.difficulty is not None else "",
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
