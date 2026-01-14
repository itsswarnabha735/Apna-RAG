import chainlit as cl
import subprocess
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.vectorstores import LanceDB
from langchain_community.retrievers import BM25Retriever
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader, UnstructuredExcelLoader
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from typing import TypedDict, List
from flashrank import Ranker, RerankRequest

# --- Config ---
MODEL = "llama3.2:3b"
EMBEDDING = "nomic-embed-text"
DOCS_DIR = "/Users/swarnabha.saha/Library/CloudStorage/OneDrive-RelianceCorporateITParkLimited/Personal/Personal RAG/Docs"

# --- Setup ---
print("Initializing Embeddings...")
embeddings = OllamaEmbeddings(model=EMBEDDING)

print("Initializing Vector Store...")
# Ensure directory exists, otherwise LanceDB might fail if empty
if not os.path.exists("./lancedb_data"):
    os.makedirs("./lancedb_data")
vector_store = LanceDB(embedding=embeddings, uri="./lancedb_data")

# FlashRank for Reranking (runs locally on CPU/M1)
print("Initializing Re-ranker...")
reranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.flashrank_cache")

# Helper to load docs for BM25 (Keyword Search)
def load_docs_for_bm25(directory):
    print("Loading documents for BM25 index...")
    loaders = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".md": TextLoader,
    }
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
                        print(f"BM25 Load Error: {e}")
    return documents

# Initialize BM25 Retriever
print("Initializing BM25 Retriever...")
docs = load_docs_for_bm25(DOCS_DIR)
if docs:
    bm25_retriever = BM25Retriever.from_documents(docs)
    bm25_retriever.k = 10
else:
    print("Warning: No documents found for BM25. Keyword search will be disabled.")
    bm25_retriever = None

print("Initializing LLM...")
llm = ChatOllama(model=MODEL, temperature=0, keep_alive="5m")

# --- LangGraph State ---
class AgentState(TypedDict):
    question: str
    expanded_queries: List[str]
    retrieved_docs: List[Document]
    context: List[str]
    answer: str

# --- Nodes ---

def query_expansion(state: AgentState):
    print(f"Expanding Query: {state['question']}")
    prompt = ChatPromptTemplate.from_template(
        """You are an AI research assistant. Your task is to generate 3 different search queries based on the user's question to improve retrieval coverage.
        Also generate 1 hypothetical passage that might answer the question (HyDE).
        
        User Question: {question}

        Output ONLY the 3 queries and 1 hypothetical passage, one per line. No numbering, no bullets.
        """
    )
    chain = prompt | llm
    response = chain.invoke({"question": state["question"]})
    queries = response.content.strip().split("\n")
    # Clean up potentially empty lines
    queries = [q.strip() for q in queries if q.strip()]
    return {"expanded_queries": queries}

def hybrid_retrieve(state: AgentState):
    print("Executing Hybrid Retrieval...")
    unique_docs = {}
    
    # 1. Vector Search (Original + Expanded)
    search_queries = [state["question"]] + state.get("expanded_queries", [])
    
    # Deduplicate queries to save compute
    search_queries = list(set(search_queries))
    
    for q in search_queries:
        print(f"Vector search for: {q}")
        v_results = vector_store.similarity_search(q, k=5)
        for doc in v_results:
            unique_docs[doc.page_content] = doc # Key by content to dedupe

    # 2. Keyword Search (BM25) - Only on original query
    if bm25_retriever:
        print(f"Keyword search for: {state['question']}")
        k_results = bm25_retriever.invoke(state["question"])
        for doc in k_results:
             unique_docs[doc.page_content] = doc
             
    combined_docs = list(unique_docs.values())
    print(f"Total unique docs retrieved: {len(combined_docs)}")
    return {"retrieved_docs": combined_docs}

def rerank(state: AgentState):
    print("Reranking documents...")
    docs = state["retrieved_docs"]
    if not docs:
        return {"context": []}
    
    passages = [
        {"id": str(i), "text": doc.page_content, "meta": doc.metadata} 
        for i, doc in enumerate(docs)
    ]
    
    rerank_request = RerankRequest(query=state["question"], passages=passages)
    results = reranker.rerank(rerank_request)
    
    # Sort and take (Top 5)
    results = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    
    # Reconstruct context
    top_docs = [res["text"] for res in results]
    
    # Add metadata for citations (if available in source docs)
    # top_docs_with_meta = [f"Source: {res['meta'].get('source', 'unknown')}\nContent: {res['text']}" for res in results]
    
    return {"context": top_docs}

def generate(state: AgentState):
    print("Generating answer with Chain-of-Thought...")
    prompt = ChatPromptTemplate.from_template(
        """You are an intelligent expert assistant. Answer the user's question using the provided context.
        
        Instructions:
        1. Think step-by-step to understand the user's intent.
        2. Reference the context to support your answer.
        3. If the answer is not in the context, say "I couldn't find relevant information in the documents."
        
        Context:
        {context}

        Question: {question}
        
        Answer:
        """
    )
    chain = prompt | llm
    response = chain.invoke({"context": "\n\n".join(state["context"]), "question": state["question"]})
    return {"answer": response.content}

# --- Graph Construction ---
workflow = StateGraph(AgentState)
workflow.add_node("query_expansion", query_expansion)
workflow.add_node("hybrid_retrieve", hybrid_retrieve)
workflow.add_node("rerank", rerank)
workflow.add_node("generate", generate)

workflow.set_entry_point("query_expansion")
workflow.add_edge("query_expansion", "hybrid_retrieve")
workflow.add_edge("hybrid_retrieve", "rerank")
workflow.add_edge("rerank", "generate")
workflow.add_edge("generate", END)

app = workflow.compile()

# --- UI Interface (Chainlit) ---
@cl.action_callback("refresh_data")
async def on_action(action):
    msg = cl.Message(content="🔄 Running ingestion with Semantic Filtering...", author="System")
    await msg.send()
    
    try:
        # Run ingest.py
        result = subprocess.run(["python3", "ingest.py"], capture_output=True, text=True)
        if result.returncode == 0:
            # Reload BM25 and Vector Store
            global bm25_retriever, vector_store
            
            # Re-init vector store
            vector_store = LanceDB(embedding=embeddings, uri="./lancedb_data")
            
            # Re-init BM25
            new_docs = load_docs_for_bm25(DOCS_DIR)
            if new_docs:
                bm25_retriever = BM25Retriever.from_documents(new_docs)
                bm25_retriever.k = 10
            
            msg.content = "✅ Knowledge base updated! Semantic chunks created."
            await msg.update()
        else:
            msg.content = f"❌ Ingestion failed:\n{result.stderr}"
            await msg.update()
    except Exception as e:
        msg.content = f"❌ Error: {str(e)}"
        await msg.update()

@cl.on_chat_start
async def start():
    actions = [
        cl.Action(name="refresh_data", value="refresh", label="Refresh Knowledge Base", payload={})
    ]
    await cl.Message(content="Welcome! I am now powered by Hybrid Search & Re-ranking.", actions=actions).send()

@cl.on_message
async def main(message: cl.Message):
    inputs = {"question": message.content}
    result = await app.ainvoke(inputs)
    await cl.Message(content=result["answer"]).send()
