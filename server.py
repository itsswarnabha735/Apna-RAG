"""
Local RAG Search Agent - FastAPI Server
Exposes local LanceDB search via a secure endpoint.
Run with: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import subprocess
import sys
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import LanceDB
from langchain_community.retrievers import BM25Retriever
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from flashrank import Ranker, RerankRequest

# --- Configuration ---
EMBEDDING_MODEL = "nomic-embed-text"
DOCS_DIR = "/Users/swarnabha.saha/Library/CloudStorage/OneDrive-RelianceCorporateITParkLimited/Personal/Personal RAG/Docs"
LANCEDB_URI = "./lancedb_data"

# --- Pydantic Models ---
class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5

class SearchResult(BaseModel):
    text: str
    score: float
    source: Optional[str] = None

class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str

class HealthResponse(BaseModel):
    status: str
    vector_store_ready: bool
    bm25_ready: bool

# --- Initialize Components ---
print("🚀 Initializing Local RAG Agent...")

print("  [1/4] Loading Embeddings...")
embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

print("  [2/4] Connecting to Vector Store...")
if not os.path.exists(LANCEDB_URI):
    os.makedirs(LANCEDB_URI)
vector_store = LanceDB(embedding=embeddings, uri=LANCEDB_URI)

print("  [3/4] Initializing Re-ranker...")
reranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.flashrank_cache")

print("  [4/4] Building BM25 Index...")
def load_docs_for_bm25(directory: str):
    loaders = {".pdf": PyPDFLoader, ".txt": TextLoader, ".md": TextLoader}
    documents = []
    if os.path.exists(directory):
        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in loaders:
                    try:
                        loader = loaders[ext](os.path.join(root, file))
                        documents.extend(loader.load())
                    except Exception as e:
                        print(f"  ⚠️ BM25 Load Error for {file}: {e}")
    return documents

bm25_docs = load_docs_for_bm25(DOCS_DIR)
bm25_retriever = None
if bm25_docs:
    bm25_retriever = BM25Retriever.from_documents(bm25_docs)
    bm25_retriever.k = 10
    print(f"  ✅ BM25 Index built with {len(bm25_docs)} documents.")
else:
    print("  ⚠️ No documents found for BM25. Keyword search disabled.")

print("✅ Local RAG Agent Ready!")

# --- FastAPI App ---
app = FastAPI(
    title="Local RAG Search Agent",
    description="Exposes local LanceDB vector search for the cloud frontend.",
    version="1.0.0"
)

# CORS: Allow the Vercel frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for the tunnel/frontend."""
    return HealthResponse(
        status="ok",
        vector_store_ready=vector_store is not None,
        bm25_ready=bm25_retriever is not None
    )

class IngestResponse(BaseModel):
    status: str
    message: str
    documents_processed: Optional[int] = None

@app.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion():
    """
    Trigger document ingestion: runs ingest.py and reloads the vector store and BM25 index.
    """
    global vector_store, bm25_retriever, bm25_docs
    
    try:
        # Step 1: Run the ingest.py script
        print("🔄 Running ingestion script...")
        result = subprocess.run(
            [sys.executable, "ingest.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for large document sets
        )
        
        if result.returncode != 0:
            print(f"❌ Ingestion failed: {result.stderr}")
            return IngestResponse(
                status="error",
                message=f"Ingestion script failed: {result.stderr}"
            )
        
        print("✅ Ingestion script completed. Reloading indexes...")
        
        # Step 2: Reload the vector store
        vector_store = LanceDB(embedding=embeddings, uri=LANCEDB_URI)
        print("  ✅ Vector store reloaded.")
        
        # Step 3: Reload BM25 index
        bm25_docs = load_docs_for_bm25(DOCS_DIR)
        if bm25_docs:
            bm25_retriever = BM25Retriever.from_documents(bm25_docs)
            bm25_retriever.k = 10
            print(f"  ✅ BM25 Index rebuilt with {len(bm25_docs)} documents.")
        else:
            bm25_retriever = None
            print("  ⚠️ No documents found for BM25 after reload.")
        
        return IngestResponse(
            status="success",
            message="Knowledge base refreshed successfully!",
            documents_processed=len(bm25_docs) if bm25_docs else 0
        )
        
    except subprocess.TimeoutExpired:
        return IngestResponse(
            status="error",
            message="Ingestion timed out after 10 minutes."
        )
    except Exception as e:
        print(f"❌ Ingestion error: {e}")
        return IngestResponse(
            status="error",
            message=f"Ingestion error: {str(e)}"
        )

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Hybrid Search: Vector + BM25, then Re-rank.
    Returns the top_k most relevant document chunks.
    """
    query = request.query
    top_k = request.top_k or 5
    
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    
    unique_docs = {}
    
    # 1. Vector Search
    try:
        v_results = vector_store.similarity_search(query, k=10)
        for doc in v_results:
            unique_docs[doc.page_content] = {"text": doc.page_content, "meta": doc.metadata}
    except Exception as e:
        print(f"Vector search error: {e}")
    
    # 2. BM25 Keyword Search
    if bm25_retriever:
        try:
            k_results = bm25_retriever.invoke(query)
            for doc in k_results:
                unique_docs[doc.page_content] = {"text": doc.page_content, "meta": doc.metadata}
        except Exception as e:
            print(f"BM25 search error: {e}")
    
    if not unique_docs:
        return SearchResponse(results=[], query=query)
    
    # 3. Re-rank
    passages = [
        {"id": str(i), "text": d["text"], "meta": d["meta"]}
        for i, d in enumerate(unique_docs.values())
    ]
    
    rerank_request = RerankRequest(query=query, passages=passages)
    reranked = reranker.rerank(rerank_request)
    reranked = sorted(reranked, key=lambda x: x["score"], reverse=True)[:top_k]
    
    results = [
        SearchResult(
            text=r["text"],
            score=r["score"],
            source=r.get("meta", {}).get("source", "unknown")
        )
        for r in reranked
    ]
    
    return SearchResponse(results=results, query=query)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
