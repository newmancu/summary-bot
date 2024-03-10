from datetime import datetime
from pydantic import Field
from sqlalchemy.ext.asyncio.session import AsyncSession
from summary_bot.models.base import BoundDbModel
from summary_bot.schemas.base import OrmModel
from summary_bot.utils.common import FilterType

MIN_DATE_BOUND_HEADER = "x-min-date-from"
MAX_DATE_BOUND_HEADER = "x-max-date-till"


class BaseHeaderDate(OrmModel):
    x_max_date: datetime | None = Field(
        serialization_alias=MAX_DATE_BOUND_HEADER
    )
    x_min_date: datetime | None = Field(
        serialization_alias=MIN_DATE_BOUND_HEADER
    )

    @property
    def headers(self):
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


async def set_bounds_response(
    session: AsyncSession,
    model: type[BoundDbModel],
    addition_filters: FilterType | list[bool],
) -> None:
    query = model.date_bounds(addition_filters)
    boarders = (await session.execute(query)).first()
    # headers = BaseHeaderDate.model_validate(boarders).headers


BOUND_RESPOSE = {
    "200": {
        "headers": {
            MIN_DATE_BOUND_HEADER: {
                "description": "left datetime boarder",
                "schema": {"type": "integer"},
            },
            MAX_DATE_BOUND_HEADER: {
                "description": "right datetime boarder",
                "schema": {"type": "integer"},
            },
        }
    }
}

DATE_BOUND_RESPONSE = {
    "200": {
        "headers": {
            MIN_DATE_BOUND_HEADER: {
                "description": "left date boarder",
                "schema": {"type": "date"},
            },
            MAX_DATE_BOUND_HEADER: {
                "description": "right date boarder",
                "schema": {"type": "date"},
            },
        }
    }
}
