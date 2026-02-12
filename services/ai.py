from sentence_transformers import SentenceTransformer

# Load the model globally so it only loads once when the server starts.
print("Loading the model ....")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model Loaded!")

def get_embedding(text: str) -> list[float]:
    """
    **Generate Vector Embedding**
    
    Converts a string of text (e.g., "Python Developer with AWS experience") 
    into a mathematical vector (a list of 384 floating-point numbers).
    
    **Reason**
    The database (pgvector) needs these numbers to perform "Semantic Search" 
    (finding related concepts, not just matching keywords).
    
    **Returns:**
    - List[float]: A 384-dimensional vector.
    - If text is empty, returns a zero-vector.
    """
    if not text:
        # Return a "blank" vector of the correct size (384 for MiniLM)
        return [0.0] * 384

    # .tolist() converts the numpy array to a standard Python list
    return model.encode(text).tolist()