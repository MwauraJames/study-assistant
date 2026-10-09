from llama_index.core import Document
from ingestion.parse import Parser, client
from ingestion.chunk import Chunk

parser = Parser(client)
chunker= Chunk()

file_path = "test.pdf"  # Replace with the path to your document
parsed_content = parser.parse_document(file_path)

doc = Document(text=parsed_content)
retriever= chunker.chunk_documents([doc])

retrieved_nodes = retriever.retrieve("Give me my PROFESSIONAL SUMMARY")



print("Retrieved Nodes:")
for node in retrieved_nodes:
    print(f"- {node.metadata.get('file_name', 'Unknown')}: {node.text[:100]}...")