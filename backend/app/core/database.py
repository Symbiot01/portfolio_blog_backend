import os
from beanie import init_beanie
from pymongo import AsyncMongoClient
from app.models.user import User
from app.models.blog_post import BlogPost
from app.models.comment import Comment
from app.models.trip import Trip
from app.models.itinerary import ItineraryItem
from app.models.expense import Expense
from app.models.settlement import Settlement
from app.models.trip_doc import TripDoc
from app.models.trip_audit import TripAuditEvent
from app.models.trip_edit_nonce import TripEditNonce

_client = None

async def initialize_database():
    """Initializes the Beanie ODM and connects to the database."""
    global _client
    _client = AsyncMongoClient(
        os.getenv("DATABASE_URL"),
        maxPoolSize=10,
        minPoolSize=2,
        maxIdleTimeMS=30000,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    db_name = os.getenv("DATABASE_NAME")
    
    await init_beanie(
        database=client.get_database(db_name),
        document_models=[
            User,
            BlogPost,
            Comment,
            Trip,
            ItineraryItem,
            Expense,
            Settlement,
            TripDoc,
            TripAuditEvent,
            TripEditNonce,
        ]
    )

def get_client():
    """Get the MongoDB client for cleanup."""
    return _client