from abc import abstractmethod
import datetime
from typing import Any, Iterable
import uuid
from enum import IntEnum
from pydantic import BaseModel, ConfigDict

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    func,
    Integer,
    TypeDecorator,
    Select,
    select,
)
from sqlalchemy.ext.declarative import as_declarative
from sqlalchemy.orm import declared_attr, Mapped, mapped_column

from summary_bot.utils.common import FilterType, camel_to_snake

class_registry: dict = {}

MIN_DATE_SQL_LABEL = "x_min_date"
MAX_DATE_SQL_LABEL = "x_max_date"


@as_declarative(class_registry=class_registry)
class Base:
    @classmethod
    def table_prefix(cls) -> str:
        return "mats"

    @classmethod
    def get_table_name(cls, model_name: str):
        return f"{cls.table_prefix()}_{camel_to_snake(model_name)}"

    @classmethod
    def __generate_table_snake_name(cls):
        """StupidCAMelCase to stupid_ca_mel_case"""
        return camel_to_snake(cls.__name__)

    @declared_attr
    def __tablename__(cls) -> str:
        """this is a class method"""
        return cls.get_table_name(cls.__name__)

    @classmethod
    def filter_fields(cls) -> list[str]:
        return []

    @classmethod
    def custom_field_comparison(cls) -> dict[str, type]:
        return {}

    @classmethod
    def order_fields(cls) -> list[str]:
        raise NotImplementedError

    @classmethod
    def default_order_fields(cls) -> list[str]:
        raise NotImplementedError

    def as_dict(self, *exclude_fields: str) -> dict[str, Any]:
        exclude_fields = list(exclude_fields)
        exclude_fields.append("_sa_instance_state")
        return {
            name: value
            for name, value in self.__dict__.items()
            if name not in exclude_fields
        }

    def as_tuple(self, *exclude_fields: str) -> tuple:
        return tuple(self.as_dict(*exclude_fields).values())

    @classmethod
    def all_fields(cls):
        return {c.name for c in cls.__table__.columns}

    @classmethod
    def from_dict(cls, values: dict[str, any]):
        """Danger method! Values should be validated with model before call."""
        fields = cls.all_fields()
        instance = cls()
        for field, value in values.items():
            if field in fields:
                setattr(instance, field, value)
        return instance


class BigIDMixin:
    """Provides id"""

    # no required index=True cause primary_key make index automatically

    # is Identity() required?
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    @classmethod
    def order_fields(cls) -> list[str]:
        return ["id"]

    @classmethod
    def default_order_fields(cls) -> list[str]:
        return ["desc_id"]


class IDMMixin(BigIDMixin):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class DateCreatedMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now()
    )

    @classmethod
    def order_fields(cls) -> list[str]:
        return ["created_at"]

    @classmethod
    def default_order_fields(cls) -> list[str]:
        return ["desc_created_at"]


class DateMixin(DateCreatedMixin):
    last_modified: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    @classmethod
    def order_fields(cls) -> list[str]:
        return ["created_at", "last_modified"]


class BigIdCreatedDateBaseMixin(BigIDMixin, DateCreatedMixin):
    @classmethod
    def order_fields(cls) -> list[str]:
        return BigIDMixin.order_fields() + DateCreatedMixin.order_fields()

    @classmethod
    def default_order_fields(cls) -> list[str]:
        return ["desc_id"]


class BigIdDateBaseMixin(BigIDMixin, DateMixin):
    @classmethod
    def order_fields(cls) -> list[str]:
        return BigIDMixin.order_fields() + DateMixin.order_fields()

    @classmethod
    def default_order_fields(cls) -> list[str]:
        return ["desc_id"]


class IdDateCreatedBaseMixin(DateCreatedMixin, IDMMixin):
    @classmethod
    def order_fields(cls) -> list[str]:
        return DateCreatedMixin.order_fields() + IDMMixin.order_fields()


class IdDateBaseMixin(DateMixin, IDMMixin):
    @classmethod
    def order_fields(cls) -> list[str]:
        return DateMixin.order_fields() + IDMMixin.order_fields()


class UUIDDateCreatedMixin(UUIDMixin, DateCreatedMixin):
    pass


class UUIDDateBaseMixin(UUIDMixin, DateMixin):
    pass


class BoundDbModel:
    __abstract__ = True

    @classmethod
    @abstractmethod
    def bound_date_column(cls) -> Column:
        raise NotImplementedError()

    @classmethod
    def date_bounds(
        cls, eq_filters: FilterType | list[bool], **kwargs
    ) -> "Select":
        date_column = cls.bound_date_column()
        return select(
            func.min(date_column).label(MIN_DATE_SQL_LABEL),
            func.max(date_column).label(MAX_DATE_SQL_LABEL),
        ).filter(
            *eq_filters if isinstance(eq_filters, Iterable) else eq_filters
        )


def id_column(model_name_id: str) -> str:
    """jus a simple function that converts ModelName to model_name
    and join the result with a column name after dot in model_name_id"""

    model_name, *id_columns = model_name_id.split(".")
    if not id_columns or len(id_columns) > 1:
        raise ValueError(
            'Incorrect model_name_id value, required "ModelName.id"'
        )
    return ".".join([Base.get_table_name(model_name)] + id_columns)


#  custom column types


class IntEnumDecorator(type):
    @staticmethod
    def process_bind_param(obj, value: IntEnum, dialect):
        if value is not None:
            return value.value

    @staticmethod
    def process_result_value(obj, value: Integer, dialect, enumcls):
        if value is not None:
            return enumcls(value)

    def __new__(cls, clsname, superclasses, attributedict, enumcls):
        clsname = clsname.replace("Enum", "")
        process_result_value = (
            lambda obj, value, dialect: cls.process_result_value(
                obj, value, dialect, enumcls
            )
        )
        superclasses = (*superclasses, TypeDecorator)
        attributedict.update(
            impl=Integer,
            enumcls=enumcls,
            process_bind_param=cls.process_bind_param,
            process_result_value=process_result_value,
        )
        return type.__new__(cls, clsname, superclasses, attributedict)


class TMP(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    t: datetime.datetime


class UnixTimestamp(TypeDecorator):
    impl = Integer

    def process_bind_param(self, value: datetime.datetime, dialect):
        match value:
            case datetime.datetime():
                return value.timestamp()
            case str():

                return int(TMP(t=value).t.timestamp())
            case _:
                return value

    @property
    def python_type(self):
        return datetime.datetime  # TODO: Mb change to small int


class MyDateTime(TypeDecorator):
    impl = DateTime

    def process_bind_param(self, value, dialect):
        match value:
            case datetime.datetime():
                return value.replace(tzinfo=None)
            case str():
                return TMP(t=value).t
            case _:
                return value  # TODO: CHANGE

    @property
    def python_type(self):
        return datetime.datetime
