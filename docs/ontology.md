# SR8 Thesis Ontology Documentation

This ontology formally represents the knowledge domain of the Sunswift Racing SR8 tri-brid electric vehicle project, integrating regulatory compliance, knowledge graph technologies, & AI-assisted reasoning.

**Version**: 2.0
**Created**: February 26, 2026
**Authors**: Manan Rathi, Ilina Sharma

**Ontology Statistics:**
- **Classes**: 48 (Node Labels)
- **Object Properties**: 37 (Relationships)
- **Data Properties**: 56 (Attributes)
- **Total Elements**: 200+

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Class Hierarchies](#class-hierarchies)
3. [Object Properties (Relationships)](#object-properties-relationships)
4. [Data Properties (Attributes)](#data-properties-attributes)
5. [Visual Diagrams](#visual-diagrams)
6. [Neo4j Access](#neo4j-access)

---

## System Architecture

### Core Integration

The SR8 ontology integrates three main management systems:

```
┌─────────────────────────┐
│  Project Tracking (PTS) │
│  - 189 Projects         │
│  - 15 Departments       │
│  - 100 Members          │
└───────┬─────────────────┘
        │
        │ assignedToProject
        │ hasPrimaryDepartment
        │
┌───────▼─────────────────┐         ┌──────────────────────┐
│  ADR Management         │◄────────┤  Parts Management    │
│  - 100 ADRs             │         │  - 100,000+ Parts    │
│  - Verification         │         │  - BOM Hierarchy     │
│  - Evidence             │         │  - Supply Chain      │
└─────────────────────────┘         └──────────────────────┘
        │                                      │
        │ usedInADR                            │
        │ generatesEvidence                    │
        └──────────────────────────────────────┘
```

### 1. Project Tracking System (PTS)

**Projects** (189 total) - Single nodes with properties:
- `projectID` - Unique project identifier
- `projectName` - Name of the project
- `projectDescription` - Description of the project

**Departments** (15 total) - Organizational units:
- `TechnicalDepartment` - Technical departments
- `OperationalDepartment` - Operational departments
- Properties: `hasID`, `hasName`, `sectionName`

**Members** (100 total) - Project assignees:
- `hasID` - Member identifier
- `hasName` - Member name

**Relationships**:
- `hasPrimaryDepartment` → Department
- `hasSecondaryDepartment` → Department
- `hasAssignee` → Member
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
- `generatesEvidence` → Evidence
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
- `assignedToProject` → Project
- `assignedToDepartment` → Department
- `hasRelevantProject` → Project
- `hasRelevantDepartment` → Department
- `hasVerificationProcedure` → VerificationProcedure
- `hasVerificationMethod` → VerificationMethod
- `supportedByEvidence` → Evidence
- `verifiedBy` → Evidence

### Key Metrics

| System | Entities | Key Features |
|--------|----------|--------------|
| Project Tracking | 189 Projects, 15 Departments, 100 Members | Primary/secondary departments, member assignments |
| Parts Management | 100,000+ Components | BOM hierarchy, supply chain, cost tracking |
| ADR Management | 100 ADRs | 6 verification methods, evidence tracking |

---

## Class Hierarchies

### 1. Organization Hierarchy

```
Organization
├── SunswiftRacing [80 members, 16 departments, 189 projects]
├── Department
│   ├── TechnicalDepartment
│   └── OperationalDepartment
├── IndustryPartner
│   └── Neo4j
└── AcademicPartner
```

**Key Relationships**:
- `hasDepartment` - Organization → Department
- `collaboratesWith` - Organization ↔ Organization (symmetric)
- `hasSection` - Department → Department (organizational hierarchy)

### 2. Artifact Hierarchy

```
Artifact
├── Vehicle
│   ├── SR8 (Sunswift 8) [100,000+ components, road-legal tri-brid electric]
│   ├── Subsystem (2+ subsystems make a system)
│   ├── Interface (5,000+ interactions)
│   └── Project (189 concurrent)
├── Document
│   ├── RegulatoryDocument
│   │   └── AustralianDesignRule (ADR) [113 rules]
│   └── EngineeringBrief
│       ├── TechnicalSpecification
│       ├── TestReport
│       ├── DesignNote
│       ├── SimulationOutput
│       └── EngineeringDrawing
├── Requirement (600,000+)
│   ├── InternalRequirement
│   │   ├── InternalEssentialRequirement (non-negotiable constraints)
│   │   │   └── Clause
│   │   └── InternalRecommendedRequirement (contextual flexibility)
│   │       └── Clause
│   ├── ExternalRequirement
│   │   ├── ExternalEssentialRequirement (non-negotiable constraints)
│   │   │   └── Clause
│   │   └── ExternalRecommendedRequirement (contextual flexibility)
│   │       └── Clause
│   └── VerificationProcedure
│       └── VerificationMethod
│           ├── Inspection
│           ├── Demonstration
│           ├── Test
│           ├── Analysis
│           ├── ADRAnnex
│           └── ADRTestingProcedure
└── Component (100,000+)
    └── Evidence (formed when components work together to pass testing)
        ├── InspectionEvidence
        ├── DemonstrationEvidence
        ├── TestEvidence
        ├── AnalysisEvidence
        ├── ADRAnnexEvidence
        └── ADRTestingProcedureEvidence
```

### 3. Process Hierarchy

```
Process
├── ExtractionProcess
│   ├── DocumentParsing
│   ├── NLPProcessing
│   ├── EntityRecognition
│   └── RelationExtraction
├── ExtensionProcess
│   ├── LinkPredictionProcess
│   ├── LLMInferenceProcess
│   └── RLPrioritizationProcess
└── ValidationProcess
    ├── ConsistencyChecking
    ├── CompletenessValidation
    └── QualityAssessment
```

---

## Object Properties (Relationships)

### Organizational Relationships
- `hasDepartment` - Organization → Department
- `collaboratesWith` - Organization ↔ Organization (symmetric)
- `hasSection` - Department → Department

### Artifact Relationships
- `hasRequirement` - Artifact → Requirement
- `hasComponent` - Subsystem → Component (transitive)
- `hasSubsystem` - Vehicle → Subsystem
- `interfacesWith` - Subsystem ↔ Subsystem (symmetric)
- `dependsOn` - Requirement → Requirement (transitive)
- `appliesTo` - Requirement → Artifact
- `derivedFrom` - Requirement → AustralianDesignRule
- `documentedIn` - Artifact → Document

### ADR Verification Relationships
- `assignedToProject` - AustralianDesignRule → Project
- `assignedToDepartment` - AustralianDesignRule → Department
- `hasRelevantProject` - AustralianDesignRule → Project
- `hasRelevantDepartment` - AustralianDesignRule → Department
- `hasVerificationProcedure` - AustralianDesignRule → VerificationProcedure
- `hasVerificationMethod` - VerificationProcedure → VerificationMethod
- `supportedByEvidence` - VerificationProcedure → Evidence
- `verifiedBy` - AustralianDesignRule → Evidence
- `hasClause` - AustralianDesignRule → Clause

### Component Management Relationships
- `usedInProject` - Component → Project
- `usedInADR` - Component → AustralianDesignRule
- `generatesEvidence` - Component → Evidence
- `suppliedBy` - Component → IndustryPartner
- `partOfBOM` - Component → Component (BOM hierarchy)
- `belongsToDepartment` - Component → Department

### Project Tracking Relationships
- `hasPrimaryDepartment` - Project → Department
- `hasSecondaryDepartment` - Project → Department
- `hasAssignee` - Project → Member

### Process Relationships
- `hasInput` - Process → Artifact
- `isInputTo` - Artifact → Process (inverse of hasInput)
- `hasOutput` - Process → Artifact
- `precedesProcess` - Process → Process

### Compliance & Risk Relationships
- `compliesWith` - Artifact → AustralianDesignRule
- `hasRisk` - Artifact → Requirement
- `propagatesRiskTo` - Subsystem → Subsystem

### Property Characteristics
- **Symmetric**: `interfacesWith`, `collaboratesWith`
- **Transitive**: `dependsOn`, `hasComponent`
- **Inverse**: `hasInput` ↔ `isInputTo`

---

## Data Properties (Attributes)

### Identifiers & Metadata
- `hasID` (string) - Unique identifier
- `hasName` (string) - Entity name
- `hasDescription` (string) - Detailed description
- `hasTimestamp` (dateTime) - Temporal metadata

### Provenance & Confidence
- `hasSource` (string) - Data source
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

**Disjoint Classes**:
- `EssentialRequirement` ⊥ `RecommendedRequirement`
- `InternalRequirement` ⊥ `ExternalRequirement`

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

### SR8 Systems Architecture

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

    ADR[Australian<br/>Design Rules] -.derivedFrom.-> R1[Safety<br/>Requirements]
    ADR -.derivedFrom.-> R2[Performance<br/>Requirements]
    ADR -.derivedFrom.-> R3[Emission<br/>Requirements]

    R1 -.appliesTo.-> SS5
    R2 -.appliesTo.-> SS1
    R3 -.appliesTo.-> SS2

    style SR8 fill:#ffcc99
    style ADR fill:#ff9999
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
- **Password**: `password123`

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