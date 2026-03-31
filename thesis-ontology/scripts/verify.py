#!/usr/bin/env python3

from neo4j import GraphDatabase
import sys

class OntologyVerifier:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            print(f"✓ Connected To neo4j @ {uri}")
        except Exception as e:
            print(f"✗ Failed To Connect To neo4j: {e}")
            sys.exit(1)

    def close(self):
        self.driver.close()

    def verify_node_labels(self):
        print("\n" + "="*60)
        print("VERIFYING NODE LABELS")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("MATCH (n:SchemaLabel) RETURN count(n) as count")
            count = result.single()['count']

            if count == 66:
                print(f"✓ All 66 Node Labels Imported Correctly")
            else:
                print(f"✗ Expected 66 Node Labels, Found {count}")
                return False

            result = session.run("""
                MATCH (n:SchemaLabel)
                RETURN n.category as category, count(*) as count
                ORDER BY count DESC
            """)

            print("\n  Node Labels By Category:")
            for record in result:
                print(f"    • {record['category']}: {record['count']}")

            result = session.run("""
                MATCH (clause:SchemaLabel {name: 'Clause'})-[:SUBCLASS_OF]->(parent)
                RETURN parent.name as parent
                ORDER BY parent
            """)

            parents = [r['parent'] for r in result]
            expected_parents = [
                'ExtractedEssentialRequirement',
                'ExtractedRecommendedRequirement',
                'InternalEssentialRequirement',
                'InternalRecommendedRequirement'
            ]

            if sorted(parents) == sorted(expected_parents):
                print(f"\n✓ Clause Has Correct 4 Parent Classes")
            else:
                print(f"\n✗ Clause Parents In-Correct:")
                print(f"  Expected: {expected_parents}")
                print(f"  Found: {parents}")
                return False

        return True

    def verify_relationships(self):
        print("\n" + "="*60)
        print("VERIFYING RELATIONSHIPS")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("MATCH (r:SchemaRelationship) RETURN count(r) as count")
            count = result.single()['count']

            if count == 49:
                print(f"✓ All 49 Relationship Types Imported Correctly")
            else:
                print(f"✗ Expected 49 Relationships, Found {count}")
                return False

            key_relationships = [
                'hasClause',
                'usedInProject',
                'usedInADR',
                'verifiedBy',
                'supportedByEvidence',
                'suppliedBy',
                'partOfBOM',
                'belongsToDepartment',
                'hasSection'
            ]

            result = session.run("""
                MATCH (r:SchemaRelationship)
                WHERE r.name IN $names
                RETURN r.name as name
            """, names=key_relationships)

            found = [r['name'] for r in result]

            if sorted(found) == sorted(key_relationships):
                print(f"\n✓ All Key Relationships Present:")
                for rel in sorted(found):
                    print(f"    • {rel}")
            else:
                missing = set(key_relationships) - set(found)
                print(f"\n✗ Missing Relationships: {missing}")
                return False

        return True

    def verify_validation_and_verification_rules(self):
        print("\n" + "="*60)
        print("VERIFYING VALIDATION & VERIFICATION RULES")
        print("="*60)

        with self.driver.session() as session:
            checks = [
                {
                    'name': 'TechnicalDepartment assignment trio',
                    'query': """
                        MATCH (r:SchemaRelationship)
                        WHERE (r.name = 'departmentAssignedToProject' AND r.sourceLabel = 'TechnicalDepartment' AND r.targetLabel = 'Project')
                           OR (r.name = 'assignedToSystem' AND r.sourceLabel = 'TechnicalDepartment' AND r.targetLabel = 'System')
                           OR (r.name = 'assignedToSubsystem' AND r.sourceLabel = 'TechnicalDepartment' AND r.targetLabel = 'Subsystem')
                        RETURN count(r) as count
                    """,
                    'expected': 3
                },
                {
                    'name': 'System hierarchy linkage',
                    'query': """
                        MATCH (r:SchemaRelationship {name: 'hasSubsystem', sourceLabel: 'System', targetLabel: 'Subsystem'})
                        RETURN count(r) as count
                    """,
                    'expected': 1
                },
                {
                    'name': 'Requirement ownership trio',
                    'query': """
                        MATCH (r:SchemaRelationship)
                        WHERE (r.name = 'projectHasRequirement' AND r.sourceLabel = 'Project' AND r.targetLabel = 'Requirement')
                           OR (r.name = 'systemHasRequirement' AND r.sourceLabel = 'System' AND r.targetLabel = 'Requirement')
                           OR (r.name = 'subsystemHasRequirement' AND r.sourceLabel = 'Subsystem' AND r.targetLabel = 'Requirement')
                        RETURN count(r) as count
                    """,
                    'expected': 3
                },
                {
                    'name': 'Component placement trio',
                    'query': """
                        MATCH (r:SchemaRelationship)
                        WHERE (r.name = 'componentInProject' AND r.sourceLabel = 'Component' AND r.targetLabel = 'Project')
                           OR (r.name = 'componentInSystem' AND r.sourceLabel = 'Component' AND r.targetLabel = 'System')
                           OR (r.name = 'componentInSubsystem' AND r.sourceLabel = 'Component' AND r.targetLabel = 'Subsystem')
                        RETURN count(r) as count
                    """,
                    'expected': 3
                },
                {
                    'name': 'ADR external requirement links',
                    'query': """
                        MATCH (r:SchemaRelationship)
                        WHERE (r.name = 'hasExternalEssentialRequirement' AND r.sourceLabel = 'AustralianDesignRule' AND r.targetLabel = 'ExtractedEssentialRequirement')
                           OR (r.name = 'hasExternalRecommendedRequirement' AND r.sourceLabel = 'AustralianDesignRule' AND r.targetLabel = 'ExtractedRecommendedRequirement')
                        RETURN count(r) as count
                    """,
                    'expected': 2
                },
                {
                    'name': 'Validation relationship chain',
                    'query': """
                        MATCH (r:SchemaRelationship)
                        WHERE (r.name = 'validatesUseCase' AND r.targetLabel = 'ValidationScenario')
                           OR (r.name = 'hasAcceptanceCriterion' AND r.sourceLabel = 'ValidationScenario' AND r.targetLabel = 'AcceptanceCriterion')
                           OR (r.name = 'validatedBy' AND r.targetLabel = 'ValidationResult')
                           OR (r.name = 'validatesRequirement' AND r.sourceLabel = 'ValidationResult' AND r.targetLabel = 'Requirement')
                        RETURN count(r) as count
                    """,
                    'expected': 4
                }
            ]

            all_passed = True
            for check in checks:
                result = session.run(check['query'])
                found = result.single()['count']
                if found == check['expected']:
                    print(f"✓ {check['name']}")
                else:
                    print(f"✗ {check['name']} (expected {check['expected']}, found {found})")
                    all_passed = False

        return all_passed

    def verify_properties(self):
        print("\n" + "="*60)
        print("VERIFYING PROPERTIES")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("MATCH (p:SchemaProperty) RETURN count(p) as count")
            count = result.single()['count']

            if count == 43:
                print(f"✓ All 43 Properties Imported Correctly")
            else:
                print(f"✗ Expected 43 Properties, Found {count}")
                return False

            result = session.run("""
                MATCH (p:SchemaProperty)
                RETURN p.dataType as type, count(*) as count
                ORDER BY count DESC
            """)

            print("\n  Properties By Data Type:")
            for record in result:
                print(f"    • {record['type']}: {record['count']}")

            result = session.run("""
                MATCH (p:SchemaProperty)
                WHERE p.applicableLabels = 'Component'
                RETURN count(p) as count
            """)

            component_props = result.single()['count']
            print(f"\n  Component-Specific Properties: {component_props}")

            key_properties = [
                'partNumber',
                'partDescription',
                'bomLevel',
                'estimatedWeight',
                'actualWeight',
                'supplier',
                'stockQuantity',
                'stockLocation',
                'requirementText',
                'testingProcedurePerRequirement',
                'isVerified'
            ]

            result = session.run("""
                MATCH (p:SchemaProperty)
                WHERE p.name IN $names
                RETURN p.name as name
            """, names=key_properties)

            found = [r['name'] for r in result]

            if sorted(found) == sorted(key_properties):
                print(f"\n✓ All Key Properties Present:")
                for prop in sorted(found):
                    print(f"    • {prop}")
            else:
                missing = set(key_properties) - set(found)
                print(f"\n✗ Missing Properties: {missing}")
                return False

        return True

    def verify_hierarchy(self):
        print("\n" + "="*60)
        print("VERIFYING CLASS HIERARCHY")
        print("="*60)

        with self.driver.session() as session:
            result = session.run("MATCH ()-[r:SUBCLASS_OF]->() RETURN count(r) as count")
            count = result.single()['count']
            print(f"  Total Hierarchy Relationships: {count}")

            result = session.run("""
                MATCH (n:SchemaLabel)
                WHERE n.type = 'TopLevel'
                RETURN n.name as name
                ORDER BY n.name
            """)

            top_level = [r['name'] for r in result]
            expected_top = [
                'Organization',
                'ProjectTrackingSystem',
                'Document',
                'Requirement',
                'PartsManagement',
                'Project',
            ]

            if sorted(top_level) == sorted(expected_top):
                print(f"\n✓ All Top-Level Classes Present:")
                for cls in sorted(top_level):
                    print(f"    • {cls}")
            else:
                print(f"\n✗ Top-level Classes Incorrect:")
                print(f"  Expected: {expected_top}")
                print(f"  Found: {top_level}")
                return False

            result = session.run("""
                MATCH (n:SchemaLabel)
                WHERE n.parent IS NOT NULL
                  AND NOT EXISTS {
                    MATCH (n)-[:SUBCLASS_OF]->()
                  }
                RETURN count(n) as count
            """)

            orphaned = result.single()['count']
            if orphaned > 0:
                print(f"\n✗ Found {orphaned} Orphaned Nodes")
                return False
            else:
                print(f"\n✓ No Orphaned Nodes")

        return True

    def run_all_verifications(self):
        print("\n" + "="*60)
        print("SR8 ONTOLOGY VERIFICATION")
        print("="*60)

        results = {
            'Node Labels': self.verify_node_labels(),
            'Relationships': self.verify_relationships(),
            'Properties': self.verify_properties(),
            'Hierarchy': self.verify_hierarchy(),
            'Validation/Verification Rules': self.verify_validation_and_verification_rules()
        }

        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)

        all_passed = True
        for check, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {check}: {status}")
            if not passed:
                all_passed = False

        print("\n" + "="*60)
        if all_passed:
            print("✓ ALL VERIFICATIONS PASSED!")
        else:
            print("✗ SOME VERIFICATIONS FAILED")
        print("="*60)

        return all_passed

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Verify SR8 Ontology Import')
    parser.add_argument('--uri', default='bolt://localhost:7687', help='neo4j URI')
    parser.add_argument('--user', default='neo4j', help='neo4j User Name')
    parser.add_argument('--password', default='password', help='neo4j Password')

    args = parser.parse_args()

    verifier = OntologyVerifier(args.uri, args.user, args.password)

    try:
        success = verifier.run_all_verifications()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        verifier.close()

if __name__ == "__main__":
    main()