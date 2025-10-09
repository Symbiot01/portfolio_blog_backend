import os
import motor.motor_asyncio
from beanie import init_beanie
from app.models.user import User
from app.models.blog_post import BlogPost
from app.models.comment import Comment
from app.models.trip import Trip
from app.models.itinerary import ItineraryItem
from app.models.expense import Expense
from app.models.settlement import Settlement

async def initialize_database():
    """Initializes the Beanie ODM and connects to the database."""
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("DATABASE_URL"))
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
        ]
    )