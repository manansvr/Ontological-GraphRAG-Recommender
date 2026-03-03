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

// ------------------------------------------------------------
// ADR VERIFICATION TRACKING QUERIES
// ------------------------------------------------------------

// Create sample ADR verification data
// ADR-42: Lighting and Light Signalling Devices
CREATE (adr42:AustralianDesignRule {
    hasID: "ADR-042",
    hasName: "ADR-42",
    hasClause: "42.2.3",
    requirementName: "Headlamp Performance",
    requirementText: "Headlamps shall provide adequate illumination under all operating conditions",
    isVerified: false,
    usesAlternativeTesting: true,
    rightProjectAssigned: true
})

// Create verification procedure
CREATE (proc1:VerificationProcedure {
    hasID: "VP-042-001",
    hasName: "Headlamp Photometric Test",
    verificationMethodDescription: "Photometric testing using calibrated lux meter at specified distances and angles per ADR-42 requirements"
})

// Create verification method
CREATE (method:Test {
    hasID: "VM-TEST-001",
    hasName: "Physical Testing"
})

// Create evidence
CREATE (evidence:TestEvidence {
    hasID: "EV-042-001",
    hasName: "Photometric Test Results",
    hasDescription: "Test results showing compliance with illumination requirements",
    hasTimestamp: datetime()
})

// Create project
CREATE (project:Project {
    hasID: "PROJ-ELEC-01",
    projectID: "PROJ-ELEC-01",
    hasName: "Electrical Systems"
})

// Create department
CREATE (dept:Department {
    hasID: "DEPT-ELEC",
    hasName: "Electrical Department"
})

// Create relationships
CREATE (adr42)-[:assignedToProject]->(project)
CREATE (adr42)-[:assignedToDepartment]->(dept)
CREATE (adr42)-[:hasVerificationProcedure]->(proc1)
CREATE (proc1)-[:hasVerificationMethod]->(method)
CREATE (proc1)-[:supportedByEvidence]->(evidence)
CREATE (adr42)-[:verifiedBy]->(evidence);

// Query: Find all ADRs and their verification status
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasVerificationProcedure]->(proc:VerificationProcedure)
OPTIONAL MATCH (proc)-[:supportedByEvidence]->(ev:Evidence)
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.isVerified AS Verified,
       proc.hasName AS Procedure,
       ev.hasName AS Evidence
ORDER BY adr.hasID;

// Query: Find all unverified ADRs
MATCH (adr:AustralianDesignRule)
WHERE adr.isVerified = false
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.hasClause AS Clause,
       adr.requirementText AS Description
ORDER BY adr.hasID;

// Query: Find ADRs by verification method
MATCH (adr:AustralianDesignRule)-[:hasVerificationProcedure]->(proc:VerificationProcedure)
      -[:hasVerificationMethod]->(method:VerificationMethod)
RETURN labels(method)[0] AS VerificationMethod,
       COUNT(adr) AS ADR_Count,
       COLLECT(adr.hasID) AS ADRs
ORDER BY ADR_Count DESC;

// Query: Find ADRs by evidence type
MATCH (adr:AustralianDesignRule)-[:verifiedBy]->(ev:Evidence)
RETURN labels(ev)[0] AS EvidenceType,
       COUNT(adr) AS ADR_Count,
       COLLECT(adr.hasID) AS ADRs
ORDER BY ADR_Count DESC;

// Query: Find all ADRs assigned to a specific project
MATCH (adr:AustralianDesignRule)-[:assignedToProject]->(p:Project)
WHERE p.projectID = "PROJ-ELEC-01"
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.isVerified AS Verified,
       p.hasName AS Project
ORDER BY adr.hasID;

// Query: Find ADRs assigned to a specific department
MATCH (adr:AustralianDesignRule)-[:assignedToDepartment]->(d:Department)
WHERE d.hasName = "Electrical Department"
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.isVerified AS Verified,
       d.hasName AS Department
ORDER BY adr.hasID;

// Query: Find ADRs using alternative testing methods
MATCH (adr:AustralianDesignRule)
WHERE adr.usesAlternativeTesting = true
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.hasClause AS Clause
ORDER BY adr.hasID;

// Query: Find ADRs with incorrect project assignments
MATCH (adr:AustralianDesignRule)
WHERE adr.rightProjectAssigned = false
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.alternativeProjectSuggestion AS SuggestedProject
ORDER BY adr.hasID;

// Query: Verification completion report by project
MATCH (p:Project)<-[:assignedToProject]-(adr:AustralianDesignRule)
WITH p, adr,
     CASE WHEN adr.isVerified = true THEN 1 ELSE 0 END AS verified_count,
     1 AS total_count
