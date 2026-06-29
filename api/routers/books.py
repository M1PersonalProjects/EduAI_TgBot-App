from typing import Optional, List
from fastapi import APIRouter
from database import db
from api.schemas.accounts import BookResponse

router = APIRouter(prefix="/api/books", tags=["Books"])

@router.get("/list", response_model=List[BookResponse])
async def get_books_list(class_level: Optional[int] = None, subject: Optional[str] = None):
    async with db.pool.acquire() as conn:
        query = """
            SELECT DISTINCT ON (class_level, subject, author) 
                   book_id, class_level, subject, author, chapter 
            FROM books_db 
            WHERE 1=1
        """
        params = []
        
        if class_level:
            params.append(class_level)
            query += f" AND class_level = ${len(params)}"
            
        if subject:
            params.append(subject)
            query += f" AND subject = ${len(params)}"
            
        books = await conn.fetch(query, *params)
        return books