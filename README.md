# SR8 Thesis Ontology - Neo4j Database

## Overview

This repository contains a comprehensive OWL/RDF ontology for the Sunswift Racing SR8 tri-brid electric vehicle project, structured around three integrated management systems:

1. **Project Tracking System (PTS)** - 189 Projects, 15 Departments, 100 Members
2. **Parts Management System** - Component/BOM hierarchy with full lifecycle tracking
3. **ADR Management System** - 100 Australian Design Rules with verification tracking

**→ See [THREE-SYSTEM-ALIGNMENT.md](THREE-SYSTEM-ALIGNMENT.md) for detailed system structure**

**Ontology Statistics:**
- 106 classes (node labels) including Member class
- 46 object properties (relationships)
- 55 data properties (attributes)
- 200+ total semantic elements

## 🚀 Quick Start

**→ See [COMPLETE-SYSTEM-GUIDE.md](COMPLETE-SYSTEM-GUIDE.md) for comprehensive documentation**

**→ See [THREE-SYSTEM-ALIGNMENT.md](THREE-SYSTEM-ALIGNMENT.md) for system architecture**

**→ See [DOCUMENTATION-INDEX.md](DOCUMENTATION-INDEX.md) for documentation roadmap**

## Accessing Neo4j Browser

### Start Neo4j

```bash
brew services start neo4j
```

### Open Neo4j Browser

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
✅ **Verification Evidence** - Simulation, Mathematical, and Test evidence linked to requirements  
✅ **Multi-System Integration** - Seamless connections between Projects, Parts, and ADRs  
✅ **Supply Chain** - Supplier, procurement, and inventory management

## Core Systems

