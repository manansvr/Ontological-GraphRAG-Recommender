# SR8 Ontology Quick Reference Guide

## File Overview

Your ontology consists of three files:

1. **project-ontology.owl** - Machine-readable OWL/RDF format (formal specification)
2. **ontology-documentation.md** - Comprehensive documentation (human-readable)
3. **ontology-diagrams.md** - Visual diagrams (Mermaid format)
4. **ontology-quick-reference.md** - This quick guide

---

## 6 Main Pillars

```
1. ORGANIZATION  → Who is involved (Sunswift, departments, partners)
2. ARTIFACT      → What is created (vehicles, documents, requirements, components)
3. PROCESS       → How work is done (extraction, extension, validation)
4. TECHNOLOGY    → What tools are used (Neo4j, LLMs, NLP tools)
5. CONCEPT       → Theoretical foundations (ontology, systems engineering, AI)
6. AGENT         → Intelligent actors (LLM, link prediction, RL, validation)
```

---

## Most Important Classes (Top 20)

| Class | Description | Count/Scale |
|-------|-------------|-------------|
| `SR8` | The vehicle being built | 1 vehicle |
| `AustralianDesignRule` | Regulatory framework | 113 rules |
| `Requirement` | Engineering requirements | 600,000+ |
| `Component` | Vehicle parts | 100,000+ |
| `Subsystem` | Major vehicle systems | ~10-20 |
| `Interface` | Cross-system connections | 5,000+ |
| `Project` | Concurrent engineering projects | 189 |
| `Department` | Organizational units | 16 |
| `KnowledgeExtraction` | Raw data → structured data | Process |
| `KnowledgeExtension` | Enrichment via AI | Process |
| `KnowledgeGraph` | Semantic knowledge store | Neo4j-based |
| `Neo4j` | Graph database technology | Tool |
| `LLMAgent` | Language model reasoning | Multi-agent |
| `LinkPredictionAgent` | Pattern detection | Multi-agent |
| `RLAgent` | Prioritization learning | Multi-agent |
| `ModelContextProtocol` | Agent orchestration | Framework |
| `Ontology` | Formal knowledge model | This! |
| `RegulatoryCompliance` | ADR adherence | Concept |
| `Traceability` | Requirement tracking | Concept |
| `NeuroSymbolicAI` | Neural + symbolic fusion | Concept |

---

## Most Important Relationships (Top 15)

| Relationship | Direction | Example |
|--------------|-----------|---------|
| `hasSubsystem` | Vehicle → Subsystem | SR8 has Battery Subsystem |
| `hasComponent` | Subsystem → Component | Battery has BMS |
| `hasRequirement` | Artifact → Requirement | SR8 has safety requirements |
| `dependsOn` | Requirement → Requirement | Req A depends on Req B |
| `derivedFrom` | Requirement → ADR | Req derived from ADR-42 |
| `appliesTo` | Requirement → Artifact | Req applies to Battery |
| `interfacesWith` | Subsystem ↔ Subsystem | Battery interfaces with Motor |
| `compliesWith` | Artifact → ADR | SR8 complies with ADR-42 |
| `hasRisk` | Artifact → Requirement | Battery has thermal risk |
| `propagatesRiskTo` | Subsystem → Subsystem | Battery risk → Electronics |
| `extractsKnowledgeFrom` | Process → Document | Extract from ADR PDF |
| `extendsKnowledgeGraph` | Process → KG | Extension enriches KG |
| `storedIn` | KG → Database | KG stored in Neo4j |
| `orchestratedBy` | Agent → MCP | LLM agent orchestrated by MCP |
| `inferredBy` | Requirement → Agent | Req inferred by LLM agent |

---

## Key Metrics (SR8 Project Scale)

```
TEAM STRUCTURE
├── 80 members
├── 16 departments (technical + operational)
└── 189 concurrent projects

ENGINEERING COMPLEXITY
├── 100,000+ components
├── 600,000+ requirements (internal + external)
├── 5,000+ subsystem interfaces
└── 113 Australian Design Rules

DATA VOLUME
├── 4 TB documents, reports, spreadsheets
├── 1.5 TB mechanical simulations
├── 1 TB electrical drawings
└── 500 GB code (high-level + low-level)
```

---

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
KNOWLEDGE EXTENSION
    • LLM Agent → Linguistic inference
    • Link Prediction Agent → Pattern detection
    • RL Agent → Prioritization
    • Validation Agent → Consistency checking
    ↓
MCP ORCHESTRATION
    • Agent coordination
    • Context management
    • Transparency & traceability
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

### Scenario 3: Identifying Agent Inferences

**Question**: Which requirements were inferred by AI agents vs. extracted directly?

