# SR8 Thesis Ontology - Neo4j Database

## Overview

This repository contains a comprehensive OWL/RDF ontology for the Sunswift Racing SR8 tri-brid electric vehicle project, structured around three integrated management systems.

**Ontology Statistics:**
- 48 classes (node labels) including Member class
- 37 object properties (relationships)
- 56 data properties (attributes)
- 185+ total semantic elements

## Quick Start

## Accessing Neo4j Browser

### Start neo4j

```bash
brew services start neo4j
```

### Open neo4j Browser

Open your browser and navigate to:
```
http://localhost:7474
```

Or run:
```bash
open http://localhost:7474
```

### Login Credentials

- **Connect URL:** `bolt://localhost:7687`
- **Username:** `neo4j`
- **Password:** `password123`

## Key Features

✅ **Project Tracking System** - 189 projects with primary/secondary departments and 100 member assignees  
✅ **ADR Management** - Track 100 Australian Design Rules with 4 verification types (Inspection, Demonstration, Test, Analysis)  
✅ **Component Management** - Full BOM hierarchy with part-to-project-to-ADR traceability  
✅ **Verification Evidence** - 6 evidence types aligned with verification methods (Inspection, Demonstration, Test, Analysis, ADR Annex, ADR Testing Procedure)  
✅ **Multi-System Integration** - Seamless connections between Projects, Parts, and ADRs  
✅ **Supply Chain** - Supplier, procurement, and inventory management

## Core Systems

### 1. Project Tracking System (189 Projects)
- **Projects**: projectID, projectName, projectDescription
- **Departments** (15): Primary and Secondary assignments
- **Members** (100): Project assignees/owners
- **Relationships**: hasPrimaryDepartment, hasSecondaryDepartment, hasAssignee

### 2. Parts Management System
- **Components**: partNumber, partDescription, bomLevel
- **BOM Hierarchy**: Multi-level assembly structure
- **Project Linkage**: usedInProject relationship
- **ADR Compliance**: relatedADRs, usedInADR
- **Supply Chain**: suppliedBy → IndustryPartner

### 3. ADR Management System (100 ADRs)
- **ADR Related Nodes**: Clause (each clause is a new node connected to 1 ADR)
- **ADR Properties**: requirementName, requirementDescription
- **Verification Methods**: Inspection, Demonstration, Test, Analysis (Simulations/Calculations)
- **Testing Procedures**: testingProcedurePerRequirement
- **Project/Department Links**: assignedToProject, hasRelevantProject, hasRelevantDepartment
- **Evidence Tracking**: verifiedBy → InspectionEvidence, DemonstrationEvidence, TestEvidence, AnalysisEvidence, ADRAnnexEvidence, ADRTestingProcedureEvidence

## Quick Start Queries

### 1. View All Components by Project

```cypher
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Components,
       SUM(c.actualWeight) AS Total_Weight_kg
ORDER BY Components DESC;
```

### 2. ADR Verification Status

```cypher
MATCH (adr:AustralianDesignRule)
RETURN adr.isVerified AS Verified,
       COUNT(adr) AS Count
ORDER BY Verified DESC;
```

### 3. Component Life-Cycle Progress

```cypher
MATCH (c:Component)
RETURN 
    SUM(CASE WHEN c.usedInCarBuild THEN 1 ELSE 0 END) AS Car_Build_Ready,
    SUM(CASE WHEN c.usedInTrackTest01 THEN 1 ELSE 0 END) AS Track_Test_Ready,
    SUM(CASE WHEN c.usedInRoadTest01 THEN 1 ELSE 0 END) AS Road_Test_Ready;
```

### 2. View Complete Ontology Structure

```cypher
MATCH (n:SchemaLabel)-[r:SUBCLASS_OF*]->(root)
WHERE root.type = 'TopLevel'
RETURN n, r, root
LIMIT 100
```

### 3. Explore Artifact Hierarchy

```cypher
MATCH path = (:SchemaLabel {name: 'Artifact'})<-[:SUBCLASS_OF*]-(child)
RETURN path
```

