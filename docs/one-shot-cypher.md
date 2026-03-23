# SR8 neo4j One-Shot Cypher

run these blocks in order in neo4j Browser.

## -1) put csv files in neo4j import folder (required)

the browser `LOAD CSV` command can only read files from neo4j's import directory.

on homebrew neo4j (macos), run this in terminal from repo root:

```bash
cp csv/node-labels.csv /opt/homebrew/var/neo4j/import/
cp csv/relationships.csv /opt/homebrew/var/neo4j/import/
cp csv/node-properties.csv /opt/homebrew/var/neo4j/import/
```

then use these exact urls in cypher:
- `file:///node-labels.csv`
- `file:///relationships.csv`
- `file:///node-properties.csv`

## 0) Optional Reset (Clean Run)

```cypher
MATCH (n) DETACH DELETE n;
```

## 1) Import Labels

```cypher
LOAD CSV WITH HEADERS FROM 'file:///node-labels.csv' AS row
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
LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
MERGE (r:SchemaRelationship {name: row.RelationshipType})
SET r.sourceLabel = row.SourceLabel,
    r.targetLabel = row.TargetLabel,
    r.description = row.Description,
    r.properties = row.Properties;
```

## 4) Import Property Definitions

```cypher
LOAD CSV WITH HEADERS FROM 'file:///node-properties.csv' AS row
MERGE (p:SchemaProperty {name: row.PropertyName})
SET p.applicableLabels = row.ApplicableLabels,
    p.dataType = row.DataType,
    p.description = row.Description,
    p.constraints = row.Constraints;
```

## 5) Show Relationships As Vertices (Relationship Nodes)

```cypher
MATCH (r:SchemaRelationship)
FOREACH (_ IN CASE WHEN r.sourceLabel = 'All' THEN [1] ELSE [] END |
  MERGE (allSrc:SchemaScope {name: 'All'})
  MERGE (allSrc)-[:SOURCE_OF]->(r)
)
FOREACH (_ IN CASE WHEN r.sourceLabel <> 'All' THEN [1] ELSE [] END |
  MERGE (s:SchemaLabel {name: r.sourceLabel})
  MERGE (s)-[:SOURCE_OF]->(r)
)
FOREACH (_ IN CASE WHEN r.targetLabel = 'All' THEN [1] ELSE [] END |
  MERGE (allTgt:SchemaScope {name: 'All'})
  MERGE (r)-[:TARGET_OF]->(allTgt)
)
FOREACH (_ IN CASE WHEN r.targetLabel <> 'All' THEN [1] ELSE [] END |
  MERGE (t:SchemaLabel {name: r.targetLabel})
  MERGE (r)-[:TARGET_OF]->(t)
);
```

this renders each schema relationship as its own node in the graph.

## 5b) optional direct edges between labels (derived from relationship nodes)

run this if you also want direct label-to-label edges for quick traversal:

```cypher
MATCH ()-[e:SCHEMA_REL]->() DELETE e;

MATCH (r:SchemaRelationship)
MATCH (s:SchemaLabel {name: r.sourceLabel})
MATCH (t:SchemaLabel {name: r.targetLabel})
MERGE (s)-[e:SCHEMA_REL {name: r.name}]->(t)
SET e.description = r.description,
    e.properties = r.properties;
```

use this to confirm all direct connections have names:

```cypher
MATCH ()-[e:SCHEMA_REL]->()
RETURN count(e) AS total,
       count(CASE WHEN e.name IS NOT NULL AND trim(toString(e.name)) <> '' THEN 1 END) AS withName;
```

## 6) Quick Counts

```cypher
MATCH (n:SchemaLabel) RETURN count(n) AS labels;
MATCH (r:SchemaRelationship) RETURN count(r) AS relationshipNodes;
MATCH (p:SchemaProperty) RETURN count(p) AS properties;
MATCH ()-[x:SUBCLASS_OF]->() RETURN count(x) AS hierarchyRels;
MATCH ()-[x:SOURCE_OF]->() RETURN count(x) AS sourceLinks;
MATCH ()-[x:TARGET_OF]->() RETURN count(x) AS targetLinks;

// should both be 0 when complete
MATCH (r:SchemaRelationship)
WHERE NOT EXISTS { MATCH ()-[:SOURCE_OF]->(r) }
RETURN count(r) AS missingSourceLink;

MATCH (r:SchemaRelationship)
WHERE NOT EXISTS { MATCH (r)-[:TARGET_OF]->() }
RETURN count(r) AS missingTargetLink;
```

## 7) View Graph (Relationships As Vertices)

```cypher
MATCH p=(s)-[:SOURCE_OF]->(r:SchemaRelationship)-[:TARGET_OF]->(t)
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
node.SchemaRelationship {
  caption: "{name}";
}

relationship.SOURCE_OF {
  caption: "";
}

relationship.TARGET_OF {
  caption: "";
}
```

## 10) Optional Clean Re-Build Of Vertex Links

```cypher
MATCH ()-[e:SOURCE_OF|TARGET_OF]->() DELETE e;

MATCH (r:SchemaRelationship)
FOREACH (_ IN CASE WHEN r.sourceLabel = 'All' THEN [1] ELSE [] END |
  MERGE (allSrc:SchemaScope {name: 'All'})
  MERGE (allSrc)-[:SOURCE_OF]->(r)
)
FOREACH (_ IN CASE WHEN r.sourceLabel <> 'All' THEN [1] ELSE [] END |
  MERGE (s:SchemaLabel {name: r.sourceLabel})
  MERGE (s)-[:SOURCE_OF]->(r)
)
FOREACH (_ IN CASE WHEN r.targetLabel = 'All' THEN [1] ELSE [] END |
  MERGE (allTgt:SchemaScope {name: 'All'})
  MERGE (r)-[:TARGET_OF]->(allTgt)
)
FOREACH (_ IN CASE WHEN r.targetLabel <> 'All' THEN [1] ELSE [] END |
  MERGE (t:SchemaLabel {name: r.targetLabel})
  MERGE (r)-[:TARGET_OF]->(t)
);
```