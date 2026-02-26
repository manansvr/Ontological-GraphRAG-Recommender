#!/usr/bin/env python3
"""
Import SR8 Ontology into Neo4j
Reads CSV files and creates nodes, relationships, and constraints in Neo4j
"""

import csv
from neo4j import GraphDatabase
import os

class SR8OntologyImporter:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password"):
        """Initialize Neo4j connection"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print(f"✓ Connected to Neo4j at {uri}")
    
    def close(self):
        """Close the Neo4j connection"""
        self.driver.close()
        print("✓ Connection closed")
    
    def clear_database(self):
        """Clear all nodes and relationships (use with caution!)"""
        with self.driver.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            print("✓ Database cleared")
    
    def create_constraints(self):
        """Create uniqueness constraints and indexes"""
        constraints = [
            "CREATE CONSTRAINT schema_label_name IF NOT EXISTS FOR (n:SchemaLabel) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT schema_rel_name IF NOT EXISTS FOR (r:SchemaRelationship) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT schema_prop_name IF NOT EXISTS FOR (p:SchemaProperty) REQUIRE p.name IS UNIQUE",
            "CREATE INDEX schema_label_category IF NOT EXISTS FOR (n:SchemaLabel) ON (n.category)",
            "CREATE INDEX schema_label_type IF NOT EXISTS FOR (n:SchemaLabel) ON (n.type)",
        ]
        
        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    print(f"✓ Created: {constraint.split()[1]}")
                except Exception as e:
                    print(f"  (Already exists or error: {constraint.split()[1]})")
    
    def import_node_labels(self, csv_file="neo4j-node-labels.csv"):
        """Import node labels from CSV"""
        print(f"\n📊 Importing node labels from {csv_file}...")
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            labels = list(reader)
        
        with self.driver.session() as session:
            for row in labels:
                session.run("""
                    MERGE (n:SchemaLabel {name: $label})
                    SET n.parent = $parent,
                        n.description = $description,
                        n.type = $type,
                        n.category = $category
                """, 
                    label=row['Label'],
                    parent=row['ParentLabel'] if row['ParentLabel'] else None,
                    description=row['Description'],
                    type=row['Type'],
                    category=row['Category']
                )
        
        print(f"✓ Imported {len(labels)} node labels")
        return len(labels)
    
    def create_label_hierarchy(self):
        """Create parent-child relationships between labels"""
        print(f"\n🔗 Creating label hierarchy...")
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (child:SchemaLabel)
                WHERE child.parent IS NOT NULL
                MATCH (parent:SchemaLabel {name: child.parent})
                MERGE (child)-[:SUBCLASS_OF]->(parent)
                RETURN count(*) as count
            """)
            count = result.single()['count']
        
        print(f"✓ Created {count} hierarchy relationships")
        return count
    
    def import_relationships(self, csv_file="neo4j-relationships.csv"):
        """Import relationship types from CSV"""
        print(f"\n📊 Importing relationships from {csv_file}...")
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            relationships = list(reader)
        
        with self.driver.session() as session:
            for row in relationships:
                session.run("""
                    MERGE (r:SchemaRelationship {name: $name})
                    SET r.sourceLabel = $source,
                        r.targetLabel = $target,
                        r.description = $description,
                        r.properties = $properties
                """,
                    name=row['RelationshipType'],
                    source=row['SourceLabel'],
                    target=row['TargetLabel'],
                    description=row['Description'],
                    properties=row['Properties']
                )
        
        print(f"✓ Imported {len(relationships)} relationship types")
        return len(relationships)
    
    def import_properties(self, csv_file="neo4j-node-properties.csv"):
        """Import node properties from CSV"""
        print(f"\n📊 Importing properties from {csv_file}...")
        
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            properties = list(reader)
        
        with self.driver.session() as session:
            for row in properties:
                session.run("""
                    MERGE (p:SchemaProperty {name: $name})
                    SET p.applicableLabels = $applicableLabels,
                        p.dataType = $dataType,
                        p.description = $description,
                        p.constraints = $constraints
                """,
                    name=row['PropertyName'],
                    applicableLabels=row['ApplicableLabels'],
                    dataType=row['DataType'],
                    description=row['Description'],
                    constraints=row['Constraints']
                )
        
        print(f"✓ Imported {len(properties)} property definitions")
        return len(properties)
    
    def get_statistics(self):
        """Get database statistics"""
        print(f"\n📈 Database Statistics:")
        
        with self.driver.session() as session:
            # Count schema labels by category
            result = session.run("""
                MATCH (n:SchemaLabel)
                RETURN n.category as category, count(*) as count
                ORDER BY count DESC
            """)
            
            print("\n  Node Labels by Category:")
            total_labels = 0
            for record in result:
                count = record['count']
                total_labels += count
                print(f"    • {record['category']}: {count}")
            print(f"    TOTAL: {total_labels}")
            
            # Count relationships
            result = session.run("MATCH (r:SchemaRelationship) RETURN count(r) as count")
            rel_count = result.single()['count']
            print(f"\n  Relationship Types: {rel_count}")
            
            # Count properties
            result = session.run("MATCH (p:SchemaProperty) RETURN count(p) as count")
            prop_count = result.single()['count']
            print(f"  Property Definitions: {prop_count}")
            
            # Count hierarchy relationships
            result = session.run("MATCH ()-[r:SUBCLASS_OF]->() RETURN count(r) as count")
            hier_count = result.single()['count']
            print(f"  Hierarchy Relationships: {hier_count}")
    
    def verify_import(self):
        """Run verification queries"""
        print(f"\n✅ Verification:")
        
        with self.driver.session() as session:
            # Check top-level categories
            result = session.run("""
                MATCH (n:SchemaLabel)
                WHERE n.type = 'TopLevel'
                RETURN n.name as name
                ORDER BY n.name
            """)
            
            top_level = [record['name'] for record in result]
            print(f"\n  Top-Level Categories ({len(top_level)}):")
            for name in top_level:
                print(f"    ✓ {name}")
            
            # Check for orphaned labels
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
                print(f"\n  ⚠️  Warning: {orphaned} orphaned labels found")
            else:
                print(f"\n  ✓ No orphaned labels")
    
    def export_sample_queries(self):
        """Export sample Cypher queries for testing"""
        queries = {
            "Find all Agent types": """
                MATCH (n:SchemaLabel)
                WHERE n.category = 'Agent'
                RETURN n.name, n.description
            """,
            
            "Get class hierarchy": """
                MATCH path = (child:SchemaLabel)-[:SUBCLASS_OF*]->(root:SchemaLabel)
                WHERE root.type = 'TopLevel'
                RETURN child.name as class, root.name as root, length(path) as depth
                ORDER BY depth DESC, class
            """,
            
            "Find relationships for Requirements": """
                MATCH (r:SchemaRelationship)
                WHERE r.sourceLabel = 'Requirement' OR r.targetLabel = 'Requirement'
                RETURN r.name, r.sourceLabel, r.targetLabel
            """,
            
            "List properties by data type": """
                MATCH (p:SchemaProperty)
                RETURN p.dataType as type, collect(p.name) as properties
                ORDER BY type
            """
        }
        
        print(f"\n💡 Sample Queries:")
        for title, query in queries.items():
            print(f"\n  {title}:")
            print(f"  {query.strip()}")
    
    def full_import(self, clear_first=False):
        """Run complete import process"""
        print("=" * 60)
        print("SR8 ONTOLOGY IMPORT TO NEO4J")
        print("=" * 60)
        
        if clear_first:
            response = input("\n⚠️  Clear existing database? (yes/no): ")
            if response.lower() == 'yes':
                self.clear_database()
        
        # Create constraints
        self.create_constraints()
        
        # Import data
        labels_count = self.import_node_labels()
        hierarchy_count = self.create_label_hierarchy()
        rel_count = self.import_relationships()
        prop_count = self.import_properties()
        
        # Statistics and verification
        self.get_statistics()
        self.verify_import()
        self.export_sample_queries()
        
        print("\n" + "=" * 60)
        print("✅ IMPORT COMPLETE!")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"  • {labels_count} node labels imported")
        print(f"  • {hierarchy_count} hierarchy relationships created")
        print(f"  • {rel_count} relationship types imported")
        print(f"  • {prop_count} property definitions imported")
        print(f"\n🚀 Ready to populate with SR8 project data!")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import SR8 Ontology into Neo4j')
    parser.add_argument('--uri', default='bolt://localhost:7687', help='Neo4j URI')
    parser.add_argument('--user', default='neo4j', help='Neo4j username')
    parser.add_argument('--password', default='password', help='Neo4j password')
    parser.add_argument('--clear', action='store_true', help='Clear database before import')
    
    args = parser.parse_args()
    
    # Create importer
    importer = SR8OntologyImporter(args.uri, args.user, args.password)
    
    try:
        # Run full import
        importer.full_import(clear_first=args.clear)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        importer.close()


if __name__ == '__main__':
    main()
