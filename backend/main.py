import asyncio
import os
import uuid
import tempfile
import shutil
import time
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from settings import settings
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import aiosqlite

# LlamaIndex Imports
from llama_index.core import (
    Settings as LlamaSettings,
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext
)
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage, MessageRole
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
DB_PATH = "sessions.db"

if not GEMINI_API_KEY or not PINECONE_API_KEY:
    raise ValueError("Missing API Keys in .env file!")

# Initialize Pinecone Client (Global)
pc = Pinecone(api_key=PINECONE_API_KEY)

# Create index only if it doesn't exist (avoids wiping data on every redeploy)
existing_indexes = [i.name for i in pc.list_indexes()]
if INDEX_NAME not in existing_indexes:
    pc.create_index(
        name=INDEX_NAME,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region=PINECONE_ENVIRONMENT)
    )
    # Wait for index to be ready before accepting requests
    while not pc.describe_index(INDEX_NAME).status['ready']:
        time.sleep(1)

# Global Dictionary to store active sessions (Engine + Metadata)
# Structure: { "session_id": { "chat_engine": obj, "filename": str } }
active_sessions: Dict[str, Dict[str, Any]] = {}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


# Initialize FastAPI
app = FastAPI(title=settings.app_config.app_name, lifespan=lifespan)

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
        # output_dimensionality=768
        output_dimensionality=3072
        )
    
    # Apply settings locally for this index creation

    LlamaSettings.llm = llm
    LlamaSettings.embed_model = embed_model

    pinecone_index = pc.Index(INDEX_NAME)

    # 3. Create Vector Store with NAMESPACE = session_id
    # This ensures data for User A never mixes with User B
    vector_store = PineconeVectorStore(pinecone_index=pinecone_index, namespace=session_id)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 4. Load Documents
    documents = SimpleDirectoryReader(input_files=[pdf_path]).load_data()

    # # DEBUG: inspect extracted text
    # for i, doc in enumerate(documents):
    #     print(f"\n--- Document {i} ---")
    #     print(f"Metadata: {doc.metadata}")
    #     print(f"Text preview: {doc.text[:500]}")

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
    
    return chat_engine


def rebuild_engine(session_id: str):
    """Rebuild chat engine from existing Pinecone namespace — no PDF needed."""
    llm = GoogleGenAI(model="models/gemini-2.5-flash", api_key=GEMINI_API_KEY)
    embed_model = GoogleGenAIEmbedding(
        model_name="models/gemini-embedding-001",
        api_key=GEMINI_API_KEY,
        output_dimensionality=3072
    )
    LlamaSettings.llm = llm
    LlamaSettings.embed_model = embed_model

    pinecone_index = pc.Index(INDEX_NAME)
    vector_store = PineconeVectorStore(pinecone_index=pinecone_index, namespace=session_id)

    index = VectorStoreIndex.from_vector_store(vector_store)
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
    return chat_engine


async def get_or_rebuild_session(session_id: str) -> Dict[str, Any]:
    """Return session from RAM. If missing, rebuild from SQLite + Pinecone."""
    if session_id in active_sessions:
        return active_sessions[session_id]

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT filename FROM sessions WHERE session_id = ?", (session_id,))
        row = await cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a PDF first.")

    loop = asyncio.get_event_loop()
    chat_engine = await loop.run_in_executor(None, lambda: rebuild_engine(session_id))

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        saved_messages = await cursor.fetchall()

    for role, content in saved_messages:
        msg_role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
        chat_engine.memory.put(ChatMessage(role=msg_role, content=content))

    session_data = {"chat_engine": chat_engine, "filename": row[0]}
    active_sessions[session_id] = session_data
    return session_data


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
        
        # 4. STORE in RAM and SQLite
        active_sessions[session_id] = {
            "chat_engine": chat_engine,
            "filename": file.filename
        }
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO sessions (session_id, filename) VALUES (?, ?)",
                (session_id, file.filename)
            )
            await db.commit()

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
        sources = []
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

        # # 5. RETURN: Send structured JSON back to the frontend
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
    session_data = await get_or_rebuild_session(session_id)
    chat_engine = session_data["chat_engine"]

    async def event_generator():
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: chat_engine.stream_chat(query))

            full_response = ""
            for token in response.response_gen:
                full_response += token
                data = json.dumps({"token": token})
                yield f"data: {data}\n\n"

            # Save user + assistant messages to SQLite
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "user", query)
                )
                await db.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "assistant", full_response)
                )
                await db.commit()

            sources = []
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
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    # 4. RETURN STREAMING RESPONSE
    # media_type='text/event-stream' tells the browser "This is a live stream"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT filename FROM sessions WHERE session_id = ?", (session_id,))
        session = await cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        rows = await cursor.fetchall()

    messages = [{"role": row[0], "content": row[1]} for row in rows]
    return {"filename": session[0], "messages": messages}


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
        # Delete vectors from Pinecone namespace for this session
        index = pc.Index(INDEX_NAME)
        index.delete(delete_all=True, namespace=session_id)

        # Free memory
        del active_sessions[session_id]

        return {
            "message": "Session cleared successfully.",
            "details": f"Deleted namespace '{session_id}' and freed memory."
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