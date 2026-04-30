from fastapi import APIRouter, HTTPException, Response
import asyncio
import os
import logging
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger("Reaper.LibraryAPI")

@router.get("/library/test")
async def test_library_endpoint():
    """Test endpoint to verify the library API is working."""
    return JSONResponse(content={"status": "ok", "message": "Library API is running"})

# Calculate the web directory for file lookups - fixed path
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'web', 'Pages', 'library')

@router.get("/library/{doc_name}")
async def get_library_document(doc_name: str):
    """Get a library document by its name."""
    try:
        # Sanitize the document name to prevent directory traversal
        if ".." in doc_name or "/" in doc_name or "\\" in doc_name:
            logger.warning(f"Invalid document name attempted: {doc_name}")
            raise HTTPException(status_code=400, detail="Invalid document name.")

        # Map the display names to actual file names
        doc_name_mapping = {
            "FAFO Doctrine": "FAFO Doctrine",
            "Basic Building Guide": "Basic Building Guide", 
            "Beige Cycle Guide": "Beige Cycle Guide",
            "Weapon Efficiency Guide": "Weapon Efficiency Guide",
            "Snipe": "Snipe",
            "Pet Guide": "Pet Guide",
        }
        
        # Get the actual filename (replace underscores with spaces for consistency)
        actual_doc_name = doc_name.replace("_", " ")
        if actual_doc_name in doc_name_mapping:
            filename = doc_name_mapping[actual_doc_name]
        else:
            filename = actual_doc_name
            
        file_path = os.path.join(web_dir, f"{filename}.md")
        
        logger.info(f"Looking for document at: {file_path}")
        logger.info(f"Web directory: {web_dir}")
        logger.info(f"Document name: {doc_name} -> {filename}")

        if not os.path.exists(file_path):
            logger.warning(f"Document not found: {file_path}")
            logger.warning(f"Directory contents: {os.listdir(web_dir) if os.path.exists(web_dir) else 'Directory does not exist'}")
            raise HTTPException(status_code=404, detail=f"Document '{doc_name}' not found.")

        content = await asyncio.to_thread(lambda: open(file_path, "r", encoding="utf-8").read())

        logger.info(f"Serving document: {file_path} ({len(content)} characters)")
        return Response(content=content, media_type="text/markdown; charset=utf-8")

    except HTTPException as http_exc:
        # Re-raise HTTPException to let FastAPI handle it
        raise http_exc
    except Exception as e:
        logger.error(f"Error serving library document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error serving library document: {str(e)}")
