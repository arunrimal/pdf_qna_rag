import asyncio
import os
import uuid
import tempfile
import shutil
import time
from typing import List, Optional, Dict, Any
from settings import settings
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from llama_index.core.query_engine import CitationQueryEngine
import json

# LlamaIndex Imports
from llama_index.core import (
    Settings as LlamaSettings,
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext
)
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore

# Pinecone Imports
from pinecone import Pinecone, ServerlessSpec

# PDF Processing
import fitz  # PyMuPDF

# Load Env Variables
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
INDEX_NAME = "pdf-rag"

if not GEMINI_API_KEY or not PINECONE_API_KEY:
    raise ValueError("Missing API Keys in .env file!")

# Initialize Pinecone Client (Global)
pc = Pinecone(api_key=PINECONE_API_KEY)
# Step 1 — delete old index
pc.delete_index(INDEX_NAME)

# Step 2 — recreate with correct dimension
pc.create_index(
    name=INDEX_NAME,
    dimension=3072,  # ← matches gemini-embedding-001
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region=PINECONE_ENVIRONMENT)
)

# Global Dictionary to store active sessions (Engine + Metadata)
# Structure: { "session_id": { "chat_engine": obj, "filename": str } }
active_sessions: Dict[str, Dict[str, Any]] = {}

# Initialize FastAPI
app = FastAPI(title=settings.app_config.app_name)

# Enable CORS (Allows React frontend on localhost:3000 to talk to this backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace "*" with specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# def initialize_engine(api_key: str, pdf_path: str):
def initialize_engine(pdf_path: str, session_id: str):
    """
    Creates a NEW chat engine for a specific user session.
    Uses Pinecone with 'namespace' to isolate data per session.
    Includes Chat Memory for conversation history.
    """
    # 1. Setup Models (Gemini)
    llm = GoogleGenAI(model="models/gemini-2.5-flash", api_key=GEMINI_API_KEY)
    embed_model = GoogleGenAIEmbedding(
        model_name="models/gemini-embedding-001", 
        api_key=GEMINI_API_KEY,
        output_dimensionality=768
        )
    
    # Apply settings locally for this index creation

    LlamaSettings.llm = llm
    LlamaSettings.embed_model = embed_model

    # 2. Ensure Pinecone Index Exists
    if INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(
            name=INDEX_NAME,
            dimension=768,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=PINECONE_ENVIRONMENT)
        )
    
    pinecone_index = pc.Index(INDEX_NAME)

    # 3. Create Vector Store with NAMESPACE = session_id
    # This ensures data for User A never mixes with User B
    vector_store = PineconeVectorStore(pinecone_index=pinecone_index, namespace=session_id)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 4. Load Documents
    documents = SimpleDirectoryReader(input_files=[pdf_path]).load_data()
    
    if not documents:
        raise ValueError("No text could be extracted from the PDF.")

    # 5. Create Index from Documents
    # We create a temporary index object just to build the engine
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context,
        show_progress=True
    )

    # 6. Create Chat Engine WITH MEMORY
    memory = ChatMemoryBuffer.from_defaults(token_limit=3900)
    
    chat_engine = index.as_chat_engine(
        chat_mode="context",
        memory=memory,
        system_prompt=(
            "You are a helpful assistant. Use the provided PDF context as the source of truth for facts (names, dates, skills). "
            "If the user asks for a summary or answer, stick strictly to the context. "
            "If the user asks you to generate something new (like a cover letter, email, or bio), use the facts from the context to inform your generation, but feel free to use your own knowledge for structure, tone, and formatting."
        ),
    )    

    # query_engine = CitationQueryEngine.from_defaults(
    #     index=index,
    #     memory=memory,
    #     system_prompt=(
    #         "You are a helpful assistant. Use the provided PDF context as the source of truth for facts (names, dates, skills). "
    #         "If the user asks for a summary or answer, stick strictly to the context. "
    #         "If the user asks you to generate something new (like a cover letter, email, or bio), use the facts from the context to inform your generation, but feel free to use your own knowledge for structure, tone, and formatting."
    #     ), 
    #     similarity_top_k=3,
    #     citation_chunk_size=512,
    # )
    
    # RETURN the engine instead of saving to a global variable
    return chat_engine
    # return query_engine


