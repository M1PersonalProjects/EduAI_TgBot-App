from typing import Optional, List
from fastapi import APIRouter
from database import db
from api.schemas.accounts import BookResponse

router = APIRouter(prefix="/api/books", tags=["Books"])

@router.get("/list", response_model=List[BookResponse])
async def get_books_list(class_level: Optional[int] = None, program: Optional[str] = None):
    async with db.pool.acquire() as conn:
        query = """
            SELECT book_id, book_class AS class_level, book_title AS title, book_author AS author, book_program
            FROM book
            WHERE 1=1
        """
        params = []

        if class_level:
            params.append(class_level)
            query += f" AND book_class = ${len(params)}"

        if program:
            params.append(program)
            query += f" AND book_program ILIKE ${len(params)}"

        rows = await conn.fetch(query, *params)
        
        books = []
        for r in rows:
            books.append(
                BookResponse(
                    book_id=r["book_id"],
                    class_level=r["class_level"],
                    subject=r["book_program"], 
                    author=r["author"],
                    chapter=r["title"]  
                )
            )
        return books


@router.get("/filters")
async def get_available_filters():
    async with db.pool.acquire() as conn:
        class_rows = await conn.fetch("SELECT DISTINCT book_class FROM book ORDER BY book_class")
        program_rows = await conn.fetch("SELECT DISTINCT book_program FROM book ORDER BY book_program")
        
    classes = [r["book_class"] for r in class_rows]
    programs = [r["book_program"] for r in program_rows]
            
    return {
        "classes": classes,
        "programs": programs
    }