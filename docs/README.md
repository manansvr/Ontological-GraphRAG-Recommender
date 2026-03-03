# SR8 Ontology - Semantic Model for Vehicle Engineering

## Overview

Comprehensive OWL/RDF ontology for the Sunswift Racing SR8 tri-brid electric vehicle project, integrating:

- **Project Tracking System** - 189 Projects, 15 Departments, 100 Members
- **Parts Management System** - Component/BOM hierarchy with lifecycle tracking
- **ADR Management System** - 100 Australian Design Rules with verification

## Quick Start

**📚 Complete Documentation:** See [SR8-ONTOLOGY-DOCUMENTATION.md](docs/SR8-ONTOLOGY-DOCUMENTATION.md)

### Statistics
- 48 classes
- 36 object properties
- 51 data properties
- 5 named individuals
- 3 top-level hierarchies: Organization, Artifact, Process

### Neo4j Setup

```bash
# Start Neo4j
brew services start neo4j

# Open browser
open http://localhost:7474

# Connect to: bolt://localhost:7687
# Username: neo4j
# Password: [your-password]
```

### Import Ontology

```bash
# Validate ontology structure
python3 scripts/validate.py

# Import schema to Neo4j (once authentication is fixed)
python3 scripts/import.py
```

## Core Files

| File | Description |
|------|-------------|
| **docs/SR8-ONTOLOGY-DOCUMENTATION.md** | Complete combined documentation |
| **project-ontology.owl** | OWL/RDF ontology specification |
| **csv/neo4j-node-labels.csv** | Node label definitions |
| **csv/neo4j-relationships.csv** | Relationship definitions |
| **csv/neo4j-node-properties.csv** | Property definitions |
| **scripts/validate.py** | Validation script |
| **scripts/import.py** | Neo4j import script |

## Three-System Architecture

### 1. Project Tracking System
- Projects with primary/secondary departments
- Member assignments
- Cross-system integration

### 2. Parts Management System
- Component hierarchy (100,000+ parts)
- BOM levels
- Project linkage
- ADR compliance tracking

### 3. ADR Management System
- 100 Australian Design Rules
- 6 verification methods (Inspection, Demonstration, Test, Analysis, ADR Annex, ADR Testing Procedure)
- 6 evidence types aligned with verification methods
- Project and department associations

## Evidence & Verification

**Key Concept:** Evidence is formed when multiple components work together to pass testing procedures.

**Verification Methods:**
- Inspection → InspectionEvidence
- Demonstration → DemonstrationEvidence
- Test → TestEvidence
- Analysis → AnalysisEvidence
- ADR Annex → ADRAnnexEvidence
- ADR Testing Procedure → ADRTestingProcedureEvidence

## Documentation Structure

The complete documentation (SR8-ONTOLOGY-DOCUMENTATION.md) contains:

1. **Overview** - System introduction and quick start
2. **Quick Reference** - Essential classes and relationships
3. **Three-System Architecture** - Integration between PTS, Parts, and ADRs
4. **Ontology Documentation** - Detailed class hierarchies
5. **Visual Diagrams** - Mermaid diagrams for visualization
6. **Complete System Guide** - ADR verification and component management
7. **Neo4j Import Guide** - Database setup and import procedures

## Validation

```bash
python3 scripts/validate.py
```

Expected output:
- ✓ 46 Classes
- ✓ 36 Object Properties
- ✓ 51 Data Properties
- ✓ 5 Individuals
- ✓ XML syntax valid
- ✓ All classes have labels

## Support

- Ontology version: 2.0
- Status: Production Ready
- Last updated: March 3, 2026

For detailed documentation, see **SR8-ONTOLOGY-DOCUMENTATION.md**