@app.post("/upload")
# async def upload_pdf(file: UploadFile = File(...), api_key: str = Form(...)):
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    # 1. Generate a Unique Session ID for this user (Once)
    session_id = str(uuid.uuid4())
    
    # 2. Save uploaded file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # --- NEW: Check Page Count Limit ---
        MAX_PAGES = 5  # Set your limit here
        
        doc = fitz.open(temp_file_path)
        page_count = len(doc)
        doc.close()  # Close the file handle immediately
        
        if page_count > MAX_PAGES:
            # Clean up temp file before raising error
            os.remove(temp_file_path)
            os.rmdir(temp_dir)
            raise HTTPException(
                status_code=400, 
                detail=f"PDF is too large! Maximum allowed is {MAX_PAGES} pages. Your file has {page_count} pages."
            )
        # -----------------------------------
        
        # 3. Initialize the engine (Get engine + collection name)
        # 3. Initialize Engine (Passing the SAME session_id)
        # chat_engine, collection_name = initialize_engine(api_key, temp_file_path)
        # Call without API key
        chat_engine = initialize_engine(temp_file_path, session_id)
        
        # 4. STORE in global dictionary
        active_sessions[session_id] = {
            "chat_engine": chat_engine,
            "filename": file.filename
        }
        
        # 5. Return the Session ID to the user
        # The frontend MUST save this ID and send it with every chat request
        return {
            "message": "PDF processed successfully!", 
            "session_id": session_id,
            "filename": file.filename,
            "pages": page_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    finally:
        # Cleanup temp file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


@app.post("/chat")
async def chat(session_id: str = Form(...), query: str = Form(...)):
    # 1. VALIDATION: Check if the session exists in our dictionary
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=404, 
            detail="Session not found. Please upload a PDF first to get a session_id."
        )
    
    # 2. RETRIEVAL: Get the specific data for this user
    session_data = active_sessions[session_id]
    engine = session_data["chat_engine"]
    
    # Optional: Update API key if the user sent a new one (flexibility)
    # But usually, the engine already has the key from the upload step.

    try:
        # 3. EXECUTION: Run the query on the SPECIFIC engine
        # This uses the memory stored inside this specific engine instance
        # response = await engine.chat(query)

        # WRAP THE SYNC CALL IN run_in_executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: engine.chat(query))


        
        # 4. FORMATTING: Extract sources for the frontend to display
        # sources = []
        # if response.sources:
        #     for source in response.sources:
        #         # Safely get metadata, defaulting to 'N/A' if missing
        #         sources.append({
        #             "text": source.node.text[:200] + "...", # Snippet preview
        #             "page": source.node.metadata.get("page_label", "N/A"),
        #             "file": source.node.metadata.get("file_name", "Unknown")
        #         })

        # # 5. RETURN: Send structured JSON back to the frontend
        # return {
        #     "answer": response.response,
        #     "sources": sources,
        #     "session_id": session_id # Echo back the ID for confirmation
        # }
        sources = []
        # # Check if sources exist and are iterable
        # if hasattr(response, 'sources') and response.sources:
        #     for source in response.sources:
        #         try:
        #             # Case 1: It's a standard NodeWithScore (has .node)
        #             if hasattr(source, 'node'):
        #                 node = source.node
        #             # Case 2: It might be a ToolOutput containing a node (newer versions)
        #             elif hasattr(source, 'content') and hasattr(source.content, 'node'):
        #                 node = source.content.node
        #             else:
        #                 # Skip unknown source types
        #                 continue
                    
        #             # Extract metadata safely
        #             sources.append({
        #                 "text": node.text[:200] + "...",
        #                 "page": node.metadata.get("page_label", "N/A"),
        #                 "file": node.metadata.get("file_name", "Unknown")
        #             })
        #         except Exception as src_err:
        #             # Log the specific source error but continue processing others
        #             print(f"Warning: Could not parse source: {src_err}")
        #             continue

        # ✅ Use source_nodes instead of sources
        if hasattr(response, 'source_nodes') and response.source_nodes:
            for node_with_score in response.source_nodes:
                try:
                    node = node_with_score.node  # Extract the actual node
                    sources.append({
                        "text": node.text[:200] + "...",
                        "page": node.metadata.get("page_label", "N/A"),
                        "file": node.metadata.get("file_name", "Unknown"),
                        "score": round(node_with_score.score, 4) if node_with_score.score else "N/A"
                    })
                except Exception as src_err:
                    print(f"Warning: Could not parse source: {src_err}")
                    continue


        # if hasattr(response, 'sources') and response.sources:
        #     for source in response.sources:
        #         try:
        #             raw = getattr(source, 'raw_output', None)
        #             if isinstance(raw, list):
        #                 for node_with_score in raw:
        #                     if hasattr(node_with_score, 'node'):
        #                         node = node_with_score.node
        #                         sources.append({
        #                             "text": node.text[:200] + "...",
        #                             "page": node.metadata.get("page_label", "N/A"),
        #                             "file": node.metadata.get("file_name", "Unknown"),
        #                             "score": round(node_with_score.score, 4) if node_with_score.score else "N/A"
        #                         })
        #         except Exception as src_err:
        #             print(f"Warning: Could not parse source: {src_err}")
        #             continue

        return {
            "answer": response.response,
            "sources": sources,
            "session_id": session_id
        }
    
    except Exception as e:
        # Handle any LLM or retrieval errors gracefully
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")
    

