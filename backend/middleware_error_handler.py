"""
Middleware for handling API errors consistently across the application
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors and return user-friendly messages
    """
    logger.error(f"Validation error on {request.url}: {exc.errors()}")
    
    errors = []
    for error in exc.errors():
        field = '.'.join(str(loc) for loc in error['loc'][1:])  # Skip 'body' or 'query'
        message = error['msg']
        errors.append(f"{field}: {message}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": " | ".join(errors) if len(errors) > 1 else errors[0] if errors else "Validation error"
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle HTTP exceptions and ensure consistent error format
    """
    logger.error(f"HTTP error on {request.url}: {exc.status_code} - {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)}
    )

async def generic_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected exceptions
    """
    logger.exception(f"Unexpected error on {request.url}: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please try again later."
        }
    )

def setup_error_handlers(app):
    """
    Register all error handlers with the FastAPI app
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

