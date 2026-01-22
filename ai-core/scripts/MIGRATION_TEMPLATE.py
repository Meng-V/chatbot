"""
Template for migrating scripts from Weaviate Cloud to Local Docker.

BEFORE (Cloud):
    import weaviate
    import weaviate.classes as wvc
    
    WEAVIATE_HOST = os.getenv("WEAVIATE_HOST")
    WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
    
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=WEAVIATE_HOST,
        auth_credentials=wvc.init.Auth.api_key(WEAVIATE_API_KEY),
        headers={"X-OpenAI-Api-Key": OPENAI_API_KEY}
    )

AFTER (Local Docker):
    from src.utils.weaviate_client import get_weaviate_client
    
    client = get_weaviate_client()
    
    # Remember to close when done
    client.close()
"""