@app.post("/chat/stream")
async def chat_stream(session_id: str = Form(...), query: str = Form(...)):
    # 1. VALIDATION (Same as above)
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    session_data = active_sessions[session_id]
    chat_engine = session_data["chat_engine"]

    # 3. GENERATOR FUNCTION: This runs asynchronously
    async def event_generator():
        try:
            # Use stream_chat instead of chat
            # response = await engine.stream_chat(query)
            
            # WRAP THE SYNC CALL IN run_in_executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: chat_engine.stream_chat(query))
            
            # Iterate over tokens as they are generated
            for token in response.response_gen:
                # Format as Server-Sent Event (SSE)
                # The 'data: ' prefix is required by the SSE protocol
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"
            
            # After the text is done, send the sources as a final event
            sources = []
            # if response.sources:
            #     for source in response.sources:
            #         sources.append({
            #             "page": source.node.metadata.get("page_label", "N/A"),
            #             "snippet": source.node.text[:150]
            #         })

            for node_with_score in response.source_nodes:
                node = node_with_score.node
                sources.append({
                    "page": node.metadata.get("page_label", "N/A"),
                    "snippet": node.text[:150],
                    "score": round(node_with_score.score, 4) if node_with_score.score else "N/A"
                })

            
            final_data = json.dumps({"sources": sources, "done": True})
            yield f"data: {final_data}\n\n"
            
        except Exception as e:
            # Send error as an SSE event so the frontend can show it
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    # 4. RETURN STREAMING RESPONSE
    # media_type='text/event-stream' tells the browser "This is a live stream"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/sessions")
async def list_sessions():
    return {"active_sessions": list(active_sessions.keys())}

@app.post("/clear")
async def clear_session(session_id: str = Form(...)):
    # 1. VALIDATION: Check if the session exists
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=404, 
            detail="Session not found. Nothing to clear."
        )
    
    try:
        # 2. RETRIEVAL: Get the collection name before we delete the session info
        collection_name = active_sessions[session_id]["collection_name"]
        
        # Optional: Delete data from Pinecone namespace here if you want permanent cleanup
        index = pc.Index(INDEX_NAME)
        index.delete(delete_all=True, namespace=session_id)
        
        # 4. CLEANUP MEMORY (RAM)
        # Remove the engine and data from our dictionary
        del active_sessions[session_id]
        
        return {
            "message": "Session cleared successfully.",
            "details": f"Deleted collection '{collection_name}' and freed memory."
        }
    
    except Exception as e:
        # If deletion fails, we still try to remove from memory to prevent corruption
        if session_id in active_sessions:
            del active_sessions[session_id]
            
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to clean up resources: {str(e)}"
        )
    
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting {settings.app_config.app_name}...")
    uvicorn.run(app, host="0.0.0.0", port=8000)