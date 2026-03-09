# SR8 Thesis Ontology Visual Diagrams

## 1. Complete Top-Level Class Hierarchy

```mermaid
graph TD
    Root[Ontology Root]
    
    Root --> Org[Organization]
    Root --> Art[Artifact]
    Root --> Proc[Process]
    
    style Root fill:#e1f5ff
    style Org fill:#ffe1e1
    style Art fill:#e1ffe1
    style Proc fill:#fff0e1
```

## 2. Organization Hierarchy

```mermaid
graph TD
    Org[Organization]
    Org --> SR[SunswiftRacing<br/>80 members, 16 depts]
    Org --> Dept[Department]
    Org --> Ind[IndustryPartner]
    Org --> Acad[AcademicPartner]
    
    Dept --> Tech[TechnicalDepartment]
    Dept --> Ops[OperationalDepartment]
    
    Ind --> Neo[Neo4j]
    
    style SR fill:#ffcccc
    style Neo fill:#ccffcc
```

## 3. Artifact Hierarchy (Detailed)

```mermaid
graph TD
    Art[Artifact]
    
    Art --> Veh[Vehicle]
    Art --> Doc[Document]
    Art --> Req[Requirement<br/>600,000+]
    Art --> Comp[Component<br/>100,000+]
    
    Veh --> SR8[SR8<br/>Tri-brid Electric<br/>Road Legal]
    Veh --> Sub[Subsystem]
    Veh --> Int[Interface<br/>5,000+]
    Veh --> Proj[Project<br/>189]
    
    Doc --> Reg[RegulatoryDocument]
    Doc --> Eng[EngineeringBrief]
    
    Reg --> ADR[AustralianDesignRule<br/>113 rules]
    
    Eng --> Spec[TechnicalSpecification]
    Eng --> Report[TestReport]
    Eng --> Note[DesignNote]
    Eng --> Sim[SimulationOutput<br/>1.5TB]
    Eng --> Draw[EngineeringDrawing<br/>1TB]
    
    Req --> IntR[InternalRequirement]
    Req --> ExtR[ExternalRequirement]
    Req --> VP[VerificationProcedure]
    
    IntR --> IntEss[InternalEssentialRequirement]
    IntR --> IntRec[InternalRecommendedRequirement]
    
    ExtR --> ExtEss[ExternalEssentialRequirement]
    ExtR --> ExtRec[ExternalRecommendedRequirement]
    
    IntEss --> Clause1[Clause]
    IntRec --> Clause2[Clause]
    ExtEss --> Clause3[Clause]
    ExtRec --> Clause4[Clause]
    
    VP --> VM[VerificationMethod]
    VM --> Insp[Inspection]
    VM --> Demo[Demonstration]
    VM --> Test[Test]
    VM --> Anal[Analysis]
    VM --> ADRAnn[ADRAnnex]
    VM --> ADRTest[ADRTestingProcedure]
    
    Comp --> Evid[Evidence]
    Evid --> InspEvid[InspectionEvidence]
    Evid --> DemoEvid[DemonstrationEvidence]
    Evid --> TestEvid[TestEvidence]
    Evid --> AnalEvid[AnalysisEvidence]
    Evid --> ADRAnnEvid[ADRAnnexEvidence]
    Evid --> ADRTestEvid[ADRTestingProcedureEvidence]
    
    style SR8 fill:#ffcc99
    style ADR fill:#ff9999
    style Req fill:#99ccff
    style Ess fill:#ff6666
    style Rec fill:#66ff66
```

## 4. Key Relationships (Object Properties)

```mermaid
graph LR
    A1[Organization] -->|hasDepartment| B1[Department]
    A1 -->|collaboratesWith| A1
    
    A2[Vehicle] -->|hasSubsystem| B2[Subsystem]
    B2 -->|hasComponent| C2[Component]
    B2 -->|interfacesWith| B2
    
    A3[Requirement] -->|dependsOn| A3
    A3 -->|appliesTo| B3[Artifact]
    A3 -->|derivedFrom| C3[ADR]
    
    A4[Process] -->|hasInput| B4[Artifact]
    A4 -->|hasOutput| B4
    
    style A1 fill:#ffe1e1
    style A2 fill:#e1ffe1
    style A3 fill:#e1e1ff
    style A4 fill:#fff0e1
```

## 5. Three-System Architecture

