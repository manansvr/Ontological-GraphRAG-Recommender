// ============================================================
// SR8 ONTOLOGY - NEO4J CYPHER EXAMPLES
// ============================================================
// Run these commands after importing the ontology schema into Neo4j

// ------------------------------------------------------------
// STEP 1: Create Constraints (Run First!)
// ------------------------------------------------------------

CREATE CONSTRAINT sr8_req_id IF NOT EXISTS 
FOR (r:Requirement) REQUIRE r.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_comp_id IF NOT EXISTS 
FOR (c:Component) REQUIRE c.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_adr_id IF NOT EXISTS 
FOR (a:AustralianDesignRule) REQUIRE a.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_subsys_id IF NOT EXISTS 
FOR (s:Subsystem) REQUIRE s.hasID IS UNIQUE;

// ------------------------------------------------------------
// STEP 2: Create Indexes for Performance
// ------------------------------------------------------------

CREATE INDEX req_name IF NOT EXISTS 
FOR (r:Requirement) ON (r.hasName);

CREATE INDEX comp_name IF NOT EXISTS 
FOR (c:Component) ON (c.hasName);

CREATE INDEX subsys_name IF NOT EXISTS 
FOR (s:Subsystem) ON (s.hasName);

// ------------------------------------------------------------
// STEP 3: Create Sample Data from Ontology
// ------------------------------------------------------------

// Organization
CREATE (sunswift:SunswiftRacing {
    hasID: "ORG-001",
    hasName: "Sunswift Racing",
    numberOfMembers: 80,
    numberOfDepartments: 16,
    numberOfProjects: 189,
    hasDescription: "World-leading student solar-electric vehicle team"
});

// Industry Partner
CREATE (neo4j:IndustryPartner {
    hasID: "PARTNER-001",
    hasName: "Neo4j",
    hasDescription: "Leading graph database technology partner"
});

// Vehicle
CREATE (sr8:SR8 {
    hasID: "VEH-SR8",
    hasName: "Sunswift 8",
    hasDescription: "World's first road-legal, student-built, tri-brid electric vehicle",
    isRoadLegal: true,
    numberOfComponents: 100000,
    numberOfRequirements: 600000
});

// Sample ADRs
CREATE (adr42:AustralianDesignRule {
    hasID: "ADR-042",
    hasName: "General Safety Requirements",
    hasDescription: "Requirements for general safety provisions"
});

CREATE (adr63:AustralianDesignRule {
    hasID: "ADR-063",
    hasName: "Light Vehicle Braking Systems",
    hasDescription: "Braking system performance and safety"
});

// Sample Subsystems
CREATE (battery:Subsystem {
    hasID: "SS-BATT",
    hasName: "Battery Subsystem",
    hasRiskLevel: "High",
    hasDescription: "Tri-brid battery pack and management system"
});

CREATE (powertrain:Subsystem {
    hasID: "SS-PWTR",
    hasName: "Powertrain Subsystem",
    hasRiskLevel: "High",
    hasDescription: "Electric motor and controller"
});

CREATE (safety:Subsystem {
    hasID: "SS-SAFE",
    hasName: "Safety Systems Subsystem",
    hasRiskLevel: "Critical",
    hasDescription: "ECU, sensors, and safety controls"
});

// Sample Requirements
CREATE (req1:EssentialRequirement {
    hasID: "REQ-ADR42-001",
    hasName: "Battery Crash Protection",
    hasDescription: "Battery must be protected from crash damage",
    isEssential: true,
    isConditional: false,
    hasRiskLevel: "High",
    hasConfidenceScore: 0.98,
    hasProvenance: "Extracted from ADR-042"
});

CREATE (req2:EssentialRequirement {
    hasID: "REQ-ADR63-001",
    hasName: "Emergency Braking Performance",
    hasDescription: "Vehicle must achieve specified braking distance",
    isEssential: true,
    isConditional: false,
    hasRiskLevel: "Critical",
    hasConfidenceScore: 0.99,
    hasProvenance: "Extracted from ADR-063"
});

CREATE (req3:RecommendedRequirement {
    hasID: "REQ-INT-001",
    hasName: "Battery Thermal Management",
    hasDescription: "Battery temperature should be monitored and controlled",
    isEssential: false,
    isConditional: true,
    hasRiskLevel: "Medium",
    hasConfidenceScore: 0.85,
    hasProvenance: "Inferred by LLM Agent"
});

