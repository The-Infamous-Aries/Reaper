import re
import asyncio
"""
README, License, and Dependencies API Endpoints
Provides documentation content for the about page.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import os
import logging
import sys

router = APIRouter()
logger = logging.getLogger("Reaper.DocsAPI")

# Calculate project root directory
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cache static doc files — read once, serve forever
_doc_cache: dict = {}

def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

async def _get_file(path: str) -> str:
    if path not in _doc_cache:
        _doc_cache[path] = await asyncio.to_thread(_read_file, path)
    return _doc_cache[path]

def convert_markdown_to_html(text):
    """Convert Discord markdown to HTML for web display."""

    def slugify(s):
        s = s.lower().strip()
        s = re.sub(r'[\s-]+', '-', s)
        s = re.sub(r'[^a-z0-9-]', '', s)
        return s

    # Generate IDs for headers
    def add_header_ids(match):
        level = len(match.group(1))
        title = match.group(2).strip()
        id = slugify(title)
        return f'<h{level} id="{id}">{title}</h{level}>'

    text = re.sub(r'^(#+)(.+)$', add_header_ids, text, flags=re.MULTILINE)

    # Update ToC links to match slugified IDs
    def update_toc_links(match):
        link_text = match.group(1)
        link_target = match.group(2)
        slug = slugify(link_target.replace('#', ''))
        return f'<a href="#{slug}">{link_text}</a>'

    text = re.sub(r'\[([^\]]+)\]\((#[^\)]+)\)', update_toc_links, text)

    # Convert bold text (**text**)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert horizontal rules (---)
    text = re.sub(r'^---+$', r'<hr>', text, flags=re.MULTILINE)
    
    # Convert numbered lists (1. 2. 3.)
    text = re.sub(r'^(\d+\.) (.+)$', r'<li>\2</li>', text, flags=re.MULTILINE)
    
    # Convert bullet points (* text)
    text = re.sub(r'^(\*|-) (.+)$', r'<li>\2</li>', text, flags=re.MULTILINE)
    
    # Wrap consecutive list items in <ol> or <ul> tags
    text = re.sub(r'(<li>.+<\/li>\s*)+', lambda m: '<ol>\n' + m.group(0) + '</ol>\n' if m.group(0).strip().startswith('<li>') else '<ul>\n' + m.group(0) + '</ul>\n', text)

    # Convert inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Convert code blocks (```code```)
    text = re.sub(r'```([a-z]*)\n([\s\S]*?)\n```', r'<pre><code class="language-\1">\2</code></pre>', text)
    
    # Convert general links [text](url)
    text = re.sub(r'\[([^\]]+)\]\((?!#)([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    
    # Convert line breaks to <br> tags for better formatting
    text = re.sub(r'\n', r'<br>', text)

    return text

@router.get("/readme")
async def get_readme():
    """Get README content."""
    try:
        readme_path = os.path.join(project_root, "README.md")
        if not os.path.exists(readme_path):
            logger.warning(f"README.md not found at {readme_path}")
            raise HTTPException(status_code=404, detail="README.md not found")
        
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_content = await _get_file(readme_path)
        
        html_content = convert_markdown_to_html(readme_content)
        logger.info("Successfully served README content")
        return JSONResponse(content={"content": html_content}, status_code=200)
        
    except Exception as e:
        logger.error(f"Error serving README: {e}")
        raise HTTPException(status_code=500, detail="Error serving README")

@router.get("/license")
async def get_license():
    """Get license content."""
    try:
        license_path = os.path.join(project_root, "LICENSE.txt")
        if not os.path.exists(license_path):
            logger.warning(f"LICENSE.txt not found at {license_path}")
            raise HTTPException(status_code=404, detail="LICENSE.txt not found")
        
        with open(license_path, "r", encoding="utf-8") as f:
            license_content = await _get_file(license_path)
        
        logger.info("Successfully served license content")
        return JSONResponse(content={"content": license_content}, status_code=200)
        
    except Exception as e:
        logger.error(f"Error serving license: {e}")
        raise HTTPException(status_code=500, detail="Error serving license")

@router.get("/dependencies")
async def get_dependencies():
    """Get requirements.txt content parsed by category."""
    try:
        requirements_path = os.path.join(project_root, "requirements.txt")
        if not os.path.exists(requirements_path):
            logger.warning(f"requirements.txt not found at {requirements_path}")
            raise HTTPException(status_code=404, detail="requirements.txt not found")
        
        with open(requirements_path, "r", encoding="utf-8") as f:
            requirements_content = await _get_file(requirements_path)
        
        # Parse requirements by category
        categories = {}
        current_category = "Uncategorized"
        lines = requirements_content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Check if it's the middle line of a category header (format: # Category Name)
            if (line.startswith('#') and 
                i > 0 and 
                i < len(lines) - 1 and
                lines[i-1].strip().startswith('#') and '===' in lines[i-1].strip() and
                lines[i+1].strip().startswith('#') and '===' in lines[i+1].strip()):
                
                # Extract category name (remove #)
                category_name = line.replace('#', '').strip()
                if category_name:
                    current_category = category_name
                    categories[current_category] = []
                continue
        
            # Skip pure comment lines (that are not category headers)
            if line.startswith('#'):
                continue
                
            # Skip lines that don't look like package specifications
            if not any(char in line for char in ['==', '>=', '<=', '>']):
                continue
                
            # Add package to current category
            if current_category not in categories:
                categories[current_category] = []
            categories[current_category].append(line)
        
        # If no categories were found, put everything in a default category
        if not categories:
            categories["Dependencies"] = [line for line in requirements_content.split('\n') 
                                          if line.strip() and not line.strip().startswith('#')]
        
        logger.info("Successfully served dependencies")
        return JSONResponse(content={"categories": categories}, status_code=200)
        
    except Exception as e:
        logger.error(f"Error serving dependencies: {e}")
        raise HTTPException(status_code=500, detail="Error serving dependencies")

@router.get("/package-json")
async def get_package_json():
    """Get package.json content parsed by dependencies and devDependencies."""
    try:
        import json
        package_json_path = os.path.join(project_root, "package.json")
        if not os.path.exists(package_json_path):
            logger.warning(f"package.json not found at {package_json_path}")
            raise HTTPException(status_code=404, detail="package.json not found")
        
        with open(package_json_path, "r", encoding="utf-8") as f:
            package_data = json.loads(await _get_file(package_json_path))
        
        # Extract dependencies sections
        categories = {}
        
        if "dependencies" in package_data:
            categories["Dependencies"] = [f"{pkg}@{version}" for pkg, version in package_data["dependencies"].items()]
        
        if "devDependencies" in package_data:
            categories["Dev Dependencies"] = [f"{pkg}@{version}" for pkg, version in package_data["devDependencies"].items()]
        
        if "peerDependencies" in package_data:
            categories["Peer Dependencies"] = [f"{pkg}@{version}" for pkg, version in package_data["peerDependencies"].items()]
        
        # Add basic package info
        package_info = []
        if "name" in package_data:
            package_info.append(f"Name: {package_data['name']}")
        if "version" in package_data:
            package_info.append(f"Version: {package_data['version']}")
        if "description" in package_data:
            package_info.append(f"Description: {package_data['description']}")
        if "license" in package_data:
            package_info.append(f"License: {package_data['license']}")
        
        if package_info:
            categories["Package Info"] = package_info
        
        logger.info("Successfully served package.json content")
        return JSONResponse(content={"categories": categories}, status_code=200)
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing package.json: {e}")
        raise HTTPException(status_code=500, detail="Error parsing package.json")
    except Exception as e:
        logger.error(f"Error serving package.json: {e}")
        raise HTTPException(status_code=500, detail="Error serving package.json")
