from fastapi import APIRouter, Depends

from app.api.client.deps import get_current_user
from app.models.user import User
from app.schemas.client.user import UserResponse
from app.schemas.response import ApiResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user profile."""
    return ApiResponse.success(data=UserResponse.model_validate(current_user))
