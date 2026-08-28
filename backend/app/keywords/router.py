import uuid
import io
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import csv
from datetime import datetime, timedelta
from app.database import get_db
from app.models import User, Project, Keyword, KeywordUrl, Url, KeywordBank
from app.schemas import KeywordOut, KeywordListResponse, KeywordSourceOut, SaveKeywordRequest, KeywordBulkSaveRequest, KeywordBankBulkActionRequest, KeywordBulkDeleteRequest
from app.auth.jwt import get_current_user
from nlp.keywords import is_publishable_keyword, seed_keyword_terms
from nlp.openrouter import ai_generated_source, generate_ai_keywords

router = APIRouter(prefix="/api/projects", tags=["keywords"])
bank_router = APIRouter(prefix="/api/keyword-bank", tags=["keywords"])


@router.get("/{project_id}/keywords", response_model=KeywordListResponse)
async def list_keywords(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    sort_by: str = Query("frequency", enum=["frequency", "phrase", "created_at"]),
    keyword_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _assert_owns_project(project_id, current_user.id, db)
    topic_terms = seed_keyword_terms(project.target_keywords)

    q = select(Keyword).where(Keyword.project_id == project_id)
    if keyword_type:
        q = q.where(Keyword.keyword_type == keyword_type)
    if search:
        q = q.where(Keyword.phrase.ilike(f"%{search}%"))

    result = await db.execute(q)
    filtered_keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword, topic_terms)
    ]

    if sort_by == "frequency":
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", -k.frequency))
    elif sort_by == "phrase":
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", k.phrase))
    else:
        filtered_keywords.sort(key=lambda k: (k.keyword_type != "top-pick", -k.created_at.timestamp()))

    total = len(filtered_keywords)
    start = (page - 1) * page_size
    keywords = filtered_keywords[start:start + page_size]

    items = []
    for kw in keywords:
        sources = await _keyword_sources(db, kw.id, limit=10)
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
        
    ai_keywords = await generate_ai_keywords(project.target_keywords)
    if not ai_keywords:
        raise HTTPException(status_code=500, detail="Failed to generate AI keywords")
        
    # Get existing keyword phrases in this project to avoid duplicates
    q_existing = select(Keyword.phrase).where(Keyword.project_id == project.id)
    result = await db.execute(q_existing)
    existing_phrases = {row[0] for row in result.all()}
    
    # Get own website URL-path keywords to filter out
    topic_terms = seed_keyword_terms(project.target_keywords)
    q_own_urls = select(Url.url).where(Url.project_id == project.id, Url.source_type == "own")
    result = await db.execute(q_own_urls)
    own_urls = result.scalars().all()
    
    from workers.pipeline import _url_keyword_candidates
    own_phrases: set[str] = set()
    for url in own_urls:
        own_phrases.update(_url_keyword_candidates(url, topic_terms, include_single_terms=True))
    
    # Combine both sets for filtering
    all_excluded = existing_phrases | own_phrases
    ai_keywords = [kw for kw in ai_keywords if kw["phrase"] not in all_excluded]
        
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
        
    added_count = 0
    for kw_data in ai_keywords:
        phrase = kw_data["phrase"]
        kw_type = kw_data["type"]
        
        q_kw = select(Keyword).where(Keyword.project_id == project.id, Keyword.phrase == phrase)
        result = await db.execute(q_kw)
        keyword = result.scalar_one_or_none()
        
        if not keyword:
            keyword = Keyword(
                project_id=project.id,
                phrase=phrase,
                keyword_type=kw_type,
                frequency=1,
            )
            db.add(keyword)
            await db.flush()
            added_count += 1
            
        # Link keyword to AI URL
        q_link = select(KeywordUrl).where(KeywordUrl.keyword_id == keyword.id, KeywordUrl.url_id == ai_url.id)
        result = await db.execute(q_link)
        link = result.scalar_one_or_none()
        if not link:
            db.add(KeywordUrl(keyword_id=keyword.id, url_id=ai_url.id))
            
    await db.commit()
    return {"message": f"Generated {added_count} new keywords", "generated": len(ai_keywords)}


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
    from nlp.openrouter import generate_ai_top_picks
    ai_keywords = await generate_ai_top_picks(project.target_keywords, existing_phrases)
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
        
    updated_count = 0
    for kw_data in ai_keywords:
        phrase = kw_data["phrase"]
        
        # We know they must exist because the AI picked them from existing_phrases,
        # but let's be safe.
        q_kw = select(Keyword).where(Keyword.project_id == project.id, Keyword.phrase == phrase)
        result = await db.execute(q_kw)
        keyword = result.scalar_one_or_none()
        
        if keyword:
            keyword.keyword_type = "top-pick"
            updated_count += 1
            
            # Ensure it's linked to the Top Picks URL so it shows up in the UI filter
            q_link = select(KeywordUrl).where(KeywordUrl.keyword_id == keyword.id, KeywordUrl.url_id == ai_url.id)
            res_link = await db.execute(q_link)
            link = res_link.scalar_one_or_none()
            if not link:
                db.add(KeywordUrl(keyword_id=keyword.id, url_id=ai_url.id))
            
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
    from datetime import datetime
    current_year = datetime.now().year

    # Phase 1: Filter
    clean_candidates = []
    for kw in existing_keywords:
        phrase_lower = kw["phrase"].lower()
            
        # Drop keywords containing past years (e.g., 2023, 2024, 2025 when we are in 2026)
        # Looks for any 4-digit number starting with 19 or 20
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', phrase_lower)
        if year_match:
            keyword_year = int(year_match.group(1))
            if keyword_year < current_year:
                continue

        # Drop merged duplicates and subheadings (they don't need their own spoke node)
        if kw["tier"] in ("merge", "subheading_group"):
            continue
            
        clean_candidates.append(kw)

    if not clean_candidates:
        raise HTTPException(status_code=400, detail="No valid parent keywords found after filtering.")

    # Phase 2: Send to LLM
    top_200 = clean_candidates[:200]
    remaining = clean_candidates[200:]
    
    clean_keywords_for_llm = [
        {"phrase": kw["phrase"], "type": kw["type"], "is_ai": kw["is_ai"]}
        for kw in top_200
    ]

    # Phase 3: The AI Skeleton
    from nlp.openrouter import cluster_hub_and_spoke
    clusters = await cluster_hub_and_spoke(clean_keywords_for_llm, main_keyword=project.main_keyword)
    if not clusters:
        raise HTTPException(status_code=500, detail="Failed to cluster keywords")

    # Phase 4: Auto-Map Remaining Keywords
    if remaining and "hubs" in clusters and isinstance(clusters["hubs"], list) and len(clusters["hubs"]) > 0:
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
            best_hub_idx = 0
            best_sub_silo_idx = None
            best_layer = "🧱 Foundations"
            best_sim = -1.0
            
            for node in placed_nodes:
                sim = phrase_similarity(phrase, node["target_kw"])
                if sim > best_sim:
                    best_sim = sim
                    best_hub_idx = node["hub_idx"]
                    best_sub_silo_idx = node["sub_silo_idx"]
                    best_layer = node["layer_name"]
                    
            if best_sim <= 0:
                best_hub_idx = 0
                best_sub_silo_idx = None
                best_layer = "🧱 Foundations"
                
            # Place in the correct node
            hub = clusters["hubs"][best_hub_idx]
            if best_sub_silo_idx is not None:
                target_node = hub.get("sub_silos", [])[best_sub_silo_idx]
            else:
                target_node = hub
                
            if "layers" not in target_node:
                target_node["layers"] = {}
            if best_layer not in target_node["layers"]:
                target_node["layers"][best_layer] = []
                
            target_node["layers"][best_layer].append(f"{phrase.title()} (Target Keyword: {phrase})")
            
            placed_nodes.append({
                "hub_idx": best_hub_idx,
                "sub_silo_idx": best_sub_silo_idx,
                "layer_name": best_layer,
                "target_kw": phrase
            })

    # Phase 5: Semantic Deduplication
    def semantic_tokenize(phrase: str) -> list[str]:
        slug = re.sub(r'[^\w]+', '-', phrase.lower()).strip('-')
        tokens = slug.split('-')
        stopwords = {"guide", "how", "to", "use", "for", "and", "vs", "the", "of"}
        filtered = [t for t in tokens if t not in stopwords and t]
        return sorted(filtered)

    seen_tokens_list = []
    
    def clean_hub_title(title: str) -> str:
        # Replicates frontend cleanHubTitle to get the exact base keyword
        title = re.sub(r'^(📍 MASTER HUB:|🪐 SUB-SILO \d+:)\s*', '', title)
        return title.split('—')[0].strip()

    # Preload Hub and Sub-Silo target keywords so spokes don't duplicate them
    if clusters and "hubs" in clusters and isinstance(clusters["hubs"], list):
        for hub in clusters["hubs"]:
            hub_kw = hub.get("target_keyword")
            if not hub_kw and "hub_title" in hub:
                hub_kw = clean_hub_title(hub["hub_title"])
            if hub_kw:
                tokens = semantic_tokenize(hub_kw)
                if tokens:
                    seen_tokens_list.append(tokens)
            
            if "sub_silos" in hub and isinstance(hub["sub_silos"], list):
                for silo in hub["sub_silos"]:
                    silo_kw = silo.get("target_keyword")
                    if not silo_kw and "hub_title" in silo:
                        silo_kw = clean_hub_title(silo["hub_title"])
                    if silo_kw:
                        tokens = semantic_tokenize(silo_kw)
                        if tokens:
                            seen_tokens_list.append(tokens)
    def is_duplicate(target_kw: str) -> bool:
        tokens = semantic_tokenize(target_kw)
        if not tokens:
            return False
        for seen_tokens in seen_tokens_list:
            overlap = len(set(tokens) & set(seen_tokens))
            max_len = max(len(tokens), len(seen_tokens))
            if max_len > 0 and (overlap / max_len) >= 0.8:
                return True
        seen_tokens_list.append(tokens)
        return False

    if clusters and "hubs" in clusters and isinstance(clusters["hubs"], list):
        for hub in clusters["hubs"]:
            if "layers" in hub and isinstance(hub["layers"], dict):
                for layer_name, spokes in hub["layers"].items():
                    deduped_spokes = []
                    for spoke in spokes:
                        match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                        if match:
                            target_kw = match.group(1).strip()
                            if not is_duplicate(target_kw):
                                deduped_spokes.append(spoke)
                        else:
                            deduped_spokes.append(spoke)
                    hub["layers"][layer_name] = deduped_spokes
            
            if "sub_silos" in hub and isinstance(hub["sub_silos"], list):
                for silo in hub["sub_silos"]:
                    if "layers" in silo and isinstance(silo["layers"], dict):
                        for layer_name, spokes in silo["layers"].items():
                            deduped_spokes = []
                            for spoke in spokes:
                                match = re.search(r'\(Target Keyword:\s*(.*?)\)', spoke, re.IGNORECASE)
                                if match:
                                    target_kw = match.group(1).strip()
                                    if not is_duplicate(target_kw):
                                        deduped_spokes.append(spoke)
                                else:
                                    deduped_spokes.append(spoke)
                            silo["layers"][layer_name] = deduped_spokes

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
               Keyword.sub_silo_id)
        .where(Keyword.project_id == project.id, Keyword.tier.isnot(None))
    )
    tier_result = await db.execute(tier_q)
    tier_metadata = {}
    for phrase, tier, article_title, h_tags, merged_from, cluster_group_id, sub_silo_id in tier_result.all():
        tier_metadata[phrase] = {
            "tier": tier,
            "article_title": article_title,
            "h_tags": h_tags,
            "merged_from": merged_from,
            "cluster_group_id": cluster_group_id,
            "sub_silo_id": sub_silo_id,
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
    project = await _assert_owns_project(project_id, current_user.id, db)
    topic_terms = seed_keyword_terms(project.target_keywords)

    result = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .order_by(Keyword.frequency.desc())
    )
    keywords = [
        keyword for keyword in result.scalars().all()
        if _is_displayable_keyword(keyword, topic_terms)
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
    for kw in keywords:
        sources = await _keyword_sources(db, kw.id)
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
    return StreamingResponse(
        iter([output.getvalue()]),
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
    q_kw = select(Keyword).where(Keyword.id.in_(body.keyword_ids))
    res_kw = await db.execute(q_kw)
    keywords_to_delete = res_kw.scalars().all()
    phrases_to_remove = {k.phrase for k in keywords_to_delete}
    
    # Keyword deletion will cascade to KeywordUrl automatically if configured, 
    # but we can manually delete from Keyword to be safe
    from sqlalchemy import delete
    
    # Delete KeywordUrls first to be completely safe against FK constraints
    await db.execute(
        delete(KeywordUrl).where(KeywordUrl.keyword_id.in_(body.keyword_ids))
    )
    
    # Delete KeywordBank entries associated with these keywords
    await db.execute(
        delete(KeywordBank).where(KeywordBank.keyword_id.in_(body.keyword_ids))
    )
    
    # Finally delete the keywords themselves
    result = await db.execute(
        delete(Keyword).where(
            Keyword.id.in_(body.keyword_ids),
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
    
    return {"message": f"Successfully deleted keywords"}


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


def _is_displayable_keyword(keyword: Keyword, topic_terms: set[str]) -> bool:
    if keyword.keyword_type == "top-pick":
        return True
    return is_publishable_keyword(keyword.phrase, min_words=2)


async def _keyword_sources(
    db: AsyncSession,
    keyword_id: uuid.UUID,
    limit: int | None = None,
) -> list[KeywordSourceOut]:
    q = (
        select(Url.url, Url.source_type, Url.source_domain)
        .join(KeywordUrl, KeywordUrl.url_id == Url.id)
        .where(KeywordUrl.keyword_id == keyword_id)
        .order_by(Url.source_domain.asc().nullslast(), Url.url.asc())
    )
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    return [
        KeywordSourceOut(
            url=url,
            source_type=source_type,
            source_domain=source_domain or _source_origin(url),
        )
        for url, source_type, source_domain in result.all()
    ]


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
