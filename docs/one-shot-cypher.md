# SR8 neo4j One-Shot Cypher

Run these blocks in order in Neo4j Browser.

## 0) Optional Reset (Clean Run)

```cypher
MATCH (n) DETACH DELETE n;
```

## 1) Import Labels

```cypher
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-labels.csv' AS row
MERGE (n:SchemaLabel {name: row.Label})
SET n.parent = CASE WHEN row.ParentLabel = '' THEN null ELSE row.ParentLabel END,
    n.description = row.Description,
    n.type = row.Type,
    n.category = row.Category;
```

## 2) Create Label Hierarchy

```cypher
MATCH (child:SchemaLabel)
WHERE child.parent IS NOT NULL
MATCH (parent:SchemaLabel {name: child.parent})
MERGE (child)-[:SUBCLASS_OF]->(parent);
```

## 3) Import Relationship Definitions

```cypher
LOAD CSV WITH HEADERS FROM 'file:///neo4j-relationships.csv' AS row
MERGE (r:SchemaRelationship {name: row.RelationshipType})
SET r.sourceLabel = row.SourceLabel,
    r.targetLabel = row.TargetLabel,
    r.description = row.Description,
    r.properties = row.Properties;
```

## 4) Import Property Definitions

```cypher
LOAD CSV WITH HEADERS FROM 'file:///neo4j-node-properties.csv' AS row
MERGE (p:SchemaProperty {name: row.PropertyName})
SET p.applicableLabels = row.ApplicableLabels,
    p.dataType = row.DataType,
    p.description = row.Description,
    p.constraints = row.Constraints;
```

## 5) Materialize Named Edges From Relationship Nodes

```cypher
MATCH (r:SchemaRelationship)
MATCH (s:SchemaLabel {name: r.sourceLabel})
MATCH (t:SchemaLabel {name: r.targetLabel})
MERGE (s)-[e:SCHEMA_REL {name: r.name}]->(t)
SET e.description = r.description,
    e.properties = r.properties;
```

## 6) Quick Counts

```cypher
MATCH (n:SchemaLabel) RETURN count(n) AS labels;
MATCH (r:SchemaRelationship) RETURN count(r) AS relationshipNodes;
MATCH (p:SchemaProperty) RETURN count(p) AS properties;
MATCH ()-[x:SUBCLASS_OF]->() RETURN count(x) AS hierarchyRels;
MATCH ()-[x:SCHEMA_REL]->() RETURN count(x) AS schemaRels;
```

## 7) View Graph (Named Connections)

```cypher
MATCH p=(s:SchemaLabel)-[r:SCHEMA_REL]->(t:SchemaLabel)
RETURN p
LIMIT 1000;
```

## 8) Optional Full Graph View

```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN DISTINCT n, r, m
LIMIT 2000;
```

## 9) Browser Style So Connection Text Shows Relationship Name

In neo4j Browser, run:

```cypher
:style
```

Then Add & Save:

```css
relationship.SCHEMA_REL {
  caption: "{name}";
}
```

## 10) Optional Re-Build of Materialized Edges

```cypher
MATCH ()-[e:SCHEMA_REL]->() DELETE e;
```