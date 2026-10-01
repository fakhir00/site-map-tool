"""Build a navigable topical map from validated pages, without inventing pages or demand."""
from collections import defaultdict
from hashlib import sha256

from nlp.keywords import clean_phrase


def place_supporting_keyword(page, keyword, placement):
    """Preserve specific section assignments; unspecified placement stays page-level."""
    kind, _, heading = placement.partition(':')
    if kind == 'entity':
        page['entity_terms'].append(keyword)
        return
    if kind not in {'h2', 'faq'} or not heading.strip():
        return
    collection, label = ('h2_sections', 'h2_heading') if kind == 'h2' else ('faq_schema_questions', 'question')
    sections = page[collection]
    section = next((item for item in sections if clean_phrase(item[label]) == clean_phrase(heading)), None)
    if section is None:
        section = {label: heading.strip(), 'targeted_keywords_placed_here': []}
        if kind == 'h2':
            section['section_definition'] = ''
        sections.append(section)
    section['targeted_keywords_placed_here'].append(keyword)


def attach_topical_map(plan):
    """Connect immediate parents and children; keep homepage links selective.

    Explicit links can feature selected deeper pages. Do not automatically add
    homepage links for all descendants or homepage backlinks on every leaf.
    """
    master = plan['master_hub']
    pages = [master, *plan['spokes']]
    by_target = {page['target_keyword']: page for page in pages}
    root = master['target_keyword']
    warnings = []
    parents = {}
    for page in pages:
        target = page['target_keyword']
        page['id'] = 'page-' + sha256(target.encode()).hexdigest()[:16]
        if target == root:
            continue
        parent = page.get('parent_target') or root
        if parent not in by_target or parent == target:
            warnings.append(f'Review parent for "{target}"; linked to the main hub.')
            parent = root
        parents[target] = parent
    # Flatten only invalid cycles. Never let a provider-created cycle strand pages.
    for target in parents:
        seen = {target}
        current = parents[target]
        while current != root:
            if current in seen:
                parents[target] = root
                warnings.append(f'Review circular hierarchy at "{target}"; linked to the main hub.')
                break
            seen.add(current)
            current = parents[current]
    master['parent_target'] = None
    for target, parent in parents.items():
        page = by_target[target]
        page['parent_target'] = parent
        page['internal_links'] = list(dict.fromkeys([parent, *page.get('internal_links', [])]))
        by_target[parent]['internal_links'] = list(dict.fromkeys([
            *by_target[parent].get('internal_links', []), target,
        ]))

    groups = defaultdict(list)
    group_names = {}
    for page in plan['spokes']:
        name = page.get('spoke_category') or 'Supporting topics'
        key = clean_phrase(name)
        group_names.setdefault(key, name)
        groups[key].append(page['id'])
    plan['topic_clusters'] = [
        {'id': 'topic-' + sha256(key.encode()).hexdigest()[:12], 'name': group_names[key], 'page_ids': ids}
        for key, ids in groups.items()
    ]
    edges = []
    for page in pages:
        target = page['target_keyword']
        for linked in dict.fromkeys(page.get('internal_links', [])):
            if linked not in by_target or linked == target:
                continue
            destination = by_target[linked]
            if parents.get(target) == linked:
                relationship, reason = 'parent', 'Return to the broader topic and its related tasks.'
            elif parents.get(linked) == target:
                relationship, reason = 'child', 'Continue to this focused task from the broader topic.'
            elif target == root or linked == root:
                relationship, reason = 'hub', 'Connect this page with the main topic hub.'
            else:
                relationship, reason = 'related', 'Suggested related reading; confirm the link is useful in context.'
            edges.append({
                'source': page['id'], 'target': destination['id'], 'source_keyword': target,
                'target_keyword': linked, 'source_url': page.get('existing_url') or page['slug'],
                'target_url': destination.get('existing_url') or destination['slug'],
                'anchor_text': destination['article_title'], 'relationship': relationship, 'reason': reason,
            })
    plan['link_plan'] = edges
    plan['map_version'] = 2
    plan['map_warnings'] = warnings
    plan['map_summary'] = {
        'pages': len(pages), 'topic_groups': len(groups), 'links': len(edges),
        'supplied_keyword_pages': sum(page.get('evidence_type') != 'editorial_proposal' for page in pages),
        'proposed_pages': sum(page.get('evidence_type') == 'editorial_proposal' for page in pages),
        'existing_pages': sum(page.get('action') == 'update' for page in pages),
    }
    return plan
