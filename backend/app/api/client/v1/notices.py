from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.public.deps import require_aksk
from app.core.config import settings
from app.db.session import get_db
from app.schemas.client.notices import NoticeItem, NoticeListResponse
from app.schemas.response import ApiResponse

router = APIRouter()


COUNTRY_RULES = {
    "FRA": ("FR", "EU"),
    "BEL": ("BE", "EU"),
    "DEU": ("DE", "EU"),
    "NLD": ("NL", "EU"),
    "ITA": ("IT", "EU"),
    "ESP": ("ES", "EU"),
    "SGP": ("SG", "SG"),
}

COUNTRY_ALPHA2_TO_ALPHA3 = {
    alpha2: alpha3 for alpha3, (alpha2, _) in COUNTRY_RULES.items()
}


def resolve_country(country: str, data_region: str) -> tuple[str, str]:
    normalized_country = country.upper()
    normalized_region = data_region.upper()
    rule = COUNTRY_RULES.get(normalized_country)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported country",
        )

    country_alpha2, country_region = rule
    if country_region != normalized_region:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Country is not allowed in this data region",
        )
    return normalized_country, country_alpha2


@router.get("")
async def list_notices(
    country: Annotated[str, Query(min_length=3, max_length=3)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    _credential=Depends(require_aksk),
):
    country_alpha3, country_alpha2 = resolve_country(country, settings.DATA_REGION)
    offset = (page - 1) * per_page

    count_result = await db.execute(
        text(
            """
            SELECT count(*)
            FROM crawler_notices
            WHERE data_region = :data_region
              AND country_code = :country_code
            """
        ),
        {"data_region": settings.DATA_REGION.upper(), "country_code": country_alpha2},
    )
    total = int(count_result.scalar_one())

    rows_result = await db.execute(
        text(
            """
            SELECT id,
                   title,
                   description,
                   COALESCE(buyer_portal_url, notice_url) AS procurement_url,
                   notice_url,
                   country_code,
                   publication_date,
                   deadline,
                   updated_at
            FROM crawler_notices
            WHERE data_region = :data_region
              AND country_code = :country_code
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "data_region": settings.DATA_REGION.upper(),
            "country_code": country_alpha2,
            "limit": per_page,
            "offset": offset,
        },
    )

    items = []
    for row in rows_result.mappings():
        item = dict(row)
        item["id"] = str(item["id"])
        item["country_code"] = COUNTRY_ALPHA2_TO_ALPHA3.get(
            item["country_code"], country_alpha3
        )
        items.append(NoticeItem(**item))

    return ApiResponse.success(
        data=NoticeListResponse(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
        )
    )
