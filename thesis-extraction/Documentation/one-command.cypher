// SR8 extraction one-command Cypher
// Run in Neo4j Browser (section by section) or via cypher-shell.
// This script:
// 1) (Assemblies are no longer created here; see below)
// 2) Runs validation/verification checks
// 3) Returns full graph paths
// 4) Returns ADR-43 hierarchy paths

// ============================================================
// 1) Assemblies
// ============================================================
// Assembly nodes and (Project)-[:belongsToAssembly]->(Assembly) edges are created by
//   python3 Scripts/run-extraction.py --only assemblies
// from data/assemblies.csv (assembly_id, assembly_name, project_id). Project IDs that do
// not exist are reported and skipped; no stub projects are created.

// ============================================================
// 2) Validation & Verification
// ============================================================
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC;

MATCH (a:AustralianDesignRule)-[:hasClause]->(c:Clause)
RETURN a.hasID, count(c) AS clauses
ORDER BY a.hasID;

// ============================================================
// 3) View Full Knowledge Graph Path
// ============================================================
MATCH path1 = (a:AustralianDesignRule)-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3;

// ============================================================
// 4) View Hierarchy For ADR-43
// ============================================================
MATCH path1 = (a:AustralianDesignRule {hasID: "ADR-43"})-[:hasExternalEssentialRequirement]->(r:ExtractedEssentialRequirement)
MATCH path2 = (r)-[:assignedToProject]->(p:Project)
MATCH path3 = (p)-[:belongsToAssembly]->(asm:Assembly)
RETURN path1, path2, path3;
