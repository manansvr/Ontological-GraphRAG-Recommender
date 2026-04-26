// SR8 extraction one-command Cypher
// Run in Neo4j Browser (section by section) or via cypher-shell.
// This script:
// 1) Rebuilds Assembly nodes and links
// 2) Runs validation/verification checks
// 3) Returns full graph paths
// 4) Returns ADR-43 hierarchy paths

// ============================================================
// 1) Create Assemblies (clean + rebuild)
// ============================================================
MATCH ()-[r:includesProject|belongsToAssembly]->() DELETE r;
MATCH (a:Assembly) DETACH DELETE a;

MERGE (a:Assembly {hasID: "ASM-FRONT-AXLE", hasName: "Front Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-043", "SRP8-045", "SRP8-050", "SRP8-088"]
MERGE (p)-[:belongsToAssembly]->(a);

MERGE (a:Assembly {hasID: "ASM-STEERING", hasName: "Steering System"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-047", "SRP8-048", "SRP8-049"]
MERGE (p)-[:belongsToAssembly]->(a);

MERGE (a:Assembly {hasID: "ASM-REAR-AXLE", hasName: "Rear Axle Assembly"})
WITH a
MATCH (p:Project) WHERE p.projectID IN ["SRP8-044", "SRP8-046", "SRP8-051", "SRP8-089"]
MERGE (p)-[:belongsToAssembly]->(a);

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
