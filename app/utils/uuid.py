import uuid

def generate_unique_link_id():
    return str(uuid.uuid4())[:8] # Example: first 8 chars of a UUID
