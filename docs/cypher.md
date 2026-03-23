# SR8 Ontology - neo4j Cypher Reference
---

## Table of Contents

1. [Database Setup](#database-setup)
2. [Sample Data Creation](#sample-data-creation)
3. [Quick Start Queries](#quick-start-queries)
4. [Component Management](#component-management)
5. [ADR Verification Tracking](#adr-verification-tracking)
6. [Integration & Analytics](#integration--analytics)
7. [Import & Validation](#import--validation)
8. [Command Line Access](#command-line-access)

---

## Data-Base Setup

### Step 1: Create Constraints

Run these first to ensure data integrity:

```cypher
CREATE CONSTRAINT sr8_req_id IF NOT EXISTS
FOR (r:Requirement) REQUIRE r.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_comp_id IF NOT EXISTS
FOR (c:Component) REQUIRE c.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_adr_id IF NOT EXISTS
FOR (a:AustralianDesignRule) REQUIRE a.hasID IS UNIQUE;

CREATE CONSTRAINT sr8_subsys_id IF NOT EXISTS
FOR (s:Subsystem) REQUIRE s.hasID IS UNIQUE;
```

### Step 2: Create Indexes For Performance

```cypher
CREATE INDEX req_name IF NOT EXISTS
FOR (r:Requirement) ON (r.hasName);

CREATE INDEX comp_name IF NOT EXISTS
FOR (c:Component) ON (c.hasName);

CREATE INDEX subsys_name IF NOT EXISTS
FOR (s:Subsystem) ON (s.hasName);

CREATE INDEX node_label_name IF NOT EXISTS 
FOR (n:NodeLabel) ON (n.name);
```

---

## Sample Data Creation

### Organizations & Project Tracking Systems

```cypher
// Create Organization
CREATE (org:Organization {
    hasID: "ORG-001",
    hasName: "Sunswift Racing Organization",
    numberOfMembers: 80,
    numberOfDepartments: 16,
    numberOfProjects: 189,
    hasDescription: "World-leading student solar-electric vehicle team"
});

// Create Industry Partner
CREATE (partner:IndustryPartner {
    hasID: "PARTNER-001",
    hasName: "Industry Partner A",
    hasDescription: "Strategic technology partner"
});

// Create Project Tracking System
CREATE (veh:ProjectTrackingSystem {
    hasID: "VEH-001",
    hasName: "Sunswift 8",
    hasDescription: "World's first road-legal, student-built, tri-brid electric vehicle",
    isRoadLegal: true,
    numberOfComponents: 100000,
    numberOfRequirements: 600000
});

// Create System
CREATE (sys:System {
    hasID: "SYS-001",
    hasName: "Propulsion System",
    hasDescription: "System-level grouping containing multiple subsystems"
});

// Create Relationship
MATCH (o:Organization), (p:IndustryPartner)
WHERE o.hasID = "ORG-001" AND p.hasID = "PARTNER-001"
CREATE (o)-[:collaboratesWith]->(p);
```

### Sub-Systems

```cypher
// Create Subsystems
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

// Link Subsystems To System
MATCH (sys:System), (b:Subsystem), (p:Subsystem), (s:Subsystem)
WHERE sys.hasID = "SYS-001"
  AND b.hasID = "SS-BATT"
  AND p.hasID = "SS-PWTR"
  AND s.hasID = "SS-SAFE"
CREATE (sys)-[:hasSubsystem]->(b),
             (sys)-[:hasSubsystem]->(p),
             (sys)-[:hasSubsystem]->(s);

// Create interface Relationships (Subsystem + System)
MATCH (b:Subsystem), (p:Subsystem), (s:Subsystem)
WHERE b.hasID = "SS-BATT"
  AND p.hasID = "SS-PWTR"
  AND s.hasID = "SS-SAFE"
CREATE (b)-[:interface]->(p),
       (b)-[:interface]->(s),
       (p)-[:interface]->(s);

CREATE (thermal:System {
        hasID: "SYS-002",
        hasName: "Thermal Management System",
        hasDescription: "System managing cooling and thermal controls"
});

MATCH (sys1:System {hasID: "SYS-001"}), (sys2:System {hasID: "SYS-002"})
CREATE (sys1)-[:interface]->(sys2);

// Risk Propagation
MATCH (b:Subsystem), (p:Subsystem)
WHERE b.hasID = "SS-BATT" AND p.hasID = "SS-PWTR"
CREATE (b)-[:propagatesRiskTo]->(p);
```

### ADRs & Requirements

```cypher
// Create ADR-042 With Related Nodes
CREATE (adr42:AustralianDesignRule {
    hasID: "ADR-042",
    hasName: "General Safety Requirements",
    hasDescription: "Requirements for general safety provisions",
    isVerified: false,
    usesAlternativeTesting: true,
    rightProjectAssigned: true
})

CREATE (clause42:Clause {hasID: "CLAUSE-042", hasName: "42.1"})
CREATE (reqName42:RequirementName {hasID: "REQNAME-042", hasName: "General Safety Provisions"})
CREATE (reqDesc42:RequirementDescription {
    hasID: "REQDESC-042",
    hasName: "Requirements for general safety provisions and crash protection"
})

CREATE (adr42)-[:hasClause]->(clause42)
CREATE (adr42)-[:hasRequirementName]->(reqName42)
CREATE (adr42)-[:hasRequirementDescription]->(reqDesc42);

// Create ADR-063 With Related Nodes
CREATE (adr63:AustralianDesignRule {
    hasID: "ADR-063",
    hasName: "Light Vehicle Braking Systems",
    hasDescription: "Braking system performance and safety",
    isVerified: false
})

CREATE (clause63:Clause {hasID: "CLAUSE-063", hasName: "63.3.1"})
CREATE (reqName63:RequirementName {hasID: "REQNAME-063", hasName: "Emergency Braking Performance"})
CREATE (reqDesc63:RequirementDescription {
    hasID: "REQDESC-063",
    hasName: "Braking system performance and safety requirements"
})

CREATE (adr63)-[:hasClause]->(clause63)
CREATE (adr63)-[:hasRequirementName]->(reqName63)
CREATE (adr63)-[:hasRequirementDescription]->(reqDesc63);

// Create Essential Requirements
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
    hasDescription: "System must achieve specified braking distance",
    isEssential: true,
    isConditional: false,
    hasRiskLevel: "Critical",
    hasConfidenceScore: 0.99,
    hasProvenance: "Extracted from ADR-063"
});

// Create Recommended Requirement
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

// Link Requirements To ADRs & Sub-Systems
MATCH (r1:Requirement), (adr42:AustralianDesignRule), (b:Subsystem)
WHERE r1.hasID = "REQ-ADR42-001" AND adr42.hasID = "ADR-042" AND b.hasID = "SS-BATT"
CREATE (r1)-[:derivedFrom]->(adr42)
CREATE (r1)-[:appliesTo]->(b);

MATCH (r2:Requirement), (adr63:AustralianDesignRule)
WHERE r2.hasID = "REQ-ADR63-001" AND adr63.hasID = "ADR-063"
CREATE (r2)-[:derivedFrom]->(adr63);

MATCH (r3:Requirement), (b:Subsystem), (r1:Requirement)
WHERE r3.hasID = "REQ-INT-001" AND b.hasID = "SS-BATT" AND r1.hasID = "REQ-ADR42-001"
CREATE (r3)-[:appliesTo]->(b)
CREATE (r3)-[:dependsOn]->(r1);
```

### Components

```cypher
// Create Component With All Properties
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

// Create/Match Related Entities
MERGE (dept:Department {hasID: "DEPT-ELEC"})
ON CREATE SET dept.hasName = "Electrical Engineering"

MERGE (proj:Project {projectID: "PROJ-ELEC-01"})
ON CREATE SET proj.hasName = "Electrical Systems"

MERGE (supplier:IndustryPartner {hasName: "Texas Instruments"})

// Create Test Evidence
CREATE (testEv:TestEvidence {
    hasID: "EV-BMS-001",
    hasName: "BMS Functional Test Results",
    hasDescription: "Complete functional testing of BMS under various load conditions"
})

// Link Component
MATCH (c:Component), (d:Department), (p:Project), (s:IndustryPartner), (ev:TestEvidence), (adr:AustralianDesignRule)
WHERE c.hasID = "COMP-ELEC-BMS-001" 
  AND d.hasID = "DEPT-ELEC"
  AND p.projectID = "PROJ-ELEC-01"
  AND s.hasName = "Texas Instruments"
  AND ev.hasID = "EV-BMS-001"
  AND adr.hasID = "ADR-042"
CREATE (c)-[:belongsToDepartment]->(d)
CREATE (c)-[:usedInProject]->(p)
CREATE (c)-[:suppliedBy]->(s)
CREATE (c)-[:generatesEvidence]->(ev)
CREATE (c)-[:usedInADR]->(adr);
```

### Verification Procedures

```cypher
// Create Verification Procedure
CREATE (proc:VerificationProcedure {
    hasID: "VP-042-001",
    hasName: "Headlamp Photometric Test",
    verificationMethodDescription: "Photometric testing using calibrated lux meter at specified distances and angles"
})

CREATE (method:Test {hasID: "VM-TEST-001", hasName: "Physical Testing"})

CREATE (evidence:TestEvidence {
    hasID: "EV-042-001",
    hasName: "Photometric Test Results",
    hasDescription: "Test results showing compliance with illumination requirements",
    hasTimestamp: datetime()
})

// Link Verification Workflow
MATCH (adr:AustralianDesignRule), (proc:VerificationProcedure), (method:Test), (ev:TestEvidence)
WHERE adr.hasID = "ADR-042" 
  AND proc.hasID = "VP-042-001"
  AND method.hasID = "VM-TEST-001"
  AND ev.hasID = "EV-042-001"
CREATE (adr)-[:hasVerificationProcedure]->(proc)
CREATE (proc)-[:hasVerificationMethod]->(method)
CREATE (proc)-[:supportedByEvidence]->(ev)
CREATE (adr)-[:verifiedBy]->(ev);
```

---

## Quick Start Queries

### Ontology Structure

```cypher
// View Complete Ontology Structure
MATCH (n:SchemaLabel)-[r:SUBCLASS_OF*]->(root)
WHERE root.type = 'TopLevel'
RETURN n, r, root
LIMIT 100;

// Explore Requirement Hierarchy
MATCH path = (:SchemaLabel {name: 'Requirement'})<-[:SUBCLASS_OF*]-(child)
RETURN path;

// Count Classes By Category
MATCH (n:SchemaLabel)
RETURN n.category as Category, count(*) as Count
ORDER BY Count DESC;

// View All Relationship Types
MATCH (r:SchemaRelationship)
RETURN r.name, r.sourceLabel, r.targetLabel, r.description;

// View Requirements-Related Relationships
MATCH (r:SchemaRelationship)
WHERE r.sourceLabel = 'Requirement' OR r.targetLabel = 'Requirement'
RETURN r.name, r.sourceLabel, r.targetLabel;
```

### Basic Operational Queries

```cypher
// View All Components By Project
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Components,
       SUM(c.actualWeight) AS Total_Weight_kg
ORDER BY Components DESC;

// ADR Verification Status
MATCH (adr:AustralianDesignRule)
RETURN adr.isVerified AS Verified,
       COUNT(adr) AS Count
ORDER BY Verified DESC;

// Component Life-Cycle Progress
MATCH (c:Component)
RETURN 
    SUM(CASE WHEN c.usedInCarBuild THEN 1 ELSE 0 END) AS Car_Build_Ready,
    SUM(CASE WHEN c.usedInTrackTest01 THEN 1 ELSE 0 END) AS Track_Test_Ready,
    SUM(CASE WHEN c.usedInRoadTest01 THEN 1 ELSE 0 END) AS Road_Test_Ready;

// Find All Subsystems Interfacing With Battery
MATCH (b:Subsystem {hasName: "Battery Subsystem"})-[:interface]-(other:Subsystem)
RETURN other.hasName, other.hasRiskLevel;

// Find interface Connections Across Systems/SubSystems
MATCH (a)-[:interface]-(b)
WHERE (a:System OR a:Subsystem)
    AND (b:System OR b:Subsystem)
RETURN labels(a)[0] AS FromType,
             a.hasName AS FromName,
             labels(b)[0] AS ToType,
             b.hasName AS ToName;

// Find Requirement Dependency Chains
MATCH path = (r1:Requirement)-[:dependsOn*]->(r2:Requirement)
WHERE r1.hasID = "REQ-INT-001"
RETURN path;
```

---

## Component Management

### Component Tracking Queries

```cypher
// All Components By Project With Costs
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Component_Count,
       SUM(c.actualWeight) AS Total_Weight_kg,
       SUM(c.assemblyActualCost) AS Total_Cost
ORDER BY Component_Count DESC;

// Weight Variance Analysis
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       SUM(c.estimatedWeight) AS Estimated_Weight_kg,
       SUM(c.actualWeight) AS Actual_Weight_kg,
       SUM(c.actualWeight) - SUM(c.estimatedWeight) AS Variance_kg,
       ROUND(100.0 * (SUM(c.actualWeight) - SUM(c.estimatedWeight)) / 
             SUM(c.estimatedWeight), 2) AS Variance_Percent
ORDER BY Actual_Weight_kg DESC;

// Cost Analysis By Project
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       SUM(c.assemblyEstimatedCost) AS Estimated_Cost,
       SUM(c.assemblyActualCost) AS Actual_Cost,
       SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost) AS Variance,
       ROUND(100.0 * (SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost)) /
             SUM(c.assemblyEstimatedCost), 2) AS Variance_Percent
ORDER BY Actual_Cost DESC;

// Stock Inventory Report
MATCH (c:Component)
WHERE c.stockQuantity > 0
RETURN c.stockLocation AS Location,
       COUNT(c) AS Parts_Count,
       SUM(c.stockQuantity) AS Total_Quantity,
       SUM(c.assemblyActualCost * c.stockQuantity) AS Inventory_Value
ORDER BY Inventory_Value DESC;

// Components By Supplier
MATCH (c:Component)-[:suppliedBy]->(s:IndustryPartner)
RETURN s.hasName AS Supplier,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Cost,
       COLLECT(c.partNumber)[0..5] AS Sample_Parts
ORDER BY Component_Count DESC;

// Procurement Status Report
MATCH (c:Component)
RETURN c.procurementStatus AS Procurement_Status,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Cost,
       AVG(c.actualWeight) AS Avg_Weight_kg
ORDER BY Component_Count DESC;

// Components Requiring Engineering Drawings
MATCH (c:Component)
WHERE c.engineeringDrawingRequired = true
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.componentStatus AS Status,
       c.approvalStatus AS Approval
ORDER BY c.partNumber;

// Department Workload Analysis
MATCH (c:Component)-[:belongsToDepartment]->(d:Department)
RETURN d.hasName AS Department,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Budget,
       SUM(c.actualWeight) AS Total_Weight_kg
ORDER BY Component_Count DESC;

// Comprehensive Component Report
MATCH (c:Component)
OPTIONAL MATCH (c)-[:usedInProject]->(p:Project)
OPTIONAL MATCH (c)-[:belongsToDepartment]->(d:Department)
OPTIONAL MATCH (c)-[:suppliedBy]->(s:IndustryPartner)
RETURN d.hasName AS Department,
       p.projectID AS Project_ID,
       c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.relatedADRs AS ADRs,
       c.actualWeight AS Weight_kg,
       s.hasName AS Supplier,
       c.assemblyActualCost AS Cost,
       c.stockQuantity AS Stock,
       c.stockLocation AS Location
ORDER BY d.hasName, p.projectID, c.partNumber;
```

---

## ADR Verification Tracking

### Verification Status Queries

```cypher
// All ADRs With Verification Status
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasVerificationProcedure]->(proc:VerificationProcedure)
OPTIONAL MATCH (proc)-[:supportedByEvidence]->(ev:TestingEvidence)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
RETURN adr.hasID AS ADR_ID,
       reqName.hasName AS Requirement,
       adr.isVerified AS Verified,
       proc.hasName AS Procedure,
       ev.hasName AS Evidence
ORDER BY adr.hasID;

// Unverified ADRs
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
OPTIONAL MATCH (adr)-[:hasClause]->(clause:Clause)
WHERE adr.isVerified = false
RETURN adr.hasID AS ADR_ID,
       reqName.hasName AS Requirement,
       clause.hasName AS Clause
ORDER BY adr.hasID;

// Verification Completion By Project
MATCH (p:Project)<-[:assignedToProject]-(adr:AustralianDesignRule)
WITH p,
     SUM(CASE WHEN adr.isVerified = true THEN 1 ELSE 0 END) AS verified,
     COUNT(adr) AS total
RETURN p.hasName AS Project,
       total AS Total_ADRs,
       verified AS Verified_ADRs,
       ROUND(100.0 * verified / total, 2) AS Completion_Percent
ORDER BY Completion_Percent DESC;

// ADRs By Verification Method
MATCH (adr:AustralianDesignRule)-[:hasVerificationProcedure]->
      (proc:VerificationProcedure)-[:hasVerificationMethod]->(method)
RETURN labels(method)[0] AS Verification_Method,
       COUNT(adr) AS ADR_Count,
       COLLECT(adr.hasID)[0..5] AS Sample_ADRs
ORDER BY ADR_Count DESC;

// ADRs Using Alternative Testing Methods
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
OPTIONAL MATCH (adr)-[:hasClause]->(clause:Clause)
WHERE adr.usesAlternativeTesting = true
RETURN adr.hasID AS ADR_ID,
       reqName.hasName AS Requirement,
       clause.hasName AS Clause
ORDER BY adr.hasID;

// ADRs Missing Verification Procedures
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
OPTIONAL MATCH (adr)-[:hasClause]->(clause:Clause)
WHERE NOT (adr)-[:hasVerificationProcedure]->(:VerificationProcedure)
RETURN adr.hasID AS ADR_ID,
       reqName.hasName AS Requirement,
       clause.hasName AS Clause,
       "Missing Verification Procedure" AS Status;

// ADRs Missing Evidence
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
WHERE NOT (adr)-[:verifiedBy]->(:TestingEvidence)
RETURN adr.hasID AS ADR_ID,
       reqName.hasName AS Requirement,
       "Missing Evidence" AS Status;

// Full Verification Workflow Path
MATCH path = (adr:AustralianDesignRule)-[:hasVerificationProcedure]->
             (proc:VerificationProcedure)-[:hasVerificationMethod]->
             (method:VerificationMethod)
MATCH (proc)-[:supportedByEvidence]->(ev:TestingEvidence)
RETURN adr.hasID AS ADR,
       proc.hasName AS Procedure,
       labels(method)[0] AS Method,
       labels(ev)[0] AS EvidenceType,
       ev.hasName AS EvidenceName;

// Comprehensive ADR Verification Checklist
MATCH (adr:AustralianDesignRule)
OPTIONAL MATCH (adr)-[:assignedToProject]->(p:Project)
OPTIONAL MATCH (adr)-[:assignedToDepartment]->(d:Department)
OPTIONAL MATCH (adr)-[:hasVerificationProcedure]->(proc:VerificationProcedure)
OPTIONAL MATCH (proc)-[:hasVerificationMethod]->(method:VerificationMethod)
OPTIONAL MATCH (proc)-[:supportedByEvidence]->(ev:TestingEvidence)
OPTIONAL MATCH (adr)-[:hasClause]->(clause:Clause)
OPTIONAL MATCH (adr)-[:hasRequirementName]->(reqName:RequirementName)
RETURN clause.hasName AS Clause,
       reqName.hasName AS Requirement_Name,
       p.projectID AS Project_ID,
       p.hasName AS Project,
       d.hasName AS Department,
       adr.usesAlternativeTesting AS Alternative_Testing,
       labels(method)[0] AS Verification_Method,
       labels(ev)[0] AS Evidence_Type,
       adr.isVerified AS Verified
ORDER BY adr.hasID;
```

---

## Integration & Analytics

### Requirements & Traceability

```cypher
// Find Requirements For The Battery Management System
MATCH (bms:Component {hasName: "Battery Management System"})
      -[:appliesTo]-(req:Requirement)
      -[:derivedFrom]->(adr:AustralianDesignRule)
RETURN bms.hasName, req.hasDescription, adr.hasName;

// Trace Requirement Back To ADR
MATCH (r:Requirement {hasID: "REQ-ADR42-001"})-[:derivedFrom]->(adr:AustralianDesignRule)
RETURN r.hasName, adr.hasName, adr.hasDescription;

// Requirement Dependencies
MATCH (r1:Requirement)-[:dependsOn*]->(r2:Requirement)
WHERE r1.hasID = "ADR-42-3.1"
RETURN r1, r2;

// Compliance Gap Analysis - Non-Compliant Components
MATCH (c:Component)-[:appliesTo]-(req:Requirement)
      -[:derivedFrom]->(adr:AustralianDesignRule)
WHERE NOT (c)-[:compliesWith]->(adr)
RETURN c.hasName, adr.hasName, req.hasDescription;

// All Essential Vs Recommended Requirements
MATCH (r:Requirement)
RETURN r.isEssential, COUNT(r) AS count;

// Low-Confidence AI Inferences For Review
MATCH (r:Requirement)-[:inferredBy]->(agent:Agent)
WHERE r.hasConfidenceScore < 0.90
RETURN r.hasName, r.hasConfidenceScore, agent.hasName, r.hasProvenance
ORDER BY r.hasConfidenceScore ASC;
```

### Risk Analysis

```cypher
// Risk Propagation Paths From Battery
MATCH path = (battery:Subsystem {hasName: "Battery Subsystem"})
      -[:propagatesRiskTo*1..3]->(affected:Subsystem)
RETURN affected.hasName, affected.hasRiskLevel
ORDER BY affected.hasRiskLevel DESC;

// Risk Propagation Analysis
MATCH path = (source:Subsystem)-[:propagatesRiskTo*]->(target:Subsystem)
WHERE source.hasName = "Battery Subsystem"
RETURN path;
```

### Cross-Department Integration

```cypher
// Interfaces Between Powertrain & Electronics Departments
MATCH (d1:Department {hasName: "Powertrain"})-[:owns]->(s1:Subsystem)
      -[:interface]-(s2:Subsystem)<-[:owns]-(d2:Department {hasName: "Electronics"})
RETURN s1.hasName, s2.hasName;

// Find All Projects With Departments
MATCH (p:Project)
OPTIONAL MATCH (p)-[:hasPrimaryDepartment]->(primary:Department)
OPTIONAL MATCH (p)-[:hasSecondaryDepartment]->(secondary:Department)
OPTIONAL MATCH (p)-[:hasAssignee]->(m:Members)
RETURN p.projectID, p.projectName, 
       primary.hasName AS PrimaryDept,
       secondary.hasName AS SecondaryDept,
       m.hasName AS Assignee;
```

### Evidence & Traceability

```cypher
// Components Generating ADR Evidence
MATCH (c:Component)-[:generatesEvidence]->(ev:TestingEvidence)
      <-[:verifiedBy]-(adr:AustralianDesignRule)
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Component,
       labels(ev)[0] AS Evidence_Type,
       adr.hasID AS ADR_ID
ORDER BY adr.hasID;

// Complete Traceability Path
MATCH path = (c:Component)-[:usedInProject]->(p:Project),
             (c)-[:generatesEvidence]->(ev:TestingEvidence),
             (ev)<-[:verifiedBy]-(adr:AustralianDesignRule),
             (adr)-[:assignedToProject]->(p)
RETURN c.partNumber AS Component,
       p.hasName AS Project,
       labels(ev)[0] AS Evidence_Type,
       adr.hasID AS ADR,
       adr.isVerified AS Verified
ORDER BY adr.hasID;
```

### Advanced Analytics

```cypher
// Project Readiness Dashboard
MATCH (p:Project)
OPTIONAL MATCH (p)<-[:usedInProject]-(c:Component)
OPTIONAL MATCH (p)<-[:assignedToProject]-(adr:AustralianDesignRule)
RETURN p.projectID,
       p.projectName,
       count(DISTINCT c) AS ComponentCount,
       count(DISTINCT adr) AS ADRCount,
       count(DISTINCT CASE WHEN adr.isVerified THEN adr END) AS VerifiedADRs,
       ROUND(100.0 * count(DISTINCT CASE WHEN adr.isVerified THEN adr END) / 
             count(DISTINCT adr), 1) AS VerificationProgress
ORDER BY p.projectID;

// Count Total Relationships By Type
MATCH ()-[r]->()
RETURN type(r) AS relationshipType, COUNT(r) AS count
ORDER BY count DESC;

// Find Most Connected Subsystems
MATCH (s:Subsystem)
OPTIONAL MATCH (s)-[r]-()
RETURN s.hasName, COUNT(r) AS connectionCount
ORDER BY connectionCount DESC;

// Find Orphaned Requirements (No ADR Source)
MATCH (r:Requirement)
WHERE NOT (r)-[:derivedFrom]->(:AustralianDesignRule)
RETURN r.hasID, r.hasName, r.hasProvenance;
```

---

## Import & Validation

### Import Schema From CSV

#### Method 1: Using neo4j Browser

```cypher
// Load Node Labels
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
CREATE (n:NodeLabel {
    name: row.Label,
    parent: row.ParentLabel,
    description: row.Description,
    type: row.Type,
    category: row.Category
});
```

#### Method 2: Using Cypher Script

```cypher
// Import Node Labels
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
MERGE (n:SchemaLabel {name: row.Label})
SET n.parent = row.ParentLabel,
    n.description = row.Description,
    n.type = row.Type,
    n.category = row.Category;

// Import Relationships
LOAD CSV WITH HEADERS FROM 'file:///neo4j-relationships.csv' AS row
MERGE (r:SchemaRelationship {name: row.RelationshipType})
SET r.sourceLabel = row.SourceLabel,
    r.targetLabel = row.TargetLabel,
    r.description = row.Description,
    r.properties = row.Properties;

// Import Properties
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-properties.csv' AS row
MERGE (p:SchemaProperty {name: row.PropertyName})
SET p.applicableLabels = row.ApplicableLabels,
    p.dataType = row.DataType,
    p.description = row.Description,
    p.constraints = row.Constraints;
```

### Validation Queries

```cypher
// Count Labels By Category
MATCH (n:SchemaLabel)
RETURN n.category, count(*) as count
ORDER BY count DESC;

// Check Hierarchy
MATCH (child:SchemaLabel)-[:SUBCLASS_OF]->(parent:SchemaLabel)
RETURN child.name, parent.name;

// List All Relationships
MATCH (r:SchemaRelationship)
RETURN r.name, r.sourceLabel, r.targetLabel;

// Find Hierarchical Depth
MATCH path = (n:SchemaLabel)-[:hasParent*]->(root:SchemaLabel)
WHERE NOT (root)-[:hasParent]->()
RETURN n.name, length(path) as depth
ORDER BY depth DESC;

// Show All Indexes
SHOW INDEXES;

// Show All Constraints
SHOW CONSTRAINTS;

// Find All Labels In Organization Category
MATCH (n:SchemaLabel)
WHERE n.category = 'Organization'
RETURN n.name, n.description;

// Get Relationship Hierarchy
MATCH (r:SchemaRelationship)
WHERE r.sourceLabel = 'Requirement'
RETURN r.name, r.targetLabel;

// Find Properties For A Label
MATCH (p:SchemaProperty)
WHERE p.applicableLabels CONTAINS 'Requirement' OR p.applicableLabels = 'All'
RETURN p.name, p.dataType, p.description;
```

---

## Command Line Access

### Using cypher-shell

```bash
# View Top-Level Categories
cypher-shell -u neo4j -p password123 \
  "MATCH (n:SchemaLabel) WHERE n.type = 'TopLevel' RETURN n.name, n.description;"

# Count All Nodes
cypher-shell -u neo4j -p password123 \
  "MATCH (n:SchemaLabel) RETURN n.category, count(*) ORDER BY count(*) DESC;"

# View All Relationships
cypher-shell -u neo4j -p password123 \
  "MATCH (r:SchemaRelationship) RETURN r.name LIMIT 10;"
```

---