**Cypher Query**:
```cypher
MATCH (req:Requirement)-[:inferredBy]->(agent:Agent)
RETURN agent.hasName, COUNT(req) AS inferredCount
ORDER BY inferredCount DESC
```

### Scenario 4: Finding Cross-Department Interfaces

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

---

## Import Into Neo4j

### Step 1: Install Neo4j
```bash
# macOS
brew install neo4j

# Start Neo4j
neo4j start

# Open browser
open http://localhost:7474
```

### Step 2: Create Constraints
```cypher
// Unique IDs
CREATE CONSTRAINT req_id IF NOT EXISTS FOR (r:Requirement) REQUIRE r.hasID IS UNIQUE;
CREATE CONSTRAINT comp_id IF NOT EXISTS FOR (c:Component) REQUIRE c.hasID IS UNIQUE;
CREATE CONSTRAINT adr_id IF NOT EXISTS FOR (a:AustralianDesignRule) REQUIRE a.hasID IS UNIQUE;

// Indexes for performance
CREATE INDEX req_name IF NOT EXISTS FOR (r:Requirement) ON (r.hasName);
CREATE INDEX comp_name IF NOT EXISTS FOR (c:Component) ON (c.hasName);
```

### Step 3: Import Ontology Schema
```cypher
// Create node labels from ontology classes
CALL apoc.meta.load("file:///project-ontology.owl")
```

### Step 4: Verify Schema
```cypher
CALL db.schema.visualization()
```

---

## Open in Protégé

### Installation
```bash
# Download from https://protege.stanford.edu/
# OR via Homebrew
brew install --cask protege
```

### Open Ontology
1. Launch Protégé
2. File → Open → Select `project-ontology.owl`
3. Navigate tabs:
   - **Classes**: See hierarchy
   - **Object Properties**: See relationships
   - **Data Properties**: See attributes
   - **Individuals**: See instances

### Run Reasoner
1. Reasoner → HermiT
2. Reasoner → Start reasoner
3. View inferred class hierarchy
4. Check for inconsistencies

---

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

## Integration with Thesis

### Where to Reference

1. **Abstract** - "ontology-driven framework"
2. **Introduction** - Semantic representation approach
3. **Context** - Domain model formalization
4. **Literature Review** - Knowledge representation techniques
5. **Methodology Section 5.1** - Ontology formalization process
6. **Methodology Section 5.2** - Multi-agent integration via ontology
7. **Methodology Section 5.3** - Systems of systems modeling
8. **Appendix** - Include ontology diagrams

### Thesis Deliverables

- [ ] Reference ontology file in appendix
- [ ] Include class hierarchy diagram in methodology
- [ ] Show example Cypher queries for validation
- [ ] Demonstrate agent-ontology alignment
- [ ] Provide traceability examples using ontology
- [ ] Document provenance through ontology metadata

---

## Validation Checklist

- [ ] All 113 ADRs mapped to RegulatoryDocument class?
- [ ] All 600,000 requirements captured in Requirement hierarchy?
- [ ] All 100,000+ components represented?
- [ ] All 16 departments linked to SunswiftRacing?
- [ ] All 189 projects instantiated?
- [ ] All 5,000+ interfaces modeled?
- [ ] All 4 agents (LLM, LP, RL, Validation) defined?
- [ ] MCP orchestration relationships established?
- [ ] Provenance tracking implemented?
- [ ] Confidence scores for inferred knowledge?

---

## Common Issues & Solutions

### Issue 1: Ontology won't load in Protégé
**Solution**: Validate XML syntax, check namespace declarations

### Issue 2: Reasoner finds inconsistencies
**Solution**: Check disjoint classes, ensure proper subclass relationships

### Issue 3: Neo4j import fails
**Solution**: Use APOC plugin for OWL import or manually map schema

### Issue 4: Too many relationships (performance)
**Solution**: Create indexes on high-cardinality properties

### Issue 5: Agent inferences conflict with ontology
**Solution**: Strengthen validation agent rules, add consistency constraints

---

## Next Steps

1. **Validate**: Run HermiT reasoner in Protégé
2. **Import**: Load into Neo4j and create sample instances
3. **Populate**: Add SR8 project data (requirements, components, etc.)
4. **Test**: Run example queries to verify relationships
5. **Extend**: Add domain-specific classes and properties as needed
6. **Document**: Reference in thesis methodology section

---

## Support Resources

- **OWL Documentation**: https://www.w3.org/OWL/
- **Protégé Tutorial**: https://protege.stanford.edu/support.php
- **Neo4j Cypher**: https://neo4j.com/docs/cypher-manual/
- **Ontology Best Practices**: https://www.w3.org/TR/owl2-primer/

---

*This quick reference provides the essential information needed to understand, use, and extend the SR8 thesis ontology.*
