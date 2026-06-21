from fastapi import APIRouter, HTTPException, Response
import asyncio
import os
import logging
from fastapi.responses import JSONResponse
import re

router = APIRouter()
logger = logging.getLogger("Reaper.DocumentationAPI")

# Calculate the docs directory - web/docs folder
# __file__ is at: web/api/documentation_api.py
# We want: web/docs
api_dir = os.path.dirname(os.path.abspath(__file__))  # web/api
web_dir = os.path.dirname(api_dir)  # web
docs_dir = os.path.join(web_dir, "docs")  # web/docs

# Log the docs directory on module load
logger.info(f"Documentation API initialized. Docs directory: {docs_dir}")
logger.info(f"Docs directory exists: {os.path.exists(docs_dir)}")

# Document mapping with metadata
DOCUMENTATION_FILES = {
    "README": {
        "title": "ReaperBot Overview",
        "file": "README.md",
        "icon": "fa-home",
        "description": "Main project overview and quick start guide"
    },
    "REAPER": {
        "title": "Reaper Discord Bot",
        "file": "REAPER.md",
        "icon": "fa-robot",
        "description": "Complete Discord bot documentation"
    },
    "HARVESTER": {
        "title": "PnWHarvester Service",
        "file": "HARVESTER.md",
        "icon": "fa-database",
        "description": "Data collection service documentation"
    },
    "WEBSITE": {
        "title": "Web Interface",
        "file": "WEBSITE.md",
        "icon": "fa-globe",
        "description": "Web interface and API documentation"
    },
    "LICENSE": {
        "title": "License",
        "file": "LICENSE.md",
        "icon": "fa-scale-balanced",
        "description": "MIT License, third-party attributions, and privacy information"
    }
}

@router.get("/list")
async def list_documents():
    """Get list of available documentation files."""
    try:
        docs_list = []
        for doc_id, doc_info in DOCUMENTATION_FILES.items():
            file_path = os.path.join(docs_dir, doc_info["file"])
            exists = os.path.exists(file_path)
            docs_list.append({
                "id": doc_id,
                "title": doc_info["title"],
                "icon": doc_info["icon"],
                "description": doc_info["description"],
                "available": exists,
                "path": file_path  # Include path for debugging
            })
        return JSONResponse(content={"documents": docs_list, "docs_dir": docs_dir})
    except Exception as e:
        logger.error(f"Error listing documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")

@router.get("/{doc_id}")
async def get_documentation(doc_id: str):
    """Get a documentation file by its ID."""
    try:
        # Validate document ID
        if doc_id not in DOCUMENTATION_FILES:
            logger.warning(f"Invalid document ID requested: {doc_id}")
            raise HTTPException(status_code=404, detail=f"Document not found. Valid IDs: {', '.join(DOCUMENTATION_FILES.keys())}")
        
        doc_info = DOCUMENTATION_FILES[doc_id]
        file_path = os.path.join(docs_dir, doc_info["file"])
        
        logger.info(f"Docs directory: {docs_dir}")
        logger.info(f"Looking for document at: {file_path}")
        logger.info(f"File exists: {os.path.exists(file_path)}")

        if not os.path.exists(file_path):
            logger.warning(f"Document file not found: {file_path}")
            # List files in docs_dir for debugging
            try:
                files_in_docs = os.listdir(docs_dir)
                logger.info(f"Files in docs directory: {files_in_docs}")
            except Exception as e:
                logger.error(f"Could not list docs directory: {e}")
            raise HTTPException(status_code=404, detail=f"Document file '{doc_info['file']}' not found at {file_path}")

        # Read the file content
        content = await asyncio.to_thread(lambda: open(file_path, "r", encoding="utf-8").read())

        # Process internal links to work with the web interface
        # Convert relative markdown links to use the documentation API
        # Pattern: [Link Text](FILE.md) or [Link Text](FILE.md#section)
        def replace_link(match):
            link_text = match.group(1)
            link_target = match.group(2)
            
            # Check if it's a markdown file link
            if link_target.endswith('.md') or '.md#' in link_target:
                # Extract the base filename without extension
                base_name = link_target.split('.md')[0].upper()
                section = ""
                if '#' in link_target:
                    section = link_target.split('#')[1]
                    base_name = link_target.split('.md#')[0].upper()
                
                # Check if this is one of our documentation files
                if base_name in DOCUMENTATION_FILES:
                    if section:
                        return f'[{link_text}](#doc-link:{base_name}#{section})'
                    else:
                        return f'[{link_text}](#doc-link:{base_name})'
            
            # Keep other links as-is
            return match.group(0)
        
        # Replace markdown links
        content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', replace_link, content)

        logger.info(f"Serving document: {file_path} ({len(content)} characters)")
        
        return Response(
            content=content, 
            media_type="text/markdown; charset=utf-8",
            headers={
                "X-Document-Title": doc_info["title"],
                "X-Document-Icon": doc_info["icon"]
            }
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error serving documentation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error serving documentation: {str(e)}")

@router.get("/search")
async def search_documentation(query: str):
    """Search across all documentation files."""
    try:
        if not query or len(query) < 2:
            raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
        
        results = []
        query_lower = query.lower()
        
        for doc_id, doc_info in DOCUMENTATION_FILES.items():
            file_path = os.path.join(docs_dir, doc_info["file"])
            
            if not os.path.exists(file_path):
                continue
            
            content = await asyncio.to_thread(lambda fp=file_path: open(fp, "r", encoding="utf-8").read())
            
            # Search for query in content
            lines = content.split('\n')
            matches = []
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Get context (line before and after)
                    context_start = max(0, i - 1)
                    context_end = min(len(lines), i + 2)
                    context = '\n'.join(lines[context_start:context_end])
                    
                    matches.append({
                        "line": i + 1,
                        "context": context[:200]  # Limit context length
                    })
                    
                    if len(matches) >= 5:  # Limit matches per document
                        break
            
            if matches:
                results.append({
                    "document": doc_id,
                    "title": doc_info["title"],
                    "icon": doc_info["icon"],
                    "matches": matches
                })
        
        return JSONResponse(content={"query": query, "results": results})
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error searching documentation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error searching documentation: {str(e)}")
