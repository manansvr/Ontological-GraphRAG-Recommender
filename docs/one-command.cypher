// run in one command:
// cypher-shell -a bolt://localhost:7687 -u neo4j -p password123 -f docs/one-command.cypher
// note: cypher-shell does not render a visual graph. to see graph visuals, run the final query in neo4j browser.

MATCH (n) DETACH DELETE n;

LOAD CSV WITH HEADERS FROM 'file:///node-labels.csv' AS row
MERGE (n:SchemaLabel {name: row.Label})
SET n.parent = CASE WHEN row.ParentLabel = '' THEN null ELSE row.ParentLabel END,
    n.description = row.Description,
    n.type = row.Type,
    n.category = row.Category;

MATCH (child:SchemaLabel)
WHERE child.parent IS NOT NULL
MATCH (parent:SchemaLabel {name: child.parent})
MERGE (child)-[:SUBCLASS_OF]->(parent);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
MERGE (r:SchemaRelationship {name: row.RelationshipType})
SET r.sourceLabel = row.SourceLabel,
    r.targetLabel = row.TargetLabel,
    r.description = row.Description,
    r.properties = row.Properties;

LOAD CSV WITH HEADERS FROM 'file:///node-properties.csv' AS row
MERGE (p:SchemaProperty {name: row.PropertyName})
SET p.applicableLabels = row.ApplicableLabels,
    p.dataType = row.DataType,
    p.description = row.Description,
    p.constraints = row.Constraints;

MATCH ()-[e:SOURCE_OF|TARGET_OF|SCHEMA_REL]->() DELETE e;
MATCH (scope:SchemaScope {name: 'All'}) DETACH DELETE scope;

MATCH (r:SchemaRelationship)
OPTIONAL MATCH (sLabel:SchemaLabel {name: r.sourceLabel})
OPTIONAL MATCH (tLabel:SchemaLabel {name: r.targetLabel})
WITH r, sLabel AS src, tLabel AS tgt
WHERE src IS NOT NULL AND tgt IS NOT NULL
MERGE (src)-[e:SCHEMA_REL {name: r.name}]->(tgt)
SET e.name = r.name,
    e.description = r.description,
    e.connector = r.description,
    e.properties = r.properties;

MATCH (n:SchemaLabel) RETURN count(n) AS labels;
MATCH (r:SchemaRelationship) RETURN count(r) AS relationshipNodes;
MATCH (p:SchemaProperty) RETURN count(p) AS properties;
MATCH ()-[x:SUBCLASS_OF]->() RETURN count(x) AS hierarchyRels;
MATCH ()-[x:SCHEMA_REL]->() RETURN count(x) AS schemaRels;
MATCH (r:SchemaRelationship)
OPTIONAL MATCH ()-[x:SCHEMA_REL {name: r.name}]->()
WITH r, count(x) AS edgeCount
WHERE edgeCount = 0
RETURN count(r) AS missingSchemaRelEdge;

// browser-only graph view (run this query by itself in neo4j browser)
// if browser shows table/text, switch result view to graph.
MATCH (s)-[r:SCHEMA_REL]->(t)
RETURN s, r, t
LIMIT 500;

// neo4j browser style (copy/paste these in browser)
// :style
//
// relationship.SCHEMA_REL {
//   caption: "{connector}";
// }
