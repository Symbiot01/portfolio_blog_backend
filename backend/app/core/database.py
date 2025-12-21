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

async def initialize_database():
    """Initializes the Beanie ODM and connects to the database."""
    # Beanie v2 uses PyMongo's native async client (NOT Motor).
    # Mixing Motor with Beanie v2 breaks link fetching (e.g. fetch_links=True) at runtime.
    client = AsyncMongoClient(os.getenv("DATABASE_URL"))
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