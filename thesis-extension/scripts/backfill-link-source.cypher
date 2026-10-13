// backfill-link-source.cypher
// For graphs that are NOT being rebuilt: label assignedToProject edges created before
// edges carried a `source` property. Only edges with no source are changed, so edges
// already marked 'extracted' (extract-ADR.py) or 'inferred' (promote_inferred_link)
// are left alone. Safe to run more than once.
//
// Run in Neo4j Browser or with cypher-shell:
//   cypher-shell -u neo4j -p <password> -f thesis-extension/scripts/backfill-link-source.cypher
//
// Before a clean rebuild, run scripts/export-confirmed-links.py instead, so the
// human decisions survive.

// 1) Edges written by extract-ADR.py (never promoted)
MATCH ()-[a:assignedToProject]->()
WHERE a.source IS NULL AND a.promotedBy IS NULL
SET a.source = 'extracted'
RETURN 'extracted' AS source, count(a) AS edges_updated;

// 2) Edges promoted by the old promote_inferred_link, which always wrote
//    promotedBy = 'human-review' and deleted the suggestion it came from
MATCH ()-[a:assignedToProject]->()
WHERE a.source IS NULL AND a.promotedBy = 'human-review'
SET a.source = 'inferred-legacy'
RETURN 'inferred-legacy' AS source, count(a) AS edges_updated;

// 3) Check: anything still without a source needs manual review
MATCH (r)-[a:assignedToProject]->(p)
WHERE a.source IS NULL
RETURN r.hasID AS requirement_id, p.projectID AS project_id, a.promotedBy AS promoted_by;