// Knowledge Graph and Technologies
CREATE (kg:KnowledgeGraph {
    hasID: "KG-SR8",
    hasName: "SR8 Regulatory Knowledge Graph",
    hasDescription: "Ontology-driven knowledge representation"
});

CREATE (neo4jdb:Neo4j {
    hasID: "TECH-NEO4J",
    hasName: "Neo4j Database"
});

// Multi-Agent System
CREATE (llm:LLMAgent {
    hasID: "AGENT-LLM",
    hasName: "LLM Inference Agent",
    hasDescription: "Detects linguistic nuance and implicit dependencies"
});

CREATE (linkpred:LinkPredictionAgent {
    hasID: "AGENT-LINK",
    hasName: "Link Prediction Agent",
    hasDescription: "Identifies latent relational patterns"
});

CREATE (rl:RLAgent {
    hasID: "AGENT-RL",
    hasName: "RL Prioritization Agent",
    hasDescription: "Learns requirement prioritization"
});

CREATE (mcp:ModelContextProtocol {
    hasID: "MCP-001",
    hasName: "MCP Orchestrator",
    hasDescription: "Coordinates multi-agent workflow"
});

// ------------------------------------------------------------
// STEP 4: Create Relationships
// ------------------------------------------------------------

// Organization relationships
MATCH (s:SunswiftRacing), (n:IndustryPartner)
WHERE s.hasID = "ORG-001" AND n.hasID = "PARTNER-001"
CREATE (s)-[:collaboratesWith]->(n);

// Vehicle-Subsystem relationships
MATCH (v:SR8), (b:Subsystem), (p:Subsystem), (s:Subsystem)
WHERE v.hasID = "VEH-SR8" 
  AND b.hasID = "SS-BATT"
  AND p.hasID = "SS-PWTR"
  AND s.hasID = "SS-SAFE"
CREATE (v)-[:hasSubsystem]->(b),
       (v)-[:hasSubsystem]->(p),
       (v)-[:hasSubsystem]->(s);

// Subsystem interfaces (symmetric)
MATCH (b:Subsystem), (p:Subsystem), (s:Subsystem)
WHERE b.hasID = "SS-BATT"
  AND p.hasID = "SS-PWTR"
  AND s.hasID = "SS-SAFE"
CREATE (b)-[:interfacesWith]->(p),
       (b)-[:interfacesWith]->(s),
       (p)-[:interfacesWith]->(s);

// Requirement-ADR relationships
MATCH (r1:Requirement), (adr42:AustralianDesignRule)
WHERE r1.hasID = "REQ-ADR42-001" AND adr42.hasID = "ADR-042"
CREATE (r1)-[:derivedFrom]->(adr42);

MATCH (r2:Requirement), (adr63:AustralianDesignRule)
WHERE r2.hasID = "REQ-ADR63-001" AND adr63.hasID = "ADR-063"
CREATE (r2)-[:derivedFrom]->(adr63);

// Requirement-Subsystem relationships
MATCH (r1:Requirement), (b:Subsystem)
WHERE r1.hasID = "REQ-ADR42-001" AND b.hasID = "SS-BATT"
CREATE (r1)-[:appliesTo]->(b);

MATCH (r3:Requirement), (b:Subsystem)
WHERE r3.hasID = "REQ-INT-001" AND b.hasID = "SS-BATT"
CREATE (r3)-[:appliesTo]->(b);

// Requirement dependencies
MATCH (r3:Requirement), (r1:Requirement)
WHERE r3.hasID = "REQ-INT-001" AND r1.hasID = "REQ-ADR42-001"
CREATE (r3)-[:dependsOn]->(r1);

// Risk propagation
MATCH (b:Subsystem), (p:Subsystem)
WHERE b.hasID = "SS-BATT" AND p.hasID = "SS-PWTR"
CREATE (b)-[:propagatesRiskTo]->(p);

// Agent inferences
MATCH (r3:Requirement), (llm:LLMAgent)
WHERE r3.hasID = "REQ-INT-001" AND llm.hasID = "AGENT-LLM"
CREATE (r3)-[:inferredBy]->(llm);

