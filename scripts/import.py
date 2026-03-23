#!/usr/bin/env python3

import csv
from neo4j import GraphDatabase
import os

# ─────────────────────────────────────────────────────────────
# ADR reference data — name + relevant ADR titles for your VD
# instance data. Extend this dict as you add more ADRs.
# ─────────────────────────────────────────────────────────────
ADR_REFERENCE = {
    "ADR-10":  "Steering Column",
    "ADR-23":  "Passenger Car Tyres",
    "ADR-25":  "Anti-Theft Lock",
    "ADR-31":  "Passenger Car Brake Systems",
    "ADR-42":  "General Safety Requirements",
    "ADR-43":  "Vehicle Configuration & Dimensions",
    "ADR-92":  "External Projections",
}


class SR8OntologyImporter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print(f"✓ Connected To neo4j @ {uri}")

    def close(self):
        self.driver.close()
        print("✓ Connection Closed")

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✓ DB Cleared")

    # ──────────────────────────────────────────────────────────
    # SCHEMA IMPORT (unchanged from original)
    # ──────────────────────────────────────────────────────────

    def create_constraints(self):
        constraints = [
            "CREATE CONSTRAINT schema_label_name IF NOT EXISTS FOR (n:SchemaLabel) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT schema_rel_name   IF NOT EXISTS FOR (r:SchemaRelationship) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT schema_prop_name  IF NOT EXISTS FOR (p:SchemaProperty) REQUIRE p.name IS UNIQUE",
            "CREATE INDEX schema_label_category  IF NOT EXISTS FOR (n:SchemaLabel) ON (n.category)",
            "CREATE INDEX schema_label_type      IF NOT EXISTS FOR (n:SchemaLabel) ON (n.type)",
            # Instance data constraints
            "CREATE CONSTRAINT project_id  IF NOT EXISTS FOR (p:Project)               REQUIRE p.projectID   IS UNIQUE",
            "CREATE CONSTRAINT adr_id      IF NOT EXISTS FOR (a:AustralianDesignRule)   REQUIRE a.hasID       IS UNIQUE",
            "CREATE CONSTRAINT dept_name   IF NOT EXISTS FOR (d:Department)             REQUIRE d.hasName     IS UNIQUE",
            "CREATE CONSTRAINT member_name IF NOT EXISTS FOR (m:Member)                 REQUIRE m.hasName     IS UNIQUE",
        ]
        with self.driver.session() as session:
            for c in constraints:
                try:
                    session.run(c)
                    print(f"  ✓ {c.split()[1]}")
                except Exception:
                    print(f"  (already exists: {c.split()[1]})")

    def import_node_labels(self, csv_file="csv/node-labels.csv"):
        print(f"\n📊 Importing Node Labels From {csv_file}...")
        with open(csv_file, 'r') as f:
            labels = list(csv.DictReader(f))
        with self.driver.session() as session:
            for row in labels:
                session.run("""
                    MERGE (n:SchemaLabel {name: $label})
                    SET n.parent      = $parent,
                        n.description = $description,
                        n.type        = $type,
                        n.category    = $category
                """,
                    label=row['Label'],
                    parent=row['ParentLabel'] if row['ParentLabel'] else None,
                    description=row['Description'],
                    type=row['Type'],
                    category=row['Category']
                )
        print(f"  ✓ {len(labels)} Node Labels Imported")
        return len(labels)

    def create_label_hierarchy(self):
        print("\n🔗 Creating Node Label Hierarchy...")
        with self.driver.session() as session:
            result = session.run("""
                MATCH (child:SchemaLabel)
                WHERE child.parent IS NOT NULL
                MATCH (parent:SchemaLabel {name: child.parent})
                MERGE (child)-[:SUBCLASS_OF]->(parent)
                RETURN count(*) AS count
            """)
            count = result.single()['count']
        print(f"  ✓ {count} Hierarchy Relationships Created")
        return count

    def import_relationships(self, csv_file="csv/relationships.csv"):
        print(f"\n📊 Importing Relationships From {csv_file}...")
        with open(csv_file, 'r') as f:
            rels = list(csv.DictReader(f))
        with self.driver.session() as session:
            for row in rels:
                session.run("""
                    MERGE (r:SchemaRelationship {name: $name})
                    SET r.sourceLabel = $source,
                        r.targetLabel = $target,
                        r.description = $description,
                        r.properties  = $properties
                """,
                    name=row['RelationshipType'],
                    source=row['SourceLabel'],
                    target=row['TargetLabel'],
                    description=row['Description'],
                    properties=row['Properties']
                )
        print(f"  ✓ {len(rels)} Relationship Types Imported")
        return len(rels)

    def import_properties(self, csv_file="csv/node-properties.csv"):
        print(f"\n📊 Importing Properties From {csv_file}...")
        with open(csv_file, 'r') as f:
            props = list(csv.DictReader(f))
        with self.driver.session() as session:
            for row in props:
                session.run("""
                    MERGE (p:SchemaProperty {name: $name})
                    SET p.applicableLabels = $applicableLabels,
                        p.dataType         = $dataType,
                        p.description      = $description,
                        p.constraints      = $constraints
                """,
                    name=row['PropertyName'],
                    applicableLabels=row['ApplicableLabels'],
                    dataType=row['DataType'],
                    description=row['Description'],
                    constraints=row['Constraints']
                )
        print(f"  ✓ {len(props)} Property Definitions Imported")
        return len(props)

    # ──────────────────────────────────────────────────────────
    # INSTANCE DATA IMPORT  ← NEW SECTION
    # ──────────────────────────────────────────────────────────

    def import_instance_data(self, csv_file="csv/instance-vd-projects.csv"):
        """
        Reads instance-vd-projects.csv and creates:
          - Department nodes
          - Member nodes
          - AustralianDesignRule nodes  (seeded from ADR_REFERENCE dict)
          - Project nodes
          - Relationships:
              (Project)-[:hasPrimaryDepartment]->(Department)
              (Project)-[:hasSecondaryDepartment]->(Department)
              (Project)-[:hasAssignee]->(Member)
              (Project)-[:assignedToProject]<-[:assignedToProject]-(ADR)
        """
        print(f"\n🏗️  Importing Instance Data From {csv_file}...")

        if not os.path.exists(csv_file):
            print(f"  ⚠️  {csv_file} not found — skipping instance data.")
            return 0

        with open(csv_file, 'r') as f:
            rows = list(csv.DictReader(f))

        # ── 1. Collect unique departments, members, ADRs ──────
        departments = set()
        members     = set()
        adrs_needed = set()

        for row in rows:
            if row.get('PrimaryDepartment'):
                departments.add(row['PrimaryDepartment'].strip())
            if row.get('SecondaryDepartment'):
                departments.add(row['SecondaryDepartment'].strip())
            if row.get('Assignee'):
                members.add(row['Assignee'].strip())
            for adr_col in ['ADR1','ADR2','ADR3','ADR4','ADR5']:
                val = row.get(adr_col, '').strip()
                if val:
                    adrs_needed.add(val)

        # ── 2. Create Department nodes ─────────────────────────
        with self.driver.session() as session:
            for dept in departments:
                session.run("""
                    MERGE (d:Department:TechnicalDepartment {hasName: $name})
                    ON CREATE SET d.hasID = 'DEPT-' + $name
                """, name=dept)
        print(f"  ✓ {len(departments)} Department(s) Created/Merged")

        # ── 3. Create Member nodes ─────────────────────────────
        with self.driver.session() as session:
            for member in members:
                session.run("""
                    MERGE (m:Member {hasName: $name})
                    ON CREATE SET m.hasID = 'MBR-' + $name
                """, name=member)
        print(f"  ✓ {len(members)} Member(s) Created/Merged")

        # ── 4. Create AustralianDesignRule nodes ───────────────
        with self.driver.session() as session:
            for adr_id in adrs_needed:
                adr_name = ADR_REFERENCE.get(adr_id, adr_id)
                session.run("""
                    MERGE (a:AustralianDesignRule {hasID: $id})
                    ON CREATE SET a.hasName   = $name,
                                  a.isVerified = false,
                                  a.usesAlternativeTesting = false,
                                  a.rightProjectAssigned   = false
                    ON MATCH SET  a.hasName   = $name
                """, id=adr_id, name=adr_name)
        print(f"  ✓ {len(adrs_needed)} ADR Node(s) Created/Merged")

        # ── 5. Create Project nodes + all relationships ────────
        projects_created = 0
        with self.driver.session() as session:
            for row in rows:
                pid   = row['ProjectID'].strip()
                pname = row['ProjectName'].strip()
                pdept = row.get('PrimaryDepartment', '').strip()
                sdept = row.get('SecondaryDepartment', '').strip()
                asgn  = row.get('Assignee', '').strip()

                # Project node
                session.run("""
                    MERGE (p:Project {projectID: $pid})
                    ON CREATE SET p.projectName        = $pname,
                                  p.projectDescription = $pname + ' project'
                    ON MATCH SET  p.projectName = $pname
                """, pid=pid, pname=pname)

                # Primary department relationship
                if pdept:
                    session.run("""
                        MATCH (p:Project   {projectID: $pid})
                        MATCH (d:Department {hasName: $dept})
                        MERGE (p)-[:hasPrimaryDepartment]->(d)
                    """, pid=pid, dept=pdept)

                # Secondary department relationship
                if sdept:
                    session.run("""
                        MATCH (p:Project   {projectID: $pid})
                        MATCH (d:Department {hasName: $dept})
                        MERGE (p)-[:hasSecondaryDepartment]->(d)
                    """, pid=pid, dept=sdept)

                # Assignee relationship
                if asgn:
                    session.run("""
                        MATCH (p:Project {projectID: $pid})
                        MATCH (m:Member  {hasName: $name})
                        MERGE (p)-[:hasAssignee]->(m)
                    """, pid=pid, name=asgn)

                # ADR relationships — both directions per ontology
                for adr_col in ['ADR1','ADR2','ADR3','ADR4','ADR5']:
                    adr_id = row.get(adr_col, '').strip()
                    if adr_id:
                        session.run("""
                            MATCH (p:Project              {projectID: $pid})
                            MATCH (a:AustralianDesignRule {hasID: $aid})
                            MERGE (a)-[:assignedToProject]->(p)
                        """, pid=pid, aid=adr_id)

                projects_created += 1

        print(f"  ✓ {projects_created} Project(s) Created/Merged With Relationships")
        return projects_created

    def verify_instance_data(self):
        """Quick sanity-check counts after instance import."""
        print("\n🔍 Instance Data Verification:")
        with self.driver.session() as session:
            checks = {
                "Projects":    "MATCH (n:Project)               RETURN count(n) AS c",
                "Departments": "MATCH (n:Department)            RETURN count(n) AS c",
                "Members":     "MATCH (n:Member)                RETURN count(n) AS c",
                "ADRs":        "MATCH (n:AustralianDesignRule)  RETURN count(n) AS c",
                "Proj→Dept":   "MATCH ()-[:hasPrimaryDepartment]->() RETURN count(*) AS c",
                "ADR→Proj":    "MATCH ()-[:assignedToProject]->()    RETURN count(*) AS c",
            }
            for label, query in checks.items():
                result = session.run(query)
                count = result.single()['c']
                status = "✓" if count > 0 else "⚠️ "
                print(f"  {status} {label:<15} : {count}")

    # ──────────────────────────────────────────────────────────
    # STATS & VERIFICATION (unchanged)
    # ──────────────────────────────────────────────────────────

    def get_statistics(self):
        print("\n📈 Schema Statistics:")
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n:SchemaLabel)
                RETURN n.category AS category, count(*) AS count
                ORDER BY count DESC
            """)
            total = 0
            for r in result:
                total += r['count']
                print(f"  • {r['category']}: {r['count']}")
            print(f"  TOTAL: {total}")

            for label, query in [
                ("Relationship Types", "MATCH (r:SchemaRelationship) RETURN count(r) AS c"),
                ("Property Defs",      "MATCH (p:SchemaProperty)     RETURN count(p) AS c"),
                ("Hierarchy Rels",     "MATCH ()-[:SUBCLASS_OF]->()  RETURN count(*) AS c"),
            ]:
                result = session.run(query)
                print(f"  {label}: {result.single()['c']}")

    def verify_import(self):
        print("\n✅ Schema Verification:")
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n:SchemaLabel)
                WHERE n.type = 'TopLevel'
                RETURN n.name AS name ORDER BY n.name
            """)
            top_level = [r['name'] for r in result]
            print(f"  Top-Level Categories ({len(top_level)}): {', '.join(top_level)}")

            result = session.run("""
                MATCH (n:SchemaLabel)
                WHERE n.parent IS NOT NULL
                  AND NOT EXISTS { MATCH (n)-[:SUBCLASS_OF]->() }
                RETURN count(n) AS count
            """)
            orphaned = result.single()['count']
            if orphaned:
                print(f"  ⚠️  {orphaned} Orphaned Label(s)")
            else:
                print("  ✓ No Orphaned Labels")

    # ──────────────────────────────────────────────────────────
    # FULL IMPORT ORCHESTRATOR
    # ──────────────────────────────────────────────────────────

    def full_import(self, clear_first=False, skip_instance=False):
        print("=" * 60)
        print("SR8 ONTOLOGY IMPORT TO NEO4J")
        print("=" * 60)

        if clear_first:
            response = input("\n⚠️  Clear Existing DB? (yes/no): ")
            if response.lower() == 'yes':
                self.clear_database()

        # ── Schema ────────────────────────────────────────────
        self.create_constraints()
        labels_count    = self.import_node_labels()
        hierarchy_count = self.create_label_hierarchy()
        rel_count       = self.import_relationships()
        prop_count      = self.import_properties()

        self.get_statistics()
        self.verify_import()

        # ── Instance Data ─────────────────────────────────────
        if not skip_instance:
            print("\n" + "─" * 60)
            print("INSTANCE DATA (Vehicle Dynamics Projects + ADRs)")
            print("─" * 60)
            self.import_instance_data()
            self.verify_instance_data()

        print("\n" + "=" * 60)
        print("✅ IMPORT COMPLETE!")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"  Schema  : {labels_count} labels, {hierarchy_count} hierarchy rels,")
        print(f"            {rel_count} relationship types, {prop_count} properties")
        if not skip_instance:
            print(f"  Instance: VD Projects + ADRs loaded & aligned")
        print(f"\n  neo4j Browser : http://localhost:7474")
        print(f"  Quick check   : MATCH (p:Project)-[:assignedToProject]-(a:AustralianDesignRule)")
        print(f"                  RETURN p.projectName, a.hasID ORDER BY p.projectID")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Import SR8 Ontology + Instance Data')
    parser.add_argument('--uri',           default='bolt://localhost:7687')
    parser.add_argument('--user',          default='neo4j')
    parser.add_argument('--password',      default='password')
    parser.add_argument('--clear',         action='store_true', help='Clear DB Before Import')
    parser.add_argument('--schema-only',   action='store_true', help='Skip Instance Data')
    args = parser.parse_args()

    importer = SR8OntologyImporter(args.uri, args.user, args.password)
    try:
        importer.full_import(
            clear_first=args.clear,
            skip_instance=args.schema_only
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        importer.close()


if __name__ == '__main__':
    main()