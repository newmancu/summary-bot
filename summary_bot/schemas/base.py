import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)
from pydantic._internal._model_construction import ModelMetaclass

from summary_bot.models.base import DEVICE_ID_TYPE  # noqa

# they rly hid it so deep for some reason in v2...


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DeviceFkSchemaMixin(OrmModel):
    device_id: DEVICE_ID_TYPE = Field(description="Идентификатор устройства")


class DeviceFkOrNoneSchemaMixin(OrmModel):
    device_id: DEVICE_ID_TYPE | None = Field(
        None, description="Идентификатор устройства"
    )


class SyncTimeMixin(OrmModel):
    sync_time: datetime.datetime | None = None
    is_actual: bool = False


class ForceAliasMixin(OrmModel):

    def model_dump(
        self: "BaseModel",
        *,
        mode: str = "python",
        include: (
            set[int] | set[str] | dict[int, Any] | dict[str, Any] | None
        ) = None,
        exclude: (
            set[int] | set[str] | dict[int, Any] | dict[str, Any] | None
        ) = None,
        by_alias: bool = True,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: bool = True,
    ) -> dict[str, Any]:
        return super().model_dump(
            mode=mode,
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            round_trip=round_trip,
            warnings=warnings,
        )


class ForcedOrmModel(ForceAliasMixin, OrmModel):
    pass


class DateTimeOrmModel(OrmModel):
    created_at: datetime.datetime | None = None
    last_modified: datetime.datetime | None = None


class CreatedTimeSchemaMixin(OrmModel):
    created_at: datetime.datetime = Field(
        description="Дата создания записи на сервере"
    )


class IntIdSchemaMixin(OrmModel):
    id: int = Field(description="Primary Key")


class UuidIdSchemaMixin(OrmModel):
    id: UUID = Field(description="Primary Key")


class StartStopSchemaBase(OrmModel):

    start_time: int | None = Field(
        None,
        description=(
            "Время, начиная с которого нужно пытаться совершить действие"
        ),
    )
    stop_time: int | None = Field(
        None,
        description=(
            "Время, после которого перестать пытаться соврешить действие"
        ),
    )


class StartStopSchemaMixin(StartStopSchemaBase):
    @field_validator("start_time", "stop_time", mode="before")
    @classmethod
    def start_stop_validator(
        cls, value: int | datetime.datetime
    ) -> datetime.datetime:
        try:
            match value:
                case datetime.datetime():
                    return int(value.timestamp())
                # case str():
                #     return datetime.datetime.strptime(
                #         value, "%Y-%m-%dT%z"
                #     ).timestamp()
                case _:
                    return value
        except Exception:
            raise ValueError(value)

    @field_serializer("start_time", "stop_time", when_used="json")
    @classmethod
    def start_stop_serializer(cls, value: int) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(value) if value else 0  # check


class StartStopToTimeStampMixin(StartStopSchemaBase):
    @field_serializer("start_time", "stop_time")
    @classmethod
    def to_proto_time(cls, value: datetime.datetime | None):
        return int(value.timestamp()) if value is not None else 0


class AllOptional(ModelMetaclass):
    """Add as metaclass for   (metaclass=AllOptional)"""

    def __new__(mcs, name, bases, namespaces, **kwargs):
        annotations = namespaces.get("__annotations__", {})
        for base in bases:
            annotations.update(base.__annotations__)
        for field in annotations:
            if not field.startswith("__"):
                annotations[field] = annotations[field] | None
                namespaces[field] = None
        namespaces["__annotations__"] = annotations
        return super().__new__(mcs, name, bases, namespaces, **kwargs)
