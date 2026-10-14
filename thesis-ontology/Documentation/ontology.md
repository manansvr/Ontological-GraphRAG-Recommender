# SR8 Thesis Ontology Documentation

This ontology formally represents the knowledge domain of the Sunswift Racing SR8 tri-brid electric vehicle project, integrating regulatory compliance, knowledge graph technologies, & AI-assisted reasoning.

**Version**: 1.0 (`owl:versionInfo` in `ontology.owl`)
**Created**: February 26, 2026
**Authors**: Manan Rathi, Ilina Sharma

**Ontology Statistics:**
- **Classes**: 72 (Node Labels)
- **Object Properties**: 59 (Relationships)
- **Data Properties**: 70 (Node Attributes)
- **Edge Properties**: 32 (properties stored on relationships; `edgeProperty` annotations)

`ontology.owl` is the single source of truth. The schema CSVs in `csv/` (`node-labels.csv`, `relationships.csv`, `node-properties.csv`, `relationship-properties.csv`) are generated from it with `python3 scripts/owl-to-csv.py`; `python3 scripts/validate.py` fails if they differ. Edit the OWL file, then regenerate.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Class Hierarchies](#class-hierarchies)
3. [Object Properties (Relationships)](#object-properties-relationships)
4. [Data Properties (Attributes)](#data-properties-attributes)
5. [Validation & Verification Framework](#validation--verification-framework)
6. [Visual Diagrams](#visual-diagrams)
7. [Neo4j Access](#neo4j-access)

---

## System Architecture

### Core Integration

The SR8 ontology integrates three main management systems:

```
┌─────────────────────────┐
│  Project Tracking (PTS) │
│  - 189 Projects         │
│  - 12 Technical Depts   │
│  - 100 Members          │
└───────┬─────────────────┘
        │
    │ departmentAssignedToProject
    │ assignedToSystem
    │ assignedToSubsystem
        │
┌───────▼─────────────────┐
│  Systems Engineering    │
│  - ProjectTrackingSystem > System     │
│  - System > Subsystem   │
│  - Requirement Flow     │
└───────┬─────────────────┘
    │ subsystemHasRequirement
    │ systemHasRequirement
    │ projectHasRequirement
    │
┌───────▼─────────────────┐         ┌──────────────────────┐
│  ADR Management         │◄────────┤  Parts Management    │
│  - 100 ADRs             │         │  - 100,000+ Parts    │
│  - Verification         │         │  - Assembly/Component│
│  - Extracted Req Links  │         │  - componentIn* links│
└─────────────────────────┘         └──────────────────────┘
    │                                      │
    │ hasExternalEssentialRequirement      │ componentInSubsystem
    │ assignedToProject (via requirement)  │ componentInSystem
    │ verifiedBy / supportedByEvidence     │ componentInProject
    └──────────────────────────────────────┘
```

### 1. Project Tracking System (PTS)

**Projects** (189 total) - Single nodes with properties:
- `projectID` - Unique project identifier
- `projectName` - Name of the project
- `projectDescription` - Description of the project

**Departments** (12 technical departments + operational units) - Organizational units:
- `TechnicalDepartment` - Technical departments
- `OperationalDepartment` - Operational departments
- Properties: `hasID`, `hasName`, `sectionName`

Technical departments:
- `ChassisAndBodywork`
- `Interior`
- `Powertrain`
- `VehicleDynamics`
- `EnergySystems`
- `EmbeddedSystems`
- `TechnicalSupportSystems`
- `IndustrialDesign`
- `WholeTeam`
- `RemoteDriving`
- `General`
- `AlternativeEnergies`

**Members** (100 total) - Project assignees:
- `hasID` - Members identifier
- `hasName` - Members name

**Relationships**:
- `hasPrimaryDepartment` → Department
- `hasSecondaryDepartment` → Department
- `hasAssignee` → Members
- `belongsToDepartment` → Department (for members)

### 2. Parts Management System

**Component** (100,000+ parts) - Engineering parts & assemblies with properties:

*Identification*
- `partNumber` - Unique part identifier
- `partDescription` - Component description
- `bomLevel` - BOM hierarchy level
- `onCarSoftwareOffCar` - Classification type

*Physical Properties*
- `quantityPer` - Quantity per assembly
- `estimatedWeight` - Estimated weight (kg)
- `actualWeight` - Actual weight (kg)

*Status*
- `approvalStatus` - Component approval status
- `componentStatus` - Current status

*Supply Chain*
- `procurementStatus` - Procurement status
- `supplier` - Supplier name
- `orderStatus` - Order status
- `stockQuantity` - Stock quantity
- `stockLocation` - Stock location

*Cost Tracking*
- `assemblyEstimatedCost` - Estimated cost
- `assemblyActualCost` - Actual cost

*ADR Integration*
- `relatedADRs` - Related ADR identifiers
- `engineeringDrawingRequired` - Engineering drawing flag (boolean)

**Relationships**:
- `usedInProject` → Project
- `belongsToDepartment` → Department
- `usedInADR` → AustralianDesignRule
- `generatesEvidence` → TestingEvidence
- `suppliedBy` → IndustryPartner
- `partOfBOM` → Component (BOM hierarchy)

### 3. ADR Management System

**AustralianDesignRule** (100 total) - Regulatory requirements with properties:

*Identification*
- `hasID` - ADR identifier (e.g., "ADR-042")
- `hasName` - ADR name
- `requirementName` - Requirement title
- `requirementText` - Full requirement text
- `requirementDescription` - Detailed description

*Verification*
- `verificationMethodDescription` - Verification details
- `testingProcedurePerRequirement` - Testing procedure
- `isVerified` - Verification status (boolean)
- `usesAlternativeTesting` - Alternative testing flag (boolean)
- `rightProjectAssigned` - Correct project flag (boolean)
- `alternativeProjectSuggestion` - Suggested alternative project

*Risk & Classification*
- `hasRiskLevel` - Risk categorization
- `hasExemption` - ADR exemption details
- `isEssential` - Essential vs recommended (boolean)
- `isConditional` - Conditional applicability (boolean)

**Related Nodes**:
- `Clause` - Specific clause reference (each clause is a new node connected to 1 ADR)

**Verification Methods** (6 types):
1. `Inspection` - Visual or manual inspection
2. `Demonstration` - Functional demonstration
3. `Test` - Physical or functional testing
4. `Analysis` - Simulations & calculations
5. `ADRAnnex` - ADR annex procedures
6. `ADRTestingProcedure` - Official ADR testing

**Evidence Types** (6 types, formed when components collectively pass testing procedures):
1. `InspectionEvidence` - Visual/manual inspection results
2. `DemonstrationEvidence` - Demonstration results
3. `TestEvidence` - Physical/functional testing results
4. `AnalysisEvidence` - Simulation/calculation results
5. `ADRAnnexEvidence` - ADR annex procedure results
6. `ADRTestingProcedureEvidence` - Official ADR testing results

**Relationships**:
- `hasClause` → Clause
- `assignedToProject` → Project (from `ExtractedEssentialRequirement`)
- `assignedToDepartment` → Department
- `hasRelevantProject` → Project
- `hasRelevantDepartment` → Department
- `hasVerificationProcedure` → VerificationProcedure
- `hasVerificationMethod` → VerificationMethod
- `supportedByEvidence` → TestingEvidence
- `verifiedBy` → TestingEvidence

### Key Metrics

| System | Entities | Key Features |
|--------|----------|--------------|
| Project Tracking | 189 Projects, 12 Technical Departments, 100 Members | Primary/secondary departments, member assignments |
| Parts Management | 100,000+ Components | BOM hierarchy, supply chain, cost tracking |
| ADR Management | 100 ADRs | 6 verification methods, evidence tracking |

These figures describe the source systems the ontology was designed for; they are not derived from data in this repository and have not been verified. The extracted graph currently holds 8 ADRs (`thesis-extraction/csv/`), 217 requirement nodes, 24 distinct projects referenced by them, and 15 FMEA components (see `thesis-extraction/Documentation/extraction.md`).

---

## Class Hierarchies

### 1. Organization Hierarchy

```
Organization
├── Department
│   ├── TechnicalDepartment
│   │   ├── ChassisAndBodywork
│   │   ├── Interior
│   │   ├── Powertrain
│   │   ├── VehicleDynamics
│   │   ├── EnergySystems
│   │   ├── EmbeddedSystems
│   │   ├── TechnicalSupportSystems
│   │   ├── IndustrialDesign
│   │   ├── WholeTeam
│   │   ├── General
│   │   ├── RemoteDriving
│   │   └── AlternativeEnergies
│   └── OperationalDepartment
├── IndustryPartner
└── AcademicPartner
```

**Key Relationships**:
- `hasDepartment` - Organization → Department
- `collaboratesWith` - Organization ↔ Organization (symmetric)
- `hasSection` - Department → Department (organizational hierarchy)

### 2. Engineering Hierarchy

```
ProjectTrackingSystem
├── System
│   └── Subsystem

Project

Document
│   ├── RegulatoryDocument
│   │   └── AustralianDesignRule (ADR)
│   │       ├── ExtractedEssentialRequirement
│   │       └── ExtractedRecommendedRequirement
│   ├── EngineeringBrief
│   ├── TestingDocuments
│   │   ├── TechnicalSpecification
│   │   ├── TestReport
│   │   ├── DesignNote
│   │   ├── SimulationOutput
│   │   └── EngineeringDrawing
│   ├── TestingEvidence
│   │   ├── InspectionEvidence
│   │   ├── DemonstrationEvidence
│   │   ├── TestEvidence
│   │   ├── AnalysisEvidence
│   │   ├── ADRAnnexEvidence
│   │   └── ADRTestingProcedureEvidence
│   ├── ConceptualDesign
│   ├── PreliminaryDesign
│   └── DetailedDesign

Requirement
│   ├── InternalRequirement
│   │   ├── InternalEssentialRequirement
│   │   └── InternalRecommendedRequirement
│   ├── ExtractedRequirement
│   │   ├── ExtractedEssentialRequirement
│   │   └── ExtractedRecommendedRequirement
│   ├── Clause
│   ├── ValidationScenario
│   │   └── AcceptanceCriterion
│   ├── ValidationResult
│   └── VerificationProcedure
│       └── VerificationMethod
│           ├── Inspection
│           ├── Demonstration
│           ├── Test
│           ├── Analysis
│           ├── ADRAnnex
│           └── ADRTestingProcedure

PartsManagement
├── Assembly
└── Component        (an Assembly is assembledFrom Components; a Component is not a kind of Assembly)

Classes written by the extractors and sr8-mcp
├── FailureMode, Cause, Effect, ControlAction   (FMEA workbook; top-level)
├── FeedbackEvent                               (a reviewer's decision on an inferred link; top-level)
└── Document
    └── ChangeImpactReport                      (written by write_change_impact_report)
```

---

## Object Properties (Relationships)

### Organizational Relationships
- `hasDepartment` - Organization → Department
- `collaboratesWith` - Organization ↔ Organization (symmetric)
- `hasSection` - Department → Department
- `assignedToSystem` - TechnicalDepartment → System
- `assignedToSubsystem` - TechnicalDepartment → Subsystem
- `departmentAssignedToProject` - TechnicalDepartment → Project

### Engineering Relationships
- `hasRequirement` - All → Requirement
- `subsystemHasRequirement` - Subsystem → Requirement
- `systemHasRequirement` - System → Requirement
- `projectHasRequirement` - Project → Requirement
- `validatesUseCase` - All → ValidationScenario
- `hasAcceptanceCriterion` - ValidationScenario → AcceptanceCriterion
- `validatedBy` - All → ValidationResult
- `validatesRequirement` - ValidationResult → Requirement
- `hasComponent` - Subsystem → Component (transitive)
- `componentInSubsystem` - Component → Subsystem
- `componentInSystem` - Component → System
- `componentInProject` - Component → Project
- `assembledFrom` - Assembly → Component
- `hasSubsystem` - System → Subsystem
- `interface` - (System|Subsystem) ↔ (System|Subsystem) (symmetric)
- `dependsOn` - Requirement → Requirement (transitive)
- `impactsOn` - Requirement → Requirement
- `appliesTo` - Requirement → All
- `derivedFrom` - Requirement → AustralianDesignRule
- `documentedIn` - All → Document

### ADR Verification Relationships
- `assignedToProject` - ExtractedEssentialRequirement → Project
- `assignedToDepartment` - AustralianDesignRule → Department
- `hasRelevantProject` - AustralianDesignRule → Project
- `hasRelevantDepartment` - AustralianDesignRule → Department
- `hasVerificationProcedure` - AustralianDesignRule → VerificationProcedure
- `hasVerificationMethod` - VerificationProcedure → VerificationMethod
- `supportedByEvidence` - VerificationProcedure → TestingEvidence
- `verifiedBy` - AustralianDesignRule → TestingEvidence
- `hasClause` - AustralianDesignRule → Clause
- `hasExternalEssentialRequirement` - AustralianDesignRule → ExtractedEssentialRequirement
- `hasExternalRecommendedRequirement` - AustralianDesignRule → ExtractedRecommendedRequirement

### Component Management Relationships
- `usedInProject` - Component → Project
- `usedInADR` - Component → AustralianDesignRule
- `generatesEvidence` - Component → TestingEvidence
- `suppliedBy` - Component → IndustryPartner
- `partOfBOM` - Component → Component (BOM hierarchy)
- `belongsToDepartment` - Component → Department

### Project Tracking Relationships
- `hasPrimaryDepartment` - Project → Department
- `hasSecondaryDepartment` - Project → Department
- `hasAssignee` - Project → Members

### Compliance & Risk Relationships
- `compliesWith` - All → AustralianDesignRule
- `hasRisk` - All → Requirement
- `propagatesRiskTo` - Subsystem → Subsystem

### Relationships Written By The Extractors And sr8-mcp
- `hasFailureMode` - Component → FailureMode; `causedBy` - FailureMode → Cause; `causes` - FailureMode → Effect; `mitigatedBy` - FailureMode → ControlAction; `satisfiesRequirement` - Component → Requirement (FMEA)
- `suggestedProject` - ExtractedEssentialRequirement → Project (machine inference, pending review)
- `belongsToAssembly` - Project → Assembly
- `recordedFor` - FeedbackEvent → ExtractedEssentialRequirement | Project
- `affectsRequirement` - ChangeImpactReport → Requirement; `affectsProject` - ChangeImpactReport → Project

Properties stored on relationships (`suggestedProject`, `assignedToProject`, `satisfiesRequirement`) are listed in `csv/relationship-properties.csv`.

### Property Characteristics
- **Symmetric**: `interface`, `collaboratesWith`
- **Transitive**: `dependsOn`, `hasComponent`, `partOfBOM`

All five are declared in `ontology.owl` (`owl:SymmetricProperty` / `owl:TransitiveProperty`). They are documentation only: no query relies on them.

---

## Validation & Verification Framework

### Distinction
- **Verification** answers: Are we building the system right?
- **Validation** answers: Are we building the right system for intended use?

### Validation Flow

```mermaid
graph LR
    P[Project/System/Subsystem]
    VS[ValidationScenario]
    AC[AcceptanceCriterion]
    VR[ValidationResult]
    R[Requirement]

    P -->|validatesUseCase| VS
    VS -->|hasAcceptanceCriterion| AC
    P -->|validatedBy| VR
    VR -->|validatesRequirement| R

    style VS fill:#fff4cc
    style VR fill:#e6f7ff
    style R fill:#f2e6ff
```

### Verification Flow

```mermaid
graph LR
    ADR[AustralianDesignRule]
    VP[VerificationProcedure]
    VM[VerificationMethod]
    TE[TestingEvidence]

    ADR -->|hasVerificationProcedure| VP
    VP -->|hasVerificationMethod| VM
    VP -->|supportedByEvidence| TE
    ADR -->|verifiedBy| TE

    style ADR fill:#ffdddd
    style TE fill:#e6f7ff
```

---

## Data Properties (Attributes)

### Identifiers & Metadata
- `hasID` (string) - Unique identifier
- `hasName` (string) - Entity name
- `hasDescription` (string) - Detailed description
- `hasTimestamp` (dateTime) - Temporal metadata (FeedbackEvent nodes store it)

### Provenance & Confidence
- `hasProvenance` (string) - Origin & history
- `hasConfidenceScore` (float, 0-1) - Extraction confidence

### Requirement Attributes
- `isEssential` (boolean) - Essential vs recommended
- `isConditional` (boolean) - Conditional applicability
- `hasRiskLevel` (string) - Risk categorization (Low/Medium/High/Critical)
- `hasExemption` (string) - ADR exemption details

### ADR Tracking Attributes
- `requirementName` (string) - Requirement title
- `requirementText` (string) - Full requirement text
- `requirementDescription` (string) - Detailed description
- `isVerified` (boolean) - Verification status
- `usesAlternativeTesting` (boolean) - Alternative testing flag
- `verificationMethodDescription` (string) - Verification details
- `testingProcedurePerRequirement` (string) - Testing procedure
- `rightProjectAssigned` (boolean) - Correct project flag
- `alternativeProjectSuggestion` (string) - Suggested alternative project

### Component Management Attributes

*Identification*
- `partNumber` (string) - Unique part identifier
- `partDescription` (string) - Component description
- `bomLevel` (integer) - BOM hierarchy level
- `approvalStatus` (string) - Approval status
- `componentStatus` (string) - Current status
- `onCarSoftwareOffCar` (string) - Classification type

*Physical Properties*
- `quantityPer` (integer) - Quantity per assembly
- `estimatedWeight` (float) - Estimated weight (kg)
- `actualWeight` (float) - Actual weight (kg)

*Supply Chain*
- `procurementStatus` (string) - Procurement status
- `supplier` (string) - Supplier name
- `orderStatus` (string) - Order status
- `stockQuantity` (integer) - Stock quantity
- `stockLocation` (string) - Stock location

*Cost & Engineering*
- `assemblyEstimatedCost` (float) - Estimated cost
- `assemblyActualCost` (float) - Actual cost
- `relatedADRs` (string) - Related ADR identifiers
- `engineeringDrawingRequired` (boolean) - Engineering drawing flag

*Project Properties*
- `projectID` (string) - Project identifier
- `projectName` (string) - Project name
- `projectDescription` (string) - Project description

*Department Properties*
- `sectionName` (string) - Department section name

### Quantitative Metrics
- `numberOfMembers` (integer) - Team size
- `numberOfDepartments` (integer) - Organizational units
- `numberOfProjects` (integer) - Concurrent projects
- `numberOfComponents` (integer) - Component count
- `numberOfRequirements` (integer) - Requirement count
- `isRoadLegal` (boolean) - Legal status

### Axioms & Constraints

**Disjoint Classes** (`owl:disjointWith` in `ontology.owl`):
- `InternalEssentialRequirement` ⊥ `InternalRecommendedRequirement`
- `ExtractedEssentialRequirement` ⊥ `ExtractedRecommendedRequirement`
- `InternalRequirement` ⊥ `ExtractedRequirement`

Like the property characteristics, these are not enforced in Neo4j: `import.py` loads only the class hierarchy, relationships and properties.

---

## Visual Diagrams

### Complete Workflow Architecture

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
        NLP[NLP Pipeline<br/>SpaCy, NLTK]
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

### Engineering Systems Architecture

```mermaid
graph TD
    ORG[Organization]
    TD[TechnicalDepartment]
    PROJ[Project]

    VEH[ProjectTrackingSystem]
    SYS[System]
    SS[Subsystem]

    PM[PartsManagement]
    ASM[Assembly]
    COMP[Component]

    ADR[AustralianDesignRule]
    EER[ExtractedEssentialRequirement]
    ERR[ExtractedRecommendedRequirement]
    REQ[Requirement]
    VP[VerificationProcedure]
    VM[VerificationMethod]
    TEV[TestingEvidence]

    DOC[Document]
    TDOC[TestingDocuments]

    ORG --> TD
    TD -.departmentAssignedToProject.-> PROJ
    TD -.assignedToSystem.-> SYS
    TD -.assignedToSubsystem.-> SS

    VEH --> SYS
    SYS -.hasSubsystem.-> SS
    SYS -.interface.-> SS
    SS -.interface.-> SS
    SYS -.interface.-> SYS

    PM --> ASM
    ASM --> COMP
    ASM -.assembledFrom.-> COMP

    COMP -.componentInSubsystem.-> SS
    COMP -.componentInSystem.-> SYS
    COMP -.componentInProject.-> PROJ

    SS -.subsystemHasRequirement.-> REQ
    SYS -.systemHasRequirement.-> REQ
    PROJ -.projectHasRequirement.-> REQ

    ADR -.hasExternalEssentialRequirement.-> EER
    ADR -.hasExternalRecommendedRequirement.-> ERR
    EER -.assignedToProject.-> PROJ
    ADR -.hasVerificationProcedure.-> VP
    VP -.hasVerificationMethod.-> VM
    VP -.supportedByEvidence.-> TEV
    ADR -.verifiedBy.-> TEV
    COMP -.generatesEvidence.-> TEV

    DOC --> TDOC
    DOC --> TEV

    style VEH fill:#ffcc99
    style ADR fill:#ff9999
    style PM fill:#e1f5ff
    style DOC fill:#e1ffe1
    style TD fill:#fff1cc
```

### Relationship Matrix (Consolidated)

```mermaid
graph LR
    TD[TechnicalDepartment]
    PROJ[Project]
    SYS[System]
    SS[Subsystem]
    COMP[Component]
    REQ[Requirement]
    ADR[AustralianDesignRule]
    EER[ExtractedEssentialRequirement]
    ERR[ExtractedRecommendedRequirement]
    VP[VerificationProcedure]
    VM[VerificationMethod]
    TEV[TestingEvidence]

    TD -->|departmentAssignedToProject| PROJ
    TD -->|assignedToSystem| SYS
    TD -->|assignedToSubsystem| SS

    SYS -->|hasSubsystem| SS

    PROJ -->|projectHasRequirement| REQ
    SYS -->|systemHasRequirement| REQ
    SS -->|subsystemHasRequirement| REQ

    COMP -->|componentInProject| PROJ
    COMP -->|componentInSystem| SYS
    COMP -->|componentInSubsystem| SS

    ADR -->|hasExternalEssentialRequirement| EER
    ADR -->|hasExternalRecommendedRequirement| ERR
    EER -->|assignedToProject| PROJ
    ADR -->|hasVerificationProcedure| VP
    VP -->|hasVerificationMethod| VM
    VP -->|supportedByEvidence| TEV
    ADR -->|verifiedBy| TEV
    COMP -->|generatesEvidence| TEV

    style TD fill:#fff1cc
    style ADR fill:#ffdddd
    style COMP fill:#e1f5ff
    style REQ fill:#f5e1ff
```

---

## neo4j Access

### Start neo4j

```bash
brew services start neo4j
```

### Open neo4j Browser

```bash
open http://localhost:7474
```

### Login Credentials

- **Connect URL**: `bolt://localhost:7687`
- **Username**: `neo4j`
- **Password**: your Neo4j password (set `NEO4J_PASSWORD` in `thesis-extension/.env`; never commit it)

### Quick Queries

See [cypher.md](cypher.md) for comprehensive query examples including:
- Schema validation
- Component tracking
- ADR verification
- Traceability analysis
- Cost & weight analysis
- Supply chain queries

---

*This ontology provides complete traceability across Projects, Components, & Regulatory Compliance for the SR8 tri-brid electric vehicle project.*