// MCP orchestration
MATCH (llm:LLMAgent), (lp:LinkPredictionAgent), 
      (rl:RLAgent), (mcp:ModelContextProtocol)
WHERE llm.hasID = "AGENT-LLM" 
  AND lp.hasID = "AGENT-LINK"
  AND rl.hasID = "AGENT-RL"
  AND mcp.hasID = "MCP-001"
CREATE (llm)-[:orchestratedBy]->(mcp),
       (lp)-[:orchestratedBy]->(mcp),
       (rl)-[:orchestratedBy]->(mcp);

// Knowledge Graph storage
MATCH (kg:KnowledgeGraph), (db:Neo4j)
WHERE kg.hasID = "KG-SR8" AND db.hasID = "TECH-NEO4J"
CREATE (kg)-[:storedIn]->(db);

// ------------------------------------------------------------
// QUERY EXAMPLES
// ------------------------------------------------------------

// Query 1: Find all requirements for the Battery Subsystem
MATCH (r:Requirement)-[:appliesTo]->(s:Subsystem {hasName: "Battery Subsystem"})
RETURN r.hasName, r.hasDescription, r.hasRiskLevel
ORDER BY r.hasRiskLevel DESC;

// Query 2: Trace requirement back to ADR
MATCH (r:Requirement {hasID: "REQ-ADR42-001"})-[:derivedFrom]->(adr:AustralianDesignRule)
RETURN r.hasName, adr.hasName, adr.hasDescription;

// Query 3: Find all subsystems interfacing with Battery
MATCH (b:Subsystem {hasName: "Battery Subsystem"})-[:interfacesWith]-(other:Subsystem)
RETURN other.hasName, other.hasRiskLevel;

// Query 4: Find requirement dependency chains
MATCH path = (r1:Requirement)-[:dependsOn*]->(r2:Requirement)
WHERE r1.hasID = "REQ-INT-001"
RETURN path;

// Query 5: Identify AI-inferred requirements
MATCH (r:Requirement)-[:inferredBy]->(agent:Agent)
RETURN agent.hasName, COUNT(r) AS inferredCount, 
       AVG(r.hasConfidenceScore) AS avgConfidence
ORDER BY inferredCount DESC;

// Query 6: Risk propagation analysis
MATCH path = (source:Subsystem)-[:propagatesRiskTo*]->(target:Subsystem)
WHERE source.hasName = "Battery Subsystem"
RETURN path;

// Query 7: Find all essential vs recommended requirements
MATCH (r:Requirement)
RETURN r.isEssential, COUNT(r) AS count;

// Query 8: Compliance check - which subsystems have requirements from specific ADR
MATCH (adr:AustralianDesignRule {hasID: "ADR-042"})<-[:derivedFrom]-(r:Requirement)
      -[:appliesTo]->(s:Subsystem)
RETURN s.hasName, COUNT(r) AS requirementCount;

// Query 9: Multi-agent coordination
MATCH (mcp:ModelContextProtocol)<-[:orchestratedBy]-(agent:Agent)
RETURN mcp.hasName, COLLECT(agent.hasName) AS agents;

// Query 10: Find low-confidence inferences for review
MATCH (r:Requirement)-[:inferredBy]->(agent:Agent)
WHERE r.hasConfidenceScore < 0.90
RETURN r.hasName, r.hasConfidenceScore, agent.hasName, r.hasProvenance
ORDER BY r.hasConfidenceScore ASC;

// ------------------------------------------------------------
// ADVANCED ANALYTICS
// ------------------------------------------------------------

// Count total relationships by type
MATCH ()-[r]->()
RETURN type(r) AS relationshipType, COUNT(r) AS count
ORDER BY count DESC;

// Find most connected subsystems
MATCH (s:Subsystem)
OPTIONAL MATCH (s)-[r]-()
RETURN s.hasName, COUNT(r) AS connectionCount
ORDER BY connectionCount DESC;

// Find orphaned requirements (no ADR source)
MATCH (r:Requirement)
WHERE NOT (r)-[:derivedFrom]->(:AustralianDesignRule)
RETURN r.hasID, r.hasName, r.hasProvenance;

// Graph summary
CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {})
YIELD value
RETURN label, value.count AS nodeCount
ORDER BY nodeCount DESC;

// ============================================================
// END OF CYPHER EXAMPLES
// ============================================================
