
from langsmith import traceable


@traceable
def parse_document(client, file_path):
        # Upload and parse a document
        file = client.files.create(file=file_path, purpose="parse")
        result = client.parsing.parse(
            file_id=file.id,
            tier="agentic",
            version="latest",
            processing_options={ 
                "cost_optimizer" : {
                            "enable": True
                            }
                },
            expand=["markdown"],
        )
        return result.markdown.pages[0].markdown


