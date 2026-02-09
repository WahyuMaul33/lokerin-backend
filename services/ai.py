from sentence_transformers import SentenceTransformer

# Load all-MiniLM-L6-v2
print("Loading the model ....")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model Loaded!")

def get_embedding(text: str) -> list[float]:
    """
    Converts text (like 'Python, FastAPI') into a list of 384 numbers.
    """
    if not text:
        return []

    return model.encode(text).tolist()