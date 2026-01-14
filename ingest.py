import os
import sys
import shutil
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader, UnstructuredExcelLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import LanceDB

# 1. Load Documents
def load_docs(directory):
    loaders = {
        ".pdf": PyPDFLoader,
        ".txt": TextLoader,
        ".md": TextLoader,
        ".xlsx": UnstructuredExcelLoader,
    }
    documents = []
    print(f"Scanning directory: {directory}")
    for root, _, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in loaders:
                file_path = os.path.join(root, file)
                print(f"Loading: {file_path}")
                try:
                    loader = loaders[ext](file_path)
                    documents.extend(loader.load())
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
    return documents

# 2. Split Text (Semantic Chunking)
docs_dir = "/Users/swarnabha.saha/Library/CloudStorage/OneDrive-RelianceCorporateITParkLimited/Personal/Personal RAG/Docs"
if not os.path.exists(docs_dir):
    print(f"Error: Directory not found: {docs_dir}")
    sys.exit(1)

docs = load_docs(docs_dir)

if not docs:
    print("No documents found.")
    sys.exit(0)

print(f"Loaded {len(docs)} documents.")

print("Initializing embeddings for Semantic Chunking...")
# Semantic Chunker needs embeddings to decide where to split
embeddings = OllamaEmbeddings(model="nomic-embed-text")

from langchain_experimental.text_splitter import SemanticChunker
text_splitter = SemanticChunker(embeddings, breakpoint_threshold_type="percentile")

print("Splitting documents (this may take a while)...")
splits = text_splitter.split_documents(docs)
print(f"Split into {len(splits)} chunks.")

# 3. Vectorize & Store
print("Initializing embeddings and vector store...")
embeddings = OllamaEmbeddings(model="nomic-embed-text")
if os.path.exists("./lancedb_data"):
    shutil.rmtree("./lancedb_data")

vector_store = LanceDB.from_documents(splits, embeddings, uri="./lancedb_data")
print("✅ Ingestion Complete. Data stored locally.")