```mermaid
graph TB
    subgraph PTS[Project Tracking System]
        P[Project<br/>189 projects]
        D[Department<br/>15 departments]
        M[Member<br/>100 members]
        
        P -.projectID.-> P
        P -.projectName.-> P
        P -.projectDescription.-> P
        
        P -->|hasPrimaryDepartment| D
        P -->|hasSecondaryDepartment| D
        P -->|hasAssignee| M
        M -->|belongsToDepartment| D
    end
    
    subgraph PMS[Parts Management System]
        C[Component<br/>100,000+ parts]
        
        C -.partNumber.-> C
        C -.partDescription.-> C
        C -.componentProjectName.-> C
        C -.clause.-> C
        C -.bomLevel.-> C
        C -.supplier.-> C
        C -.stockLocation.-> C
        
        C -->|usedInProject| P
        C -->|belongsToDepartment| D
    end
    
    subgraph AMS[ADR Management System]
        A[AustralianDesignRule<br/>100 ADRs]
        V[VerificationProcedure]
        
        A -.hasID.-> A
        A -.hasClause.-> A
        A -.requirementDescription.-> A
        A -.testingProcedurePerRequirement.-> A
        
        A -->|hasRelevantProject| P
        A -->|hasPrimaryDepartment| D
        A -->|hasSecondaryDepartment| D
        A -->|hasVerificationMethod| V
        A -->|appliesTo| C
    end
    
    style PTS fill:#e1f0ff
    style PMS fill:#ffe1f0
    style AMS fill:#f0ffe1
    style P fill:#99ccff
    style D fill:#ff99cc
    style M fill:#ccff99
    style C fill:#ffcc99
    style A fill:#99ffcc
```

## 6. Complete Workflow Architecture

```mermaid
graph TB
    subgraph Sources[Data Sources]
        ADR[Australian Design Rules<br/>113 documents]
        Specs[Technical Specs<br/>4TB documents]
        Sims[Simulations<br/>1.5TB]
        Draws[Drawings<br/>1TB]
        Code[Code<br/>500GB]
    end
    
    subgraph Extraction[Extraction Pipeline]
        Parse[Document Parsing<br/>PDFMiner, Tesseract]
        NLP[NLP Processing<br/>SpaCy, NLTK]
        Entity[Entity Recognition<br/>BERT, RoBERTa]
        Relation[Relation Extraction]
        Onto[Ontology Mapping<br/>OWL/RDF]
    end
    
    subgraph Storage[Knowledge Storage]
        KG[Knowledge Graph<br/>Neo4j]
        Schema[Ontology Schema<br/>Protégé]
    end
    
    subgraph Output[Engineering Support]
        Comply[Compliance<br/>Verification]
        RiskP[Risk<br/>Propagation]
        Rec[Design<br/>Recommendations]
        Trace[Traceability<br/>Analysis]
    end
    
    ADR --> Parse
    Specs --> Parse
    Sims --> Parse
    Draws --> Parse
    Code --> Parse
    
    Parse --> NLP
    NLP --> Entity
    Entity --> Relation
    Relation --> Onto
    
    Onto --> KG
    Onto --> Schema
    
    KG --> Comply
    KG --> RiskP
    KG --> Rec
    KG --> Trace
    
    style Sources fill:#ffe1e1
    style Extraction fill:#e1ffe1
    style Storage fill:#e1e1ff
    style Output fill:#e1f5ff
```

## 7. Requirement Classification System

```mermaid
graph TD
    Req[Requirement<br/>600,000+]
    
    Req --> Type{Classification}
    
    Type --> |Criticality| Ess[Essential<br/>Non-negotiable<br/>constraints]
    Type --> |Criticality| Rec[Recommended<br/>Contextual<br/>flexibility]
    
    Type --> |Source| Int[Internal<br/>Team-defined]
    Type --> |Source| Ext[External<br/>ADR-derived]
    
    Req --> Attr{Attributes}
    Attr --> Conf[Confidence Score<br/>0.0 - 1.0]
    Attr --> Risk[Risk Level<br/>Low/Med/High]
    Attr --> Cond[Conditional<br/>True/False]
    Attr --> Prov[Provenance<br/>Source tracking]
    
    Req --> Rel{Relationships}
    Rel --> Dep[dependsOn<br/>Transitive]
    Rel --> App[appliesTo<br/>Components]
    Rel --> Der[derivedFrom<br/>ADR rules]
    
    style Ess fill:#ff6666
    style Rec fill:#66ff66
    style Int fill:#6666ff
    style Ext fill:#ff9966
```

## 8. SR8 Systems Architecture

