from ingestion.parse import Parser, client
from ingestion.chunk import Chunk

parser = Parser(client)
chunker= Chunk()

file_path = "test.txt"  # Replace with the path to your document
parsed_content = parser.parse_document(file_path)
result= chunker.chunk_documents([parsed_content])