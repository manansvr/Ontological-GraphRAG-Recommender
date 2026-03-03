# SR8 Ontology - Complete System Guide
## ADR Verification & Component Management

**Version:** 2.0  
**Date:** March 2, 2026  
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [ADR Verification System](#adr-verification-system)
4. [Component Management System](#component-management-system)
5. [Data Model](#data-model)
6. [Column Mapping Reference](#column-mapping-reference)
7. [Neo4j Implementation](#neo4j-implementation)
8. [Query Examples](#query-examples)
9. [Import Guide](#import-guide)

---

## Overview

The SR8 ontology provides a comprehensive semantic model for the Sunswift Racing SR8 tri-brid electric vehicle project, integrating:

- **113 Australian Design Rules (ADRs)** with verification tracking
- **100,000+ Components** with full lifecycle management
- **600,000+ Requirements** with traceability
- **189 Projects** with integration workflows
- **16 Departments** with organizational hierarchy

### Key Capabilities

✅ **End-to-End Traceability**: Component → Project → ADR → Evidence  
✅ **Lifecycle Tracking**: Car build through road testing  
✅ **Cost & Weight Management**: Estimated vs actual with variance analysis  
✅ **Supply Chain Integration**: Supplier and procurement tracking  
✅ **Compliance Verification**: Evidence-based ADR verification  
✅ **Inventory Control**: Real-time stock and location tracking

### Ontology Statistics

| Metric | Count |
|--------|-------|
| **Classes** | 105 |
| **Object Properties** | 43 |
| **Data Properties** | 52 |
| **Named Individuals** | 12 |
| **Total Elements** | 200+ |

---

## System Architecture

### Core Integration Flow

```
┌─────────────┐
│  Component  │──────────────┐
│  (Part)     │              │
└──────┬──────┘              │
       │                     │
       │ usedInProject       │ generatesEvidence
       ↓                     ↓
┌────────────┐         ┌──────────┐
│  Project   │         │ Evidence │
└─────┬──────┘         └────┬─────┘
      │                     │
      │                     │ verifiedBy
      │ assignedToProject   ↓
      └──────────────→ ┌─────────────────────┐
                       │ AustralianDesignRule│
                       │      (ADR)          │
                       └─────────────────────┘
```

### Six Main Hierarchies

1. **Organization** → Teams, departments, partners
2. **Artifact** → Vehicles, documents, requirements, **components**
3. **Process** → Extraction, extension, validation, **lifecycle milestones**
4. **Technology** → Neo4j, LLMs, tools
5. **Concept** → Systems engineering, compliance, AI
6. **Agent** → Multi-agent reasoning system

---

## ADR Verification System

### What Is Tracked

Every ADR (Australian Design Rule) must have:

1. **Project Assignment**: One or more projects responsible for compliance
2. **Verification Procedure**: Detailed testing/validation procedure
3. **Verification Method**: How compliance is verified
4. **Evidence**: Proof of compliance (simulation, mathematics, or actual test)

### Verification Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| **Inspection** | Visual or manual inspection | Physical checks, visual compliance |
| **Demonstration** | Functional demonstration | Feature demonstrations |
| **Test** | Physical or functional testing | Performance testing, load testing |
| **Analysis** | Simulations and calculations | CFD, FEA, mathematical proofs |
| **ADR Annex** | ADR annex procedures | Regulatory-specified methods |
| **ADR Testing Procedure** | Official ADR testing | Certification testing |

### Evidence Types

| Evidence Type | Description | Example |
|---------------|-------------|---------|
| **TestEvidence** | Actual physical testing | Crash test results, photometric tests |
| **SimulationEvidence** | Computational simulation | CFD analysis, thermal simulations |
| **MathematicalEvidence** | Calculations and analysis | Structural calculations, load analysis |

### ADR Data Properties

| Property | Type | Description |
|----------|------|-------------|
| `hasClause` | string | Clause reference (e.g., "42.2.3") |
| `requirementName` | string | Short requirement name |
| `requirementText` | string | Full requirement text |
| `isVerified` | boolean | Verification status |
| `usesAlternativeTesting` | boolean | Alternative testing flag |
| `rightProjectAssigned` | boolean | Correct project flag |
| `alternativeProjectSuggestion` | string | Suggested alternative project |

### ADR Relationships

```
AustralianDesignRule
    ├── assignedToProject ──────> Project
    ├── assignedToDepartment ───> Department
    ├── hasVerificationProcedure → VerificationProcedure
    │       ├── hasVerificationMethod ──> VerificationMethod
    │       └── supportedByEvidence ────> Evidence
    └── verifiedBy ─────────────────────> Evidence
```

---

## Component Management System

### Complete Parts Tracking

Every component tracks:

- **Identification**: Part number, description, BOM level
- **Project & Department**: Organizational assignment
- **Lifecycle Milestones**: Progress through testing phases
- **Physical Properties**: Weight, quantity
- **ADR Integration**: Links to related ADRs and evidence generation
- **Supply Chain**: Supplier, procurement, order status
- **Cost Management**: Estimated vs actual costs
- **Inventory**: Stock quantity and location

### Component Data Properties

#### Identification & Classification
- `partNumber` (string) - Unique identifier
- `partDescription` (string) - Component description
- `bomLevel` (integer) - BOM hierarchy level
- `approvalStatus` (string) - Approval state
- `componentStatus` (string) - Current status
- `onCarSoftwareOffCar` (string) - Classification type

#### Physical Properties
- `quantityPer` (integer) - Quantity per assembly
- `estimatedWeight` (float) - Estimated weight (kg)
- `actualWeight` (float) - Actual weight (kg)

#### ADR Integration
- `relatedADRs` (string) - Comma-separated ADR list
- `engineeringDrawingRequired` (boolean)

#### Supply Chain
- `procurementStatus` (string) - Procurement state
- `supplier` (string) - Supplier name
- `orderStatus` (string) - Order state
- `stockQuantity` (integer) - Quantity in stock
- `stockLocation` (string) - Physical location

#### Cost Tracking
- `assemblyEstimatedCost` (float)
- `assemblyActualCost` (float)

### Component Relationships

| Relationship | To | Description |
|--------------|-----|-------------|
| `usedInProject` | Project | Project assignment |
| `belongsToDepartment` | Department | Department responsibility |
| `usedInADR` | AustralianDesignRule | ADR verification link |
| `generatesEvidence` | Evidence | Evidence creation |
| `suppliedBy` | IndustryPartner | Supplier link |
| `partOfBOM` | Component | BOM hierarchy |

---

## Data Model

### Complete Component-to-ADR Integration

```
Component
    ├── Identification
    │   ├── partNumber: "BMS-2024-001"
    │   ├── partDescription: "Battery Management System"
    │   └── bomLevel: 2
    │
    ├── Organization
    │   ├── usedInProject ──────────> Project
    │   ├── belongsToDepartment ───> Department
    │   └── partOfBOM ─────────────> Component (parent)
    │
    ├── Supply Chain
    │   ├── suppliedBy ────────────> IndustryPartner
    │   ├── procurementStatus: "Received"
    │   ├── orderStatus: "Complete"
    │   ├── stockQuantity: 3
    │   └── stockLocation: "Workshop A-12"
    │
    ├── ADR Verification
    │   ├── usedInADR ─────────────> AustralianDesignRule
    │   ├── generatesEvidence ─────> Evidence
    │   │       └── verifiedBy ───> AustralianDesignRule
    │   └── relatedADRs: "ADR-42, ADR-68"
    │
    ├── Physical Properties
    │   ├── quantityPer: 1
    │   ├── estimatedWeight: 2.5 kg
    │   └── actualWeight: 2.3 kg
    │
    └── Cost Tracking
        ├── assemblyEstimatedCost: $850
        └── assemblyActualCost: $820
```

---

## Column Mapping Reference

### Parts Management Spreadsheet → Ontology

| # | Spreadsheet Column | Ontology Property/Relationship | Type |
|---|-------------------|-------------------------------|------|
| 1 | DEPARTMENT | `belongsToDepartment` → Department | Relationship |
| 2 | SECTION | `Department.sectionName` | String |
| 3 | PROJECT # | `Project.projectID` | String |
| 4 | PROJECT | `usedInProject` → Project | Relationship |
| 5 | APPROVED | `approvalStatus` | String |
| 6 | STATUS | `componentStatus` | String |
| 7 | ONCAR SOFTWARE OFFCAR | `onCarSoftwareOffCar` | String |
| 8 | BOM LEVEL | `bomLevel` | Integer |
| 9 | PART NUMBER | `partNumber` | String |
| 10 | PART DESCRIPTION | `partDescription` | String |
| 11 | QTY PER | `quantityPer` | Integer |
| 12 | ADR'S | `relatedADRs` + `usedInADR` | String + Relationship |
| 13 | ENG DWG REQ | `engineeringDrawingRequired` | Boolean |
| 14 | EST WEIGHT kg | `estimatedWeight` | Float |
| 15 | ACTUAL WEIGHT kg | `actualWeight` | Float |
| 16 | PROCUREMENT | `procurementStatus` | String |
| 17 | SUPPLIER / PARTNER | `supplier` + `suppliedBy` | String + Relationship |
| 18 | ASSEMBLY EST COST | `assemblyEstimatedCost` | Float |
| 19 | ASSEMBLY ACTUAL COST | `assemblyActualCost` | Float |
| 20 | ORDER STATUS | `orderStatus` | String |
| 21 | STOCK QTY | `stockQuantity` | Integer |
| 22 | STOCK LOCATION | `stockLocation` | String |

---

## Neo4j Implementation

### Creating a Complete Component

```cypher
// Create component with all properties
CREATE (c:Component {
    hasID: "COMP-ELEC-BMS-001",
    partNumber: "BMS-2024-001",
    partDescription: "Battery Management System - Primary Controller",
    bomLevel: 2,
    approvalStatus: "Approved",
    componentStatus: "In Production",
    onCarSoftwareOffCar: "On-Car Software",
    quantityPer: 1,
    estimatedWeight: 2.5,
    actualWeight: 2.3,
    relatedADRs: "ADR-42, ADR-68",
    engineeringDrawingRequired: true,
    procurementStatus: "Received",
    supplier: "Texas Instruments",
    assemblyEstimatedCost: 850.00,
    assemblyActualCost: 820.00,
    orderStatus: "Complete",
    stockQuantity: 3,
    stockLocation: "Workshop A-12"
})

// Create/match related entities
MERGE (dept:Department {hasID: "DEPT-ELEC"})
ON CREATE SET dept.hasName = "Electrical Engineering"

MERGE (proj:Project {projectID: "PROJ-ELEC-01"})
ON CREATE SET proj.hasName = "Electrical Systems"

MERGE (supplier:IndustryPartner {hasName: "Texas Instruments"})

// Create relationships
CREATE (c)-[:belongsToDepartment]->(dept)
CREATE (c)-[:usedInProject]->(proj)
CREATE (c)-[:suppliedBy]->(supplier)
```

### Creating ADR with Verification

```cypher
// Create ADR
CREATE (adr:AustralianDesignRule {
    hasID: "ADR-042",
    hasName: "ADR-42",
    hasClause: "42.2.3",
    requirementName: "Headlamp Performance",
    requirementText: "Headlamps shall provide adequate illumination...",
    isVerified: true,
    usesAlternativeTesting: true,
    rightProjectAssigned: true
})

// Create verification procedure
CREATE (proc:VerificationProcedure {
    hasID: "VP-042-001",
    hasName: "Headlamp Photometric Test",
    verificationMethodDescription: "Photometric testing using calibrated lux meter..."
})

// Create verification method and evidence
CREATE (method:Test {hasName: "Physical Testing"})
CREATE (evidence:TestEvidence {
    hasID: "EV-042-001",
    hasName: "Photometric Test Results"
})

// Link everything together
CREATE (adr)-[:hasVerificationProcedure]->(proc)
CREATE (proc)-[:hasVerificationMethod]->(method)
CREATE (proc)-[:supportedByEvidence]->(evidence)
CREATE (adr)-[:verifiedBy]->(evidence)

// Link component to ADR and evidence
MATCH (c:Component {partNumber: "BMS-2024-001"})
CREATE (c)-[:usedInADR]->(adr)
CREATE (c)-[:generatesEvidence]->(evidence)
```

---

## Query Examples

### Component Queries

#### 1. All Components by Project
```cypher
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       COUNT(c) AS Component_Count,
       SUM(c.actualWeight) AS Total_Weight_kg,
       SUM(c.assemblyActualCost) AS Total_Cost
ORDER BY Component_Count DESC;
```

#### 2. Weight Variance Analysis
```cypher
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       SUM(c.estimatedWeight) AS Estimated_Weight_kg,
       SUM(c.actualWeight) AS Actual_Weight_kg,
       SUM(c.actualWeight) - SUM(c.estimatedWeight) AS Variance_kg,
       ROUND(100.0 * (SUM(c.actualWeight) - SUM(c.estimatedWeight)) / 
             SUM(c.estimatedWeight), 2) AS Variance_Percent
ORDER BY Actual_Weight_kg DESC;
```

#### 3. Cost Analysis by Project
```cypher
MATCH (c:Component)-[:usedInProject]->(p:Project)
RETURN p.hasName AS Project,
       SUM(c.assemblyEstimatedCost) AS Estimated_Cost,
       SUM(c.assemblyActualCost) AS Actual_Cost,
       SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost) AS Variance,
       ROUND(100.0 * (SUM(c.assemblyActualCost) - SUM(c.assemblyEstimatedCost)) /
             SUM(c.assemblyEstimatedCost), 2) AS Variance_Percent
ORDER BY Actual_Cost DESC;
```

#### 5. Stock Inventory Report
```cypher
MATCH (c:Component)
WHERE c.stockQuantity > 0
RETURN c.stockLocation AS Location,
       COUNT(c) AS Parts_Count,
       SUM(c.stockQuantity) AS Total_Quantity,
       SUM(c.assemblyActualCost * c.stockQuantity) AS Inventory_Value
ORDER BY Inventory_Value DESC;
```

### ADR Verification Queries

#### 6. Unverified ADRs
```cypher
MATCH (adr:AustralianDesignRule)
WHERE adr.isVerified = false
RETURN adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement,
       adr.hasClause AS Clause
ORDER BY adr.hasID;
```

#### 7. Verification Completion by Project
```cypher
MATCH (p:Project)<-[:assignedToProject]-(adr:AustralianDesignRule)
WITH p,
     SUM(CASE WHEN adr.isVerified = true THEN 1 ELSE 0 END) AS verified,
     COUNT(adr) AS total
RETURN p.hasName AS Project,
       total AS Total_ADRs,
       verified AS Verified_ADRs,
       ROUND(100.0 * verified / total, 2) AS Completion_Percent
ORDER BY Completion_Percent DESC;
```

#### 8. ADRs by Verification Method
```cypher
MATCH (adr:AustralianDesignRule)-[:hasVerificationProcedure]->
      (proc:VerificationProcedure)-[:hasVerificationMethod]->(method)
RETURN labels(method)[0] AS Verification_Method,
       COUNT(adr) AS ADR_Count,
       COLLECT(adr.hasID)[0..5] AS Sample_ADRs
ORDER BY ADR_Count DESC;
```

### Integration Queries

#### 9. Components Generating ADR Evidence
```cypher
MATCH (c:Component)-[:generatesEvidence]->(ev:Evidence)
      <-[:verifiedBy]-(adr:AustralianDesignRule)
RETURN c.partNumber AS Part_Number,
       c.partDescription AS Component,
       labels(ev)[0] AS Evidence_Type,
       adr.hasID AS ADR_ID,
       adr.requirementName AS Requirement
ORDER BY adr.hasID;
```

#### 10. Complete Traceability Path
```cypher
MATCH path = (c:Component)-[:usedInProject]->(p:Project),
             (c)-[:generatesEvidence]->(ev:Evidence),
             (ev)<-[:verifiedBy]-(adr:AustralianDesignRule),
             (adr)-[:assignedToProject]->(p)
RETURN c.partNumber AS Component,
       p.hasName AS Project,
       labels(ev)[0] AS Evidence_Type,
       adr.hasID AS ADR,
       adr.isVerified AS Verified
ORDER BY adr.hasID;
```

#### 11. Department Workload Analysis
```cypher
MATCH (c:Component)-[:belongsToDepartment]->(d:Department)
RETURN d.hasName AS Department,
       COUNT(c) AS Component_Count,
       SUM(c.assemblyActualCost) AS Total_Budget,
       SUM(c.actualWeight) AS Total_Weight_kg
ORDER BY Component_Count DESC;
```

#### 12. Comprehensive Component Report
```cypher
MATCH (c:Component)
OPTIONAL MATCH (c)-[:usedInProject]->(p:Project)
OPTIONAL MATCH (c)-[:belongsToDepartment]->(d:Department)
OPTIONAL MATCH (c)-[:suppliedBy]->(s:IndustryPartner)
RETURN d.hasName AS Department,
       p.projectID AS Project_ID,
       c.partNumber AS Part_Number,
       c.partDescription AS Description,
       c.relatedADRs AS ADRs,
       c.actualWeight AS Weight_kg,
       s.hasName AS Supplier,
       c.assemblyActualCost AS Cost,
       c.stockQuantity AS Stock,
       c.stockLocation AS Location
ORDER BY d.hasName, p.projectID, c.partNumber;
```

---

## Import Guide

### Step 1: Prepare Your Data

Clean your spreadsheet data:
- Ensure unique part numbers
- Standardize status values
- Convert checkmarks to TRUE/FALSE
- Verify weight units (kg)
- Standardize currency (AUD)

### Step 2: Create CSV File

Export to `components.csv`:
```csv
partNumber,partDescription,department,project,actualWeight,actualCost,supplier,stockQty,stockLocation,relatedADRs
BMS-2024-001,Battery Management System,Electrical Engineering,PROJ-ELEC-01,2.3,820.00,Texas Instruments,3,Workshop A-12,"ADR-42, ADR-68"
```

### Step 3: Bulk Import with Cypher

```cypher
// Load components
LOAD CSV WITH HEADERS FROM 'file:///components.csv' AS row
CREATE (c:Component {
    partNumber: row.partNumber,
    partDescription: row.partDescription,
    actualWeight: toFloat(row.actualWeight),
    assemblyActualCost: toFloat(row.actualCost),
    stockQuantity: toInteger(row.stockQty),
    stockLocation: row.stockLocation,
    relatedADRs: row.relatedADRs
})
WITH c, row
MERGE (d:Department {hasName: row.department})
MERGE (p:Project {projectID: row.project})
MERGE (s:IndustryPartner {hasName: row.supplier})
CREATE (c)-[:belongsToDepartment]->(d)
CREATE (c)-[:usedInProject]->(p)
CREATE (c)-[:suppliedBy]->(s);
```

### Step 4: Link to ADRs

```cypher
// Parse ADR relationships
MATCH (c:Component)
WHERE c.relatedADRs IS NOT NULL
UNWIND split(c.relatedADRs, ',') AS adrID
WITH c, trim(adrID) AS cleanADRID
MATCH (adr:AustralianDesignRule)
WHERE adr.hasID = cleanADRID
CREATE (c)-[:usedInADR]->(adr);
```

### Step 5: Verify Import

```cypher
// Count nodes and relationships
MATCH (c:Component) RETURN count(c) AS Components;
MATCH ()-[r:usedInProject]->() RETURN count(r) AS ProjectLinks;
MATCH ()-[r:usedInADR]->() RETURN count(r) AS ADRLinks;
```

---

## Best Practices

### Data Entry
- Use consistent naming conventions
- Always populate part numbers
- Update milestone flags as work progresses
- Record actual weights and costs when available
- Link components to ADRs during design phase

### Query Optimization
- Create constraints on unique identifiers
- Index frequently queried properties
- Use MERGE for idempotent operations
- Batch large imports

### Maintenance
- Regular stock inventory audits
- Update verification status as tests complete
- Track cost variances for budget management
- Monitor weight for performance optimization

---

## Support Files

- **project-ontology.owl** - Full OWL/RDF ontology specification
- **ontology-documentation.md** - Detailed class and property documentation
- **neo4j-examples.cypher** - 50+ ready-to-use queries
- **validate.py** - Ontology validation script

---

## Quick Reference

### Key Node Types
- `Component` - Parts and assemblies
- `AustralianDesignRule` - ADR requirements
- `Project` - Engineering projects
- `Department` - Organizational units
- `Evidence` - Verification evidence
- `IndustryPartner` - Suppliers

### Critical Relationships
- `usedInProject` - Component to Project
- `usedInADR` - Component to ADR
- `generatesEvidence` - Component to Evidence
- `verifiedBy` - ADR to Evidence
- `suppliedBy` - Component to Supplier

### Essential Queries
1. Component inventory by project
2. Milestone readiness tracking
3. Weight and cost variance
4. ADR verification status
5. Supply chain tracking
6. Stock inventory
7. Complete traceability

---

**Ontology Version:** 2.0  
**Total Elements:** 200+ (105 classes, 43 properties, 52 attributes)  
**Validation:** ✅ Complete  
**Status:** Production Ready

*For technical support, refer to ontology-documentation.md or Neo4j query examples.*