RETURN p.hasName AS Project,
       SUM(total_count) AS Total_ADRs,
       SUM(verified_count) AS Verified_ADRs,
       ROUND(100.0 * SUM(verified_count) / SUM(total_count), 2) AS Completion_Percentage
ORDER BY Completion_Percentage DESC;

// Query: Full ADR verification workflow path
MATCH path = (adr:AustralianDesignRule)-[:hasVerificationProcedure]->
             (proc:VerificationProcedure)-[:hasVerificationMethod]->
             (method:VerificationMethod)
MATCH (proc)-[:supportedByEvidence]->(ev:Evidence)
RETURN adr.hasID AS ADR,
       proc.hasName AS Procedure,
       labels(method)[0] AS Method,
       labels(ev)[0] AS EvidenceType,
       ev.hasName AS EvidenceName;

// Query: Find ADRs missing verification procedures
MATCH (adr:AustralianDesignRule)
WHERE NOT (adr)-[:hasVerificationProcedure]->(:VerificationProcedure)
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.hasClause AS Clause,
       "Missing Verification Procedure" AS Status;

// Query: Find ADRs missing evidence
MATCH (adr:AustralianDesignRule)
WHERE NOT (adr)-[:verifiedBy]->(:Evidence)
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       "Missing Evidence" AS Status;

// Query: Find ADRs not assigned to any project
MATCH (adr:AustralianDesignRule)
WHERE NOT (adr)-[:assignedToProject]->(:Project)
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       "Not Assigned to Project" AS Status;

// Query: Comprehensive ADR verification checklist
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:assignedToProject]->(p:Project)
OPTIONAL MATCH (adr)-[:assignedToDepartment]->(d:Department)
OPTIONAL MATCH (adr)-[:hasVerificationProcedure]->(proc:VerificationProcedure)
OPTIONAL MATCH (proc)-[:hasVerificationMethod]->(method:VerificationMethod)
OPTIONAL MATCH (proc)-[:supportedByEvidence]->(ev:Evidence)
RETURN adr.hasClause AS Clause,
       adr.requirementName AS Requirement_Name,
       adr.requirementText AS Text,
       p.projectID AS Project_ID,
       p.hasName AS Project,
       d.hasName AS Department,
       adr.rightProjectAssigned AS Right_Project,
       adr.usesAlternativeTesting AS Alternative_Testing,
       labels(method)[0] AS Verification_Method,
       proc.verificationMethodDescription AS Method_Description,
       labels(ev)[0] AS Evidence_Type,
       adr.isVerified AS Verified
ORDER BY adr.hasID;

// ------------------------------------------------------------
// COMPONENT MANAGEMENT TRACKING QUERIES
// ------------------------------------------------------------

// Create sample component data
// Component: Battery Management System (BMS)
CREATE (bms:Component {
    hasID: "COMP-ELEC-BMS-001",
    partNumber: "BMS-2024-001",
    partDescription: "Battery Management System - Primary Controller",
    bomLevel: 2,
    approvalStatus: "Approved",
    componentStatus: "In Production",
    onCarSoftwareOffCar: "On-Car Software",
    quantityPer: 1,
    estimatedWeight: 2.5,
    actualWeight: 2.3,
    usedInCarBuild: true,
    usedInShakeDown: true,
    usedInTrackTest01: true,
    usedInTrackTest02: true,
    usedInCarLaunch: true,
    usedInPressLaunch: true,
    usedInRoadTest01: true,
    relatedADRs: "ADR-42, ADR-68",
    engineeringDrawingRequired: true,
    procurementStatus: "Received",
    supplier: "Texas Instruments",
    assemblyEstimatedCost: 850.00,
    assemblyActualCost: 820.00,
    orderStatus: "Complete",
    stockQuantity: 3,
    stockLocation: "Workshop A-12"
})

// Create project
CREATE (projElec:Project {
    hasID: "PROJ-ELEC-01",
    projectID: "PROJ-ELEC-01",
    hasName: "Electrical Systems",
    hasDescription: "Electrical subsystems and power management"
})

// Create department
CREATE (deptElec:Department {
    hasID: "DEPT-ELEC",
    hasName: "Electrical Engineering"
})

// Create supplier
CREATE (supplierTI:IndustryPartner {
    hasID: "SUPPLIER-TI",
    hasName: "Texas Instruments",
    hasDescription: "Semiconductor and integrated circuits supplier"
})

// Create ADR
CREATE (adr42:AustralianDesignRule {
    hasID: "ADR-042",
    hasName: "ADR-42",
    requirementName: "Lighting Systems"
})

