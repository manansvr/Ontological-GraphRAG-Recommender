# Neo4j Import Guide - SR8 Ontology

## Overview
This directory contains CSV files that map the SR8 ontology to Neo4j node labels, relationships, and properties for easy import into a Neo4j graph database.

## CSV Files Created

1. **neo4j-node-labels.csv** - Maps all 86 ontology classes to Neo4j node labels
2. **neo4j-relationships.csv** - Maps all 29 object properties to Neo4j relationships
3. **neo4j-node-properties.csv** - Maps all 17 data properties to Neo4j node properties

---

## File 1: neo4j-node-labels.csv

### Structure
```
Label,ParentLabel,Description,Type,Category
```

### Fields
- **Label**: The Neo4j node label name (corresponds to owl:Class)
- **ParentLabel**: The parent class (from rdfs:subClassOf)
- **Description**: Human-readable description (from rdfs:comment)
- **Type**: Either "TopLevel" (6 main categories) or "Derived" (subclasses)
- **Category**: The root category hierarchy (Organization, Artifact, Process, Technology, Concept, Agent)

### Statistics
- **Total Labels**: 86
- **Top-Level Labels**: 6
- **Derived Labels**: 80

### Top-Level Categories
1. **Organization** (11 labels) - Entities involved in SR8 project
2. **Artifact** (27 labels) - Documents, requirements, components, vehicles
3. **Process** (13 labels) - Extraction, extension, validation workflows
4. **Technology** (21 labels) - Tools, databases, NLP, LLMs
5. **Concept** (14 labels) - Theoretical foundations, compliance, traceability
6. **Agent** (4 labels) - Multi-agent AI system components

---

## File 2: neo4j-relationships.csv

### Structure
```
RelationshipType,SourceLabel,TargetLabel,Description,Properties
```

### Fields
- **RelationshipType**: The relationship name in Neo4j (corresponds to owl:ObjectProperty)
- **SourceLabel**: Source node label (from rdfs:domain)
- **TargetLabel**: Target node label (from rdfs:range)
- **Description**: Relationship description
- **Properties**: Special properties (symmetric, transitive, inverseOf, subPropertyOf)

### Statistics
- **Total Relationships**: 28
- **Symmetric**: 3 (interfacesWith, collaboratesWith, collaboratesWithAgent)
- **Transitive**: 2 (dependsOn, hasComponent)

### Key Relationship Types
1. **Organizational**: hasDepartment, collaboratesWith
2. **Structural**: hasSubsystem, hasComponent, interfacesWith
3. **Requirements**: hasRequirement, dependsOn, appliesTo, derivedFrom
4. **Process**: hasInput, hasOutput, uses, employs
5. **Agent**: orchestratedBy, collaboratesWithAgent, inferredBy
6. **Compliance**: compliesWith, hasRisk, propagatesRiskTo

---

## File 3: neo4j-node-properties.csv

### Structure
```
PropertyName,ApplicableLabels,DataType,Description,Constraints
```

### Fields
- **PropertyName**: Property name in Neo4j (corresponds to owl:DatatypeProperty)
- **ApplicableLabels**: Which node labels can have this property
- **DataType**: Data type (string, integer, float, boolean, dateTime)
- **Description**: Property description
- **Constraints**: Value constraints (ranges, allowed values)

### Statistics
- **Total Properties**: 17
- **String**: 7
- **Integer**: 5
- **Boolean**: 3
- **Float**: 1
- **DateTime**: 1

---

## Import Instructions

### Method 1: Using Neo4j Browser (Manual)

```cypher
// 1. Load node labels
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
CREATE (n:NodeLabel {
    name: row.Label,
    parent: row.ParentLabel,
    description: row.Description,
    type: row.Type,
    category: row.Category
});

// 2. Create indexes
CREATE INDEX node_label_name IF NOT EXISTS FOR (n:NodeLabel) ON (n.name);
```

### Method 2: Using Cypher Script

Save this as `import-schema.cypher`:

```cypher
// Import node labels
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
MERGE (n:SchemaLabel {name: row.Label})
SET n.parent = row.ParentLabel,
    n.description = row.Description,
    n.type = row.Type,
    n.category = row.Category;

// Import relationships
LOAD CSV WITH HEADERS FROM 'file:///neo4j-relationships.csv' AS row
MERGE (r:SchemaRelationship {name: row.RelationshipType})
SET r.sourceLabel = row.SourceLabel,
    r.targetLabel = row.TargetLabel,
    r.description = row.Description,
    r.properties = row.Properties;

// Import properties
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-properties.csv' AS row
MERGE (p:SchemaProperty {name: row.PropertyName})
SET p.applicableLabels = row.ApplicableLabels,
    p.dataType = row.DataType,
    p.description = row.Description,
    p.constraints = row.Constraints;
```

### Method 3: Creating Actual Nodes with Labels

