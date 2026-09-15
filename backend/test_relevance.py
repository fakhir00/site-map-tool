from nlp.keywords import seed_keyword_terms, site_scope_terms

seed = "circuitdiagrammaker com"
print("seed_anchors:", seed_keyword_terms([seed]))
print("seed_scope:", site_scope_terms(seed))