```mermaid
graph TD
    SR8[Sunswift 8<br/>Tri-brid Electric Vehicle]
    
    SR8 --> SS1[Powertrain<br/>Subsystem]
    SR8 --> SS2[Battery<br/>Subsystem]
    SR8 --> SS3[Solar Array<br/>Subsystem]
    SR8 --> SS4[Chassis<br/>Subsystem]
    SR8 --> SS5[Safety Systems<br/>Subsystem]
    SR8 --> SS6[Electronics<br/>Subsystem]
    
    SS1 -.interfacesWith.- SS2
    SS2 -.interfacesWith.- SS3
    SS2 -.interfacesWith.- SS6
    SS4 -.interfacesWith.- SS5
    SS5 -.interfacesWith.- SS6
    SS1 -.interfacesWith.- SS6
    
    SS1 --> C1[Motor<br/>Controller]
    SS1 --> C2[Electric<br/>Motor]
    
    SS2 --> C3[Battery<br/>Pack]
    SS2 --> C4[BMS]
    
    SS5 --> C5[ECU]
    SS5 --> C6[Sensors]
    
    ADR[Australian<br/>Design Rules] -.derivedFrom.-> R1[Safety<br/>Requirements]
    ADR -.derivedFrom.-> R2[Performance<br/>Requirements]
    ADR -.derivedFrom.-> R3[Emission<br/>Requirements]
    
    R1 -.appliesTo.-> SS5
    R2 -.appliesTo.-> SS1
    R3 -.appliesTo.-> SS2
    
    style SR8 fill:#ffcc99
    style ADR fill:#ff9999
```

## 9. Data Properties Overview

```mermaid
graph LR
    subgraph Identifiers
        ID[hasID]
        Name[hasName]
        Desc[hasDescription]
        Time[hasTimestamp]
    end
    
    subgraph Provenance
        Source[hasSource]
        Prov[hasProvenance]
        Conf[hasConfidenceScore]
    end
    
    subgraph Requirements
        Ess[isEssential]
        Cond[isConditional]
        Risk[hasRiskLevel]
        Exempt[hasExemption]
    end
    
    subgraph Metrics
        Members[numberOfMembers]
        Depts[numberOfDepartments]
        Projs[numberOfProjects]
        Comps[numberOfComponents]
        Reqs[numberOfRequirements]
        Legal[isRoadLegal]
    end
    
    style Identifiers fill:#e1f5ff
    style Provenance fill:#ffe1f0
    style Requirements fill:#fff0e1
    style Metrics fill:#e1ffe1
```

## 10. Ontology Usage in Neo4j

```cypher
// Example: Create SR8 vehicle node
CREATE (sr8:SR8 {
    hasID: "SR8-001",
    hasName: "Sunswift 8",
    hasDescription: "World's first road-legal student-built tri-brid electric vehicle",
    isRoadLegal: true,
    numberOfComponents: 100000,
    numberOfRequirements: 600000
})

// Example: Create ADR and requirement relationship
CREATE (adr:AustralianDesignRule {hasID: "ADR-42", hasName: "General Safety"})
CREATE (req:EssentialRequirement {
    hasID: "REQ-42-001",
    hasDescription: "Crash worthiness standards",
    isEssential: true,
    hasConfidenceScore: 0.95,
    hasRiskLevel: "High"
})
CREATE (req)-[:derivedFrom]->(adr)
CREATE (req)-[:appliesTo]->(sr8)
```

## 11. Semantic Integration

```mermaid
graph TB
    subgraph Symbolic[Symbolic Reasoning]
        OWL[OWL Ontology<br/>Formal Logic]
        Rules[Inference Rules<br/>SWRL]
        Reason[Reasoner<br/>HermiT/Pellet]
    end
    
    subgraph Neural[Neural Reasoning]
        LLM[Large Language<br/>Models]
        Embed[Graph<br/>Embeddings]
        RL[Reinforcement<br/>Learning]
    end
    
    subgraph Integration[Neuro-Symbolic Integration]
        MCP[Model Context<br/>Protocol]
        RAG[Retrieval-Augmented<br/>Generation]
        Val[Validation<br/>Layer]
    end
    
    OWL --> MCP
    Rules --> MCP
    
    LLM --> MCP
    Embed --> MCP
    RL --> MCP
    
    MCP --> RAG
    MCP --> Val
    
    Val --> KG[Enriched<br/>Knowledge Graph]
    
    style OWL fill:#9999ff
    style LLM fill:#ff99ff
    style MCP fill:#ffff99
    style KG fill:#99ff99
```

---

*These diagrams provide a comprehensive visual representation of the SR8 thesis ontology, showing the hierarchical structure, relationships, workflows, and integration points across the entire knowledge framework.*