```cypher
// Example: Create Organization nodes
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
WHERE row.Category = 'Organization'
CALL apoc.create.node([row.Label], {
    name: row.Label,
    description: row.Description
}) YIELD node
RETURN node;
```

### Method 4: Using neo4j-admin import (Bulk Import)

For large-scale import, prepare header files:

**nodes-header.csv**:
```
labelId:ID,label:LABEL,parent,description,type,category
```

**nodes-data.csv**:
```
org-001,Organization,,Entities involved in the SR8 project,TopLevel,Organization
art-001,Artifact,,Engineering artifacts documents and knowledge items,TopLevel,Artifact
...
```

Then run:
```bash
neo4j-admin import \
  --nodes=nodes-header.csv,nodes-data.csv \
  --database=sr8-ontology
```

---

## Creating Sample Data

After importing the schema, populate with instances:

```cypher
// Create Sunswift Racing organization
CREATE (org:SunswiftRacing {
    hasID: "ORG-001",
    hasName: "Sunswift Racing",
    numberOfMembers: 80,
    numberOfDepartments: 16,
    numberOfProjects: 189
});

// Create SR8 vehicle
CREATE (sr8:SR8 {
    hasID: "VEH-SR8",
    hasName: "Sunswift 8",
    hasDescription: "World's first road-legal, student-built, tri-brid electric vehicle",
    isRoadLegal: true,
    numberOfComponents: 100000
});

// Create relationship
MATCH (o:SunswiftRacing {hasID: "ORG-001"})
MATCH (v:SR8 {hasID: "VEH-SR8"})
CREATE (o)-[:develops]->(v);
```

---

## Validation Queries

### Check imported schema

```cypher
// Count node labels by category
MATCH (n:SchemaLabel)
RETURN n.category, count(*) as count
ORDER BY count DESC;

// List all relationships
MATCH (r:SchemaRelationship)
RETURN r.name, r.sourceLabel, r.targetLabel;

// Find hierarchical depth
MATCH path = (n:SchemaLabel)-[:hasParent*]->(root:SchemaLabel)
WHERE NOT (root)-[:hasParent]->()
RETURN n.name, length(path) as depth
ORDER BY depth DESC;
```

### Verify constraints

```cypher
// Show all indexes
SHOW INDEXES;

// Show all constraints
SHOW CONSTRAINTS;
```

---

## Usage Examples

### Query 1: Find all subclasses of a category
```cypher
MATCH (n:SchemaLabel)
WHERE n.category = 'Agent'
RETURN n.name, n.description;
```

### Query 2: Get relationship hierarchy
```cypher
MATCH (r:SchemaRelationship)
WHERE r.sourceLabel = 'Requirement'
RETURN r.name, r.targetLabel;
```

### Query 3: Find properties for a label
```cypher
MATCH (p:SchemaProperty)
WHERE p.applicableLabels CONTAINS 'Requirement' OR p.applicableLabels = 'All'
RETURN p.name, p.dataType, p.description;
```

---

## Integration with Python

```python
from neo4j import GraphDatabase
import pandas as pd

class OntologyImporter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def import_labels(self, csv_file):
        df = pd.read_csv(csv_file)
        with self.driver.session() as session:
            for _, row in df.iterrows():
                session.run("""
                    MERGE (n:SchemaLabel {name: $label})
                    SET n.parent = $parent,
                        n.description = $description,
                        n.type = $type,
                        n.category = $category
                """, label=row['Label'], 
                     parent=row['ParentLabel'],
                     description=row['Description'],
                     type=row['Type'],
                     category=row['Category'])
    
    def close(self):
        self.driver.close()

# Usage
importer = OntologyImporter("bolt://localhost:7687", "neo4j", "password")
importer.import_labels("neo4j-node-labels.csv")
importer.close()
```

---

## File Locations

Default Neo4j import directory:
- **macOS**: `~/Library/Application Support/Neo4j Desktop/Application/relate-data/dbmss/dbms-xxx/import/`
- **Linux**: `/var/lib/neo4j/import/`
- **Windows**: `C:\Users\<username>\.Neo4jDesktop\relate-data\dbmss\dbms-xxx\import\`

Copy CSV files to this directory before running LOAD CSV commands.

---

## Next Steps

1. ✅ Import schema CSVs into Neo4j
2. ✅ Create constraints and indexes
3. ✅ Populate with SR8 project data
4. ✅ Link with existing ontology (project-ontology.owl)
5. ✅ Run validation queries
6. ✅ Export visualizations for thesis

---

## References

- **Neo4j Import Documentation**: https://neo4j.com/docs/operations-manual/current/tools/neo4j-admin/neo4j-admin-import/
- **Cypher Manual**: https://neo4j.com/docs/cypher-manual/current/
- **APOC Procedures**: https://neo4j.com/labs/apoc/

---

*These CSV files provide a complete mapping of the SR8 ontology to Neo4j's property graph model, enabling efficient import and querying of the knowledge graph.*
