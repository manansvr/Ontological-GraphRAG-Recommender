# Extend The Ontology

## Add New Class
```xml
<owl:Class rdf:about="#NewSubSystem">
    <rdfs:subClassOf rdf:resource="#SubSystem"/>
    <rdfs:label>New SubSystem Type</rdfs:label>
    <rdfs:comment>Description of New SubSystem</rdfs:comment>
</owl:Class>
```

## Add New Relationship
```xml
<owl:ObjectProperty rdf:about="#newRelationship">
    <rdfs:domain rdf:resource="#SourceClass"/>
    <rdfs:range rdf:resource="#TargetClass"/>
    <rdfs:label>New Relationship</rdfs:label>
</owl:ObjectProperty>
```

## Add New Individual
```xml
<owl:NamedIndividual rdf:about="#NewInstance">
    <rdf:type rdf:resource="#ClassName"/>
    <hasName>Instance Name</hasName>
    <hasDescription>Instance Description</hasDescription>
</owl:NamedIndividual>
```