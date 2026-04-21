import os
import networkx as nx
from config import RAG_WORKING_DIR

def list_entities():
    graph_path = str(RAG_WORKING_DIR / "graph_chunk_entity_relation.graphml")
    
    if not os.path.exists(graph_path):
        print(f"Error: Knowledge graph file not found at {graph_path}")
        return

    try:
        # Load the graph
        G = nx.read_graphml(graph_path)
        
        # Extract entity labels or IDs
        entities = []
        for node, data in G.nodes(data=True):
            # In LightRAG, nodes often have 'entity_type' and 'description'
            # Let's filter for nodes that have a label
            label = data.get('label')
            if label:
                entities.append(str(label))
            else:
                entities.append(str(node))
        
        # Deduplicate and sort
        entities = sorted(list(set(entities)))
        display_list = entities[:150]
        
        print(f"--- OmniGraph-Vault Entity List ---")
        print(f"Total Unique Entities: {len(entities)}")
        print(f"Showing first {len(display_list)}:")
        print("-" * 40)
        for i, entity in enumerate(display_list, 1):
            print(f"{i:3}. {entity}")
            
    except Exception as e:
        print(f"An error occurred while reading the graph: {e}")

if __name__ == "__main__":
    list_entities()
