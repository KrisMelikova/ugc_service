from functools import lru_cache
from http import HTTPStatus

from bson.objectid import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.api.v1.schemas import Review, ReviewFromDB, ReviewIn
from src.core.logger import ugc_logger
from src.db.mongo import get_mongo_db


class ReviewService:
    """Service for interacting with Review"""

    def __init__(self, mongo_db: AsyncIOMotorDatabase):
        self.mongo_db = mongo_db
        self.collection_name = "reviews"

    async def get(self, page_number: int = 1, per_page: int = 50) -> list[ReviewFromDB]:
        """Get all reviews"""

        try:
            reviews = (
                self.mongo_db[self.collection_name]
                .find()
                .sort("_id")
                .skip((page_number - 1) * per_page)
                .limit(per_page)
            )
        except Exception as exc:
            ugc_logger.error(f"Error while getting reviews: {exc}")

            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Error while getting reviews",
            )

        reviews_list = await reviews.to_list(length=per_page)
        reviews_from_db = [ReviewFromDB(**review) for review in reviews_list]

        return reviews_from_db

    async def add(self, user_id: str, data: ReviewIn) -> ReviewFromDB:
        """Add review for movie"""

        review = Review(**data.model_dump(), user_id=user_id)
        film_id = review.film_id

        is_review_exist = await self.check_if_review_exist(film_id, user_id)
        if is_review_exist:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=f"Review by user {user_id} for movie {film_id} already exist",
            )

        review_data_for_db = ReviewFromDB(**review.model_dump()).model_dump()

        try:
            new_data = await self.mongo_db[self.collection_name].insert_one(
                review_data_for_db
            )
        except Exception as exc:
            ugc_logger.error(
                f"Error while adding review by {user_id} for movie {film_id}: {exc}"
            )

            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"Error while adding review by {user_id} for movie {film_id}",
            )

        return await self.mongo_db[self.collection_name].find_one(
            {"_id": new_data.inserted_id}
        )

    async def update(self, review_id: str, data: ReviewFromDB) -> ReviewFromDB:
        """Update review for movie"""

        review_data = jsonable_encoder(data)
        prep_review_data = {k: v for k, v in review_data.items()}

        is_review_exist = await self.mongo_db[self.collection_name].find_one(
            {"_id": ObjectId(review_id)},
        )
        if not is_review_exist:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f"Not found review {review_id} for update",
            )

        update_result = await self.mongo_db[self.collection_name].update_one(
            {"_id": ObjectId(review_id)},
            {"$set": prep_review_data},
        )

        if update_result.modified_count == 1:
            return await self.mongo_db[self.collection_name].find_one(
                {"_id": ObjectId(review_id)},
            )

    async def remove(self, review_id: str) -> None:
        """Delete review"""

        removed_review = await self.mongo_db[self.collection_name].delete_one(
            {"_id": ObjectId(review_id)}
        )

        if removed_review.deleted_count != 1:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f"Not found review {review_id} for deletion",
            )

    async def check_if_review_exist(self, movie_id, user_id):
        """Check if review exists"""

        return await self.mongo_db[self.collection_name].find_one(
            {"film_id": movie_id, "user_id": user_id},
        )


@lru_cache()
def get_review_service():
    return ReviewService(get_mongo_db())
