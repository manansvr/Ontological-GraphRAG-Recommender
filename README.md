# SR8 Thesis Ontology - Neo4j Database

## Overview

This repository contains a comprehensive OWL/RDF ontology for the Sunswift Racing SR8 tri-brid electric vehicle project, imported into Neo4j graph database.

**Ontology Statistics:**
- 86 node labels (classes)
- 28 relationship types (object properties)
- 17 property definitions (data properties)
- 80 hierarchy relationships

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

## Quick Start Queries

Copy and paste these queries into the Neo4j Browser command bar:

### 1. View All Top-Level Categories

```cypher
MATCH (n:SchemaLabel)
WHERE n.type = 'TopLevel'
RETURN n
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

- **project-ontology.owl** - Complete OWL/RDF ontology specification
- **neo4j-node-labels.csv** - 86 node labels mapped from OWL classes
- **neo4j-relationships.csv** - 28 relationship types from object properties
- **neo4j-node-properties.csv** - 17 data property definitions
- **import.py** - Python script for automated Neo4j import
- **validate_ontology.py** - Python script to validate OWL structure
- **neo4j-examples.cypher** - 330 lines of example queries
- **NEO4J-IMPORT-GUIDE.md** - Detailed import documentation
- **ontology-documentation.md** - Comprehensive ontology documentation
- **ontology-diagrams.md** - 14 Mermaid diagrams
- **ontology-quick-reference.md** - Quick reference guide

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
1. Check the [ontology-documentation.md](ontology-documentation.md) for detailed explanations
2. Review [NEO4J-IMPORT-GUIDE.md](NEO4J-IMPORT-GUIDE.md) for import procedures
3. Consult [neo4j-examples.cypher](neo4j-examples.cypher) for query examples

## License

This ontology is part of the COMP4951 thesis project for Sunswift Racing SR8.