// Create evidence
CREATE (testEv:TestEvidence {
    hasID: "EV-BMS-001",
    hasName: "BMS Functional Test Results",
    hasDescription: "Complete functional testing of BMS under various load conditions"
})

// Create milestones
CREATE (carBuild:CarBuild {
    hasID: "MILESTONE-CARBUILD",
    hasName: "Car Build Phase"
})

CREATE (trackTest:TrackTest {
    hasID: "MILESTONE-TRACKTEST01",
    hasName: "Track Test 01"
})

// Create relationships
CREATE (bms)-[:usedInProject]->(projElec)
CREATE (bms)-[:belongsToDepartment]->(deptElec)
CREATE (bms)-[:usedInADR]->(adr42)
CREATE (bms)-[:generatesEvidence]->(testEv)
CREATE (bms)-[:suppliedBy]->(supplierTI)
CREATE (bms)-[:participatesInMilestone]->(carBuild)
CREATE (bms)-[:participatesInMilestone]->(trackTest);

// Query: Find all components by project
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Component_Count,
       SUM(c.actualWeight) AS Total_Weight_kg,
       SUM(c.assemblyActualCost) AS Total_Cost
ORDER BY Component_Count DESC;

// Query: Find components by part number
MATCH (c:Component)
WHERE c.partNumber = "BMS-2024-001"
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.bomLevel AS BOM_Level,
       c.componentStatus AS Status,
       c.actualWeight AS Weight_kg,
       c.assemblyActualCost AS Cost,
       c.stockLocation AS Location;

// Query: Find components used in specific ADR
MATCH (c:Component)-[:usedInADR]->(adr:AustralianDesignRule)
WHERE adr.hasID = "ADR-042"
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.supplier AS Supplier,
       c.componentStatus AS Status
ORDER BY c.partNumber;

// Query: Track components through lifecycle milestones
MATCH (c:Component)
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.usedInCarBuild AS Car_Build,
       c.usedInShakeDown AS Shake_Down,
       c.usedInTrackTest01 AS Track_Test_01,
       c.usedInTrackTest02 AS Track_Test_02,
       c.usedInCarLaunch AS Car_Launch,
       c.usedInPressLaunch AS Press_Launch,
       c.usedInRoadTest01 AS Road_Test_01
ORDER BY c.partNumber;

// Query: Find components by supplier
MATCH (c:Component)-[:suppliedBy]->(s:IndustryPartner)
RETURN s.hasName AS Supplier,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Cost,
       COLLECT(c.partNumber) AS Part_Numbers
ORDER BY Component_Count DESC;

// Query: Component BOM hierarchy
MATCH path = (parent:Component)<-[:partOfBOM*]-(child:Component)
RETURN parent.partNumber AS Parent_Part,
       parent.partDescription AS Parent_Description,
       LENGTH(path) AS BOM_Depth,
       COLLECT(child.partNumber) AS Child_Parts
ORDER BY parent.partNumber;

// Query: Weight analysis by project
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Component_Count,
       SUM(c.estimatedWeight) AS Estimated_Weight_kg,
       SUM(c.actualWeight) AS Actual_Weight_kg,
       SUM(c.actualWeight) - SUM(c.estimatedWeight) AS Weight_Variance_kg,
       ROUND(100.0 * (SUM(c.actualWeight) - SUM(c.estimatedWeight)) / SUM(c.estimatedWeight), 2) AS Variance_Percentage
ORDER BY Actual_Weight_kg DESC;

// Query: Cost analysis by project
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyEstimatedCost) AS Estimated_Cost,
       SUM(c.assemblyActualCost) AS Actual_Cost,
       SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost) AS Cost_Variance,
       ROUND(100.0 * (SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost)) / SUM(c.assemblyEstimatedCost), 2) AS Variance_Percentage
ORDER BY Actual_Cost DESC;

// Query: Procurement status report
MATCH (c:Component)
RETURN c.procurementStatus AS Procurement_Status,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Cost,
       AVG(c.actualWeight) AS Avg_Weight_kg
ORDER BY Component_Count DESC;

// Query: Stock inventory report
MATCH (c:Component)
WHERE c.stockQuantity > 0
RETURN c.stockLocation AS Location,
       COUNT(c) AS Parts_In_Stock,
       SUM(c.stockQuantity) AS Total_Quantity,
       SUM(c.assemblyActualCost * c.stockQuantity) AS Inventory_Value
ORDER BY Inventory_Value DESC;

// Query: Components requiring engineering drawings
MATCH (c:Component)
WHERE c.engineeringDrawingRequired = true
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.componentStatus AS Status,
       c.approvalStatus AS Approval
ORDER BY c.partNumber;

// Query: Components generating evidence for ADR verification
MATCH (c:Component)-[:generatesEvidence]->(ev:Evidence)<-[:verifiedBy]-(adr:AustralianDesignRule)
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Component,
       labels(ev)[0] AS Evidence_Type,
       ev.hasName AS Evidence_Name,
       adr.hasID AS ADR_ID,
       adr.requirementName AS ADR_Requirement
ORDER BY adr.hasID;

// Query: Component readiness by milestone
MATCH (c:Component)
WITH COUNT(c) AS total,
     SUM(CASE WHEN c.usedInCarBuild = true THEN 1 ELSE 0 END) AS car_build,
     SUM(CASE WHEN c.usedInShakeDown = true THEN 1 ELSE 0 END) AS shake_down,
     SUM(CASE WHEN c.usedInTrackTest01 = true THEN 1 ELSE 0 END) AS track_test_01,
     SUM(CASE WHEN c.usedInTrackTest02 = true THEN 1 ELSE 0 END) AS track_test_02,
     SUM(CASE WHEN c.usedInCarLaunch = true THEN 1 ELSE 0 END) AS car_launch,
     SUM(CASE WHEN c.usedInPressLaunch = true THEN 1 ELSE 0 END) AS press_launch,
     SUM(CASE WHEN c.usedInRoadTest01 = true THEN 1 ELSE 0 END) AS road_test
RETURN "Car Build" AS Milestone, car_build AS Components_Ready, ROUND(100.0 * car_build / total, 2) AS Percentage
UNION
MATCH (c:Component)
WITH COUNT(c) AS total,
     SUM(CASE WHEN c.usedInShakeDown = true THEN 1 ELSE 0 END) AS shake_down
RETURN "Shake-Down" AS Milestone, shake_down AS Components_Ready, ROUND(100.0 * shake_down / total, 2) AS Percentage
UNION
MATCH (c:Component)
WITH COUNT(c) AS total,
     SUM(CASE WHEN c.usedInTrackTest01 = true THEN 1 ELSE 0 END) AS track_test_01
RETURN "Track Test 01" AS Milestone, track_test_01 AS Components_Ready, ROUND(100.0 * track_test_01 / total, 2) AS Percentage
UNION
MATCH (c:Component)
WITH COUNT(c) AS total,
     SUM(CASE WHEN c.usedInCarLaunch = true THEN 1 ELSE 0 END) AS car_launch
RETURN "Car Launch" AS Milestone, car_launch AS Components_Ready, ROUND(100.0 * car_launch / total, 2) AS Percentage
UNION
MATCH (c:Component)
WITH COUNT(c) AS total,
     SUM(CASE WHEN c.usedInRoadTest01 = true THEN 1 ELSE 0 END) AS road_test
RETURN "Road Test 01" AS Milestone, road_test AS Components_Ready, ROUND(100.0 * road_test / total, 2) AS Percentage
ORDER BY Milestone;

// Query: Department workload analysis
MATCH (c:Component)-[:belongsToDepartment]->(d:Department)
RETURN d.hasName AS Department,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Budget,
       SUM(c.actualWeight) AS Total_Weight_kg,
       COLLECT(DISTINCT c.supplier)[0..5] AS Top_Suppliers
ORDER BY Component_Count DESC;

// Query: Comprehensive component tracking report
MATCH (c:Component)
OPTIONAL MATCH (c)-[:usedInProject]->(p:Project)
OPTIONAL MATCH (c)-[:belongsToDepartment]->(d:Department)
OPTIONAL MATCH (c)-[:suppliedBy]->(s:IndustryPartner)
OPTIONAL MATCH (c)-[:usedInADR]->(adr:AustralianDesignRule)
RETURN d.hasName AS Department,
       p.projectID AS Project_ID,
       c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.quantityPer AS Qty,
       c.usedInCarBuild AS Car_Build,
       c.usedInShakeDown AS Shake_Down,
       c.usedInTrackTest01 AS Track_Test_01,
       c.relatedADRs AS ADRs,
       c.engineeringDrawingRequired AS Eng_Dwg,
       c.estimatedWeight AS Est_Weight,
       c.actualWeight AS Actual_Weight,
       c.procurementStatus AS Procurement,
       s.hasName AS Supplier,
       c.assemblyEstimatedCost AS Est_Cost,
       c.assemblyActualCost AS Actual_Cost,
       c.orderStatus AS Order_Status,
       c.stockQuantity AS Stock_Qty,
       c.stockLocation AS Stock_Location
ORDER BY d.hasName, p.projectID, c.partNumber;

// ============================================================
// END OF CYPHER EXAMPLES
// ============================================================