### 4. View All Relationship Types

```cypher
MATCH (r:SchemaRelationship)
RETURN r.name, r.sourceLabel, r.targetLabel, r.description
```

### 5. Count Classes By Category

```cypher
MATCH (n:SchemaLabel)
RETURN n.category as Category, count(*) as Count
ORDER BY Count DESC
```

### 5. View Requirements-Related Relationships

```cypher
MATCH (r:SchemaRelationship)
WHERE r.sourceLabel = 'Requirement' OR r.targetLabel = 'Requirement'
RETURN r.name, r.sourceLabel, r.targetLabel
```

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

## Workflow Summary

```
DATA SOURCES
    ↓
KNOWLEDGE EXTRACTION
    • Document parsing (PDFMiner, Tesseract)
    • NLP processing (SpaCy, NLTK)
    • Entity recognition (BERT, RoBERTa)
    • Relation extraction
    • Ontology mapping (OWL/RDF)
    ↓
KNOWLEDGE GRAPH (Neo4j)
    • Structured entities
    • Semantic relationships
    • Ontology-aligned schema
    ↓
DATA VALIDATION
    • Consistency checking
    • Relationship verification
    • Completeness validation
    ↓
ENGINEERING SUPPORT
    • Compliance verification
    • Risk propagation
    • Design recommendations
    • Traceability analysis
```

---

## Usage Scenarios

### Scenario 1: Finding Requirements for a Component

**Question**: What ADR requirements apply to the Battery Management System?

**Cypher Query**:
```cypher
MATCH (bms:Component {hasName: "Battery Management System"})
      -[:appliesTo]-(req:Requirement)
      -[:derivedFrom]->(adr:AustralianDesignRule)
RETURN bms.hasName, req.hasDescription, adr.hasName
```

### Scenario 2: Tracing Risk Propagation

**Question**: What subsystems are affected if the battery has a thermal risk?

**Cypher Query**:
```cypher
MATCH (battery:Subsystem {hasName: "Battery Subsystem"})
      -[:propagatesRiskTo*1..3]->(affected:Subsystem)
RETURN affected.hasName, affected.hasRiskLevel
ORDER BY affected.hasRiskLevel DESC
```

### Scenario 3: Finding Cross-Department Interfaces

**Question**: What interfaces exist between Powertrain and Electronics departments?

**Cypher Query**:
```cypher
MATCH (d1:Department {hasName: "Powertrain"})-[:owns]->(s1:Subsystem)
      -[:interfacesWith]-(s2:Subsystem)<-[:owns]-(d2:Department {hasName: "Electronics"})
RETURN s1.hasName, s2.hasName
```

### Scenario 5: Compliance Gap Analysis

**Question**: Which components don't comply with their applicable ADRs?

**Cypher Query**:
```cypher
MATCH (c:Component)-[:appliesTo]-(req:Requirement)
      -[:derivedFrom]->(adr:AustralianDesignRule)
WHERE NOT (c)-[:compliesWith]->(adr)
RETURN c.hasName, adr.hasName, req.hasDescription
```

## Extend the Ontology

### Add a New Class
```xml
<owl:Class rdf:about="#NewSubsystem">
    <rdfs:subClassOf rdf:resource="#Subsystem"/>
    <rdfs:label>New Subsystem Type</rdfs:label>
    <rdfs:comment>Description of new subsystem</rdfs:comment>
</owl:Class>
```

### Add a New Relationship
```xml
<owl:ObjectProperty rdf:about="#newRelationship">
    <rdfs:domain rdf:resource="#SourceClass"/>
    <rdfs:range rdf:resource="#TargetClass"/>
    <rdfs:label>new relationship</rdfs:label>
</owl:ObjectProperty>
```

### Add a New Individual
```xml
<owl:NamedIndividual rdf:about="#NewInstance">
    <rdf:type rdf:resource="#ClassName"/>
    <hasName>Instance Name</hasName>
    <hasDescription>Instance description</hasDescription>
</owl:NamedIndividual>
```

---

