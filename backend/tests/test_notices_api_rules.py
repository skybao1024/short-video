import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.client.v1.notices import list_notices, resolve_country
from app.schemas.client.notices import NoticeListResponse


def test_resolve_country_accepts_alpha3_for_region() -> None:
    assert resolve_country("DEU", "EU") == ("DEU", "DE")
    assert resolve_country("sgp", "SG") == ("SGP", "SG")


def test_resolve_country_rejects_alpha2() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_country("DE", "EU")

    assert exc_info.value.status_code == 400


def test_resolve_country_rejects_cross_region_with_403() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_country("SGP", "EU")

    assert exc_info.value.status_code == 403


def test_notice_list_response_caps_per_page_at_100() -> None:
    with pytest.raises(ValidationError):
        NoticeListResponse(items=[], page=1, per_page=101, total=0)


class _CountResult:
    def scalar_one(self) -> int:
        return 1


class _RowsResult:
    def mappings(self):
        return [
            {
                "id": 123456789,
                "title": "Notice title",
                "description": "Notice description",
                "procurement_url": "https://buyer.example/tender/1",
                "notice_url": "https://official.example/notice/1",
                "country_code": "DE",
                "publication_date": None,
                "deadline": None,
                "updated_at": None,
            }
        ]


class _FakeDb:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if len(self.calls) == 1:
            return _CountResult()
        return _RowsResult()


@pytest.mark.asyncio
async def test_list_notices_returns_public_contract() -> None:
    db = _FakeDb()

    response = await list_notices(
        country="DEU",
        page=1,
        per_page=20,
        db=db,
        _credential=object(),
    )

    assert response.status_code == 200
    assert response.body
    assert b'"total":1' in response.body
    assert b'"id":"123456789"' in response.body
    assert b'"country_code":"DEU"' in response.body
    assert b'"procurement_url":"https://buyer.example/tender/1"' in response.body
    assert db.calls[0][1] == {"data_region": "EU", "country_code": "DE"}