### 1. Project Tracking System (189 Projects)
- **Projects**: projectID, projectName, projectDescription
- **DTHREE-SYSTEM-ALIGNMENT.md](THREE-SYSTEM-ALIGNMENT.md)** | **Three-system architecture** (Project Tracking, Parts, ADR Management) |
| **[epartments** (15): Primary and Secondary assignments
- **Members** (100): Project assignees/owners
- **Relationships**: hasPrimaryDepartment, hasSecondaryDepartment, hasAssignee

### 2. Parts Management System
- **Components**: partNumber, partDescription, bomLevel
- **BOM Hierarchy**: Multi-level assembly structure
- **Project Linkage**: usedInProject relationship
- **ADR Compliance**: relatedADRs, usedInADR
- **Supply Chain**: suppliedBy → IndustryPartner

### 3. ADR Management System (100 ADRs)
- **ADR Attributes**: hasClause, requirementName, requirementDescription
- **Verification Methods**: Inspection, Demonstration, Test, Analysis (Simulations/Calculations)
- **Testing Procedures**: testingProcedurePerRequirement
- **Project/Department Links**: assignedToProject, hasRelevantProject, hasRelevantDepartment
- **Evidence Tracking**: verifiedBy → SimulationEvidence, MathematicalEvidence, TestEvidence

## Documentation

| Document | Description |
|----------|-------------|
| **[COMPLETE-SYSTEM-GUIDE.md](COMPLETE-SYSTEM-GUIDE.md)** | **Comprehensive system guide** (START HERE) |
| [ontology-documentation.md](ontology-documentation.md) | Detailed class/property reference |
| [ontology-quick-reference.md](ontology-quick-reference.md) | Quick reference guide |
| [neo4j-examples.cypher](neo4j-examples.cypher) | 50+ ready-to-use queries |
| [project-ontology.owl](project-ontology.owl) | OWL/RDF specification |

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

### 3. Component Lifecycle Progress

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

### 5. Count Classes by Category

```cypher
MATCH (n:SchemaLabel)
RETURN n.category as Category, count(*) as Count
ORDER BY Count DESC
```

### 6. Find All Agent Types

```cypher
MATCH (n:SchemaLabel)
WHERE n.category = 'Agent'
RETURN n.name, n.description
```

### 7. View Requirements-Related Relationships

```cypher
MATCH (r:SchemaRelationship)
WHERE r.sourceLabel = 'Requirement' OR r.targetLabel = 'Requirement'
RETURN r.name, r.sourceLabel, r.targetLabel
```

### 8. Explore Technology Stack

```cypher
MATCH (child:SchemaLabel)-[:SUBCLASS_OF*]->(parent:SchemaLabel {name: 'Technology'})
RETURN child.name as Technology, child.description
ORDER BY Technology
```

## Command Line Access

### Using cypher-shell

```bash
# View top-level categories
cypher-shell -u neo4j -p password123 \
  "MATCH (n:SchemaLabel) WHERE n.type = 'TopLevel' RETURN n.name, n.description;"

# Count all nodes
cypher-shell -u neo4j -p password123 \
  "MATCH (n:SchemaLabel) RETURN n.category, count(*) ORDER BY count(*) DESC;"

# View all relationships
cypher-shell -u neo4j -p password123 \
  "MATCH (r:SchemaRelationship) RETURN r.name LIMIT 10;"
```

## Managing Neo4j

### Stop Neo4j

```bash
brew services stop neo4j
```

### Restart Neo4j

```bash
brew services restart neo4j
```

### Check Neo4j Status

```bash
brew services info neo4j
```

## Re-importing the Ontology

If you need to re-import the ontology from scratch:

```bash
python3 import.py --uri bolt://localhost:7687 \
                  --user neo4j \
                  --password password123 \
                  --clear
```

## Files in This Repository

### Documentation
- **[COMPLETE-SYSTEM-GUIDE.md](COMPLETE-SYSTEM-GUIDE.md)** ⭐ - Comprehensive system guide (start here)
- **[DOCUMENTATION-INDEX.md](DOCUMENTATION-INDEX.md)** - Documentation navigation roadmap
- **[ontology-documentation.md](ontology-documentation.md)** - Complete class and property reference
- **[ontology-quick-reference.md](ontology-quick-reference.md)** - Quick reference guide
- **[ontology-diagrams.md](ontology-diagrams.md)** - 14 Mermaid diagrams
- **[ONTOLOGY-SUMMARY.txt](ONTOLOGY-SUMMARY.txt)** - Statistics and validation summary

### Core Ontology Files
- **[project-ontology.owl](project-ontology.owl)** - OWL/RDF ontology specification (105 classes, 43 properties)
- **[validate.py](validate.py)** - Python script to validate OWL structure

### Neo4j Integration
- **[neo4j-examples.cypher](neo4j-examples.cypher)** - 50+ ready-to-use Cypher queries
- **[neo4j-node-labels.csv](neo4j-node-labels.csv)** - Node labels mapped from OWL classes
- **[neo4j-relationships.csv](neo4j-relationships.csv)** - Relationship types from object properties
- **[neo4j-node-properties.csv](neo4j-node-properties.csv)** - Data property definitions
- **[import.py](import.py)** - Python script for automated Neo4j import
- **[NEO4J-IMPORT-GUIDE.md](NEO4J-IMPORT-GUIDE.md)** - Detailed import documentation
- **[NEO4J-CSV-SUMMARY.txt](NEO4J-CSV-SUMMARY.txt)** - CSV export summary

## Ontology Categories

### 1. Organization (7 classes)
Entities involved in the SR8 project - Sunswift Racing, departments, partners

### 2. Artifact (22 classes)
Engineering artifacts - vehicles, subsystems, components, requirements, documents

### 3. Process (15 classes)
Methodological workflows - extraction, extension, validation, orchestration

### 4. Technology (22 classes)
Technical tools - Neo4j, LLMs, NLP frameworks, AI models

### 5. Concept (15 classes)
Theoretical concepts - systems engineering, compliance, traceability

### 6. Agent (5 classes)
Computational agents - LLM Agent, Link Prediction Agent, RL Agent, Validation Agent

## Integration with Thesis

Reference this ontology in:
- **Methodology Section 5.1** - Knowledge Extraction
- **Methodology Section 5.2** - Knowledge Extension
- **Appendix** - Include sample queries and visualizations

## Support

For issues or questions about the ontology:
1. Check [COMPLETE-SYSTEM-GUIDE.md](COMPLETE-SYSTEM-GUIDE.md) for comprehensive documentation
2. Review [DOCUMENTATION-INDEX.md](DOCUMENTATION-INDEX.md) for navigation help
3. See [ontology-documentation.md](ontology-documentation.md) for detailed class reference
4. Consult [neo4j-examples.cypher](neo4j-examples.cypher) for 50+ query examples

## License

This ontology is part of the COMP4951 thesis project for Sunswift Racing SR8.
