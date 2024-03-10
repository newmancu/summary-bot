from collections.abc import Iterable
from functools import wraps
from typing import Any, TypeVar, Generic, TypeAlias, Callable, Awaitable

import loguru
from pydantic import BaseModel
from sqlalchemy import select, delete, update, func
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import OperatorExpression, UnaryExpression

from summary_bot.config import get_settings, Settings
from summary_bot.models import Base


ModelType = TypeVar("ModelType", bound=Base)
GetSchemaType = TypeVar("GetSchemaType", bound=BaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)


CRUDBaseCommonMethodType: TypeAlias = (
    Callable[
        [AsyncSession, dict[str, Any], int, int], Awaitable[list[ModelType]]
    ]
    | Callable[[AsyncSession, dict[str, Any]], Awaitable[ModelType] | None]
    | Callable[[AsyncSession, dict[str, Any], dict[str, Any], bool], None]
)


class NoResultFoundEx(Exception):
    pass


def map_to_schema_result(func) -> ():
    @wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        self: CRUDBase = args[0]

        # just a crazy hack for grabbing a generic class
        get_schema: GetSchemaType = self.__orig_bases__[0].__args__[1]

        if isinstance(result, Iterable):
            return [get_schema.model_validate(res) for res in result]
        return get_schema.model_validate(result)

    return wrapper


UpdateFilter: TypeAlias = (
    dict[str, Any] | list[OperatorExpression] | OperatorExpression
)


class CRUDBase(Generic[ModelType, GetSchemaType, CreateSchemaType]):
    def __init__(self, settings: Settings = None):
        """
        CRUD object with default methods to
            Create, Read, Update, Delete (CRUD).
        **Parameters**
        * `model`: A SQLAlchemy model class
        * `settings`: Settings dependency injection, get default sys if None
        """

        self._settings = settings or get_settings()

        base = self.__orig_bases__[0]
        model, get_schema, create_schema = base.__args__[:3]
        self._model: ModelType = model
        self._get_schema: GetSchemaType = get_schema
        self._create_schema: CreateSchemaType = create_schema

    @property
    def model(self):
        return self._model

    @property
    def get_schema(self):
        return self._get_schema

    @property
    def create_schema(self):
        return self._create_schema

    def _generate_where_cause(self, filter_dict: dict[str, Any] | None = None):
        filter_dict = filter_dict or {}
        return [
            getattr(self._model, field) == value
            for field, value in filter_dict.items()
        ]

    @property
    def _select_model(self) -> Select | None:
        """can be used for config options with inload"""
        return select(self._model)

    @property
    def _has_custom_base(self):
        return self._select_model != select(self._model)

    def _resolve_filter(
        self, filter_: UpdateFilter
    ) -> list[OperatorExpression]:
        if isinstance(filter_, dict):
            filter_ = self._generate_where_cause(filter_)

        if not isinstance(filter_, Iterable):
            filter_ = [filter_]
        return filter_

    def _resolve_operator_expressions(
        self,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> list[OperatorExpression]:
        if operator_expressions is not None:
            operator_expressions = self._resolve_filter(operator_expressions)
        if filter_dict:
            operator_expressions = (
                operator_expressions or []
            ) + self._resolve_filter(filter_dict)

        return operator_expressions or ()

    async def get_multi_raw(
        self,
        session: AsyncSession,
        offset: int = 0,
        limit: int | None = None,
        order_by: UnaryExpression | None = None,
        operator_expressions: list[OperatorExpression] | None = None,
        scalars: bool = True,
        unique: bool = False,
        **filter_dict: ...,
    ) -> list[ModelType]:
        stmt = self._select_model.where(
            *self._resolve_operator_expressions(
                operator_expressions, **filter_dict
            )
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await session.execute(stmt)
        if unique:
            result = result.unique()
        if scalars:
            result = result.scalars()
        return result.all()

    async def get_count(
        self,
        session: AsyncSession,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> int:
        stmt = select(func.count()).where(
            *self._resolve_operator_expressions(
                operator_expressions, **filter_dict
            )
        )
        return (await session.execute(stmt)).scalar()

    @map_to_schema_result
    async def get_multi(
        self,
        session: AsyncSession,
        offset: int = 0,
        limit: int | None = None,
        order_by: UnaryExpression | None = None,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> list[GetSchemaType]:
        return await self.get_multi_raw(
            session=session,
            offset=offset,
            limit=limit,
            order_by=order_by,
            operator_expressions=operator_expressions,
            **filter_dict,
        )

    async def get_one_raw(
        self,
        session: AsyncSession,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> ModelType:
        stmt = self._select_model.where(
            *self._resolve_operator_expressions(
                operator_expressions, **filter_dict
            )
        )
        return (await session.execute(stmt)).scalars().one()

    @map_to_schema_result
    async def get_one(
        self,
        session: AsyncSession,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> GetSchemaType:
        return await self.get_one_raw(
            session, operator_expressions, **filter_dict
        )

    @staticmethod
    async def raw_add(
        session: AsyncSession, models: list[ModelType], commit=False
    ) -> list[ModelType]:
        session.add_all(models)
        if not commit:
            await session.flush(models)
            return models
        await session.commit()
        for model in models:
            await session.refresh(model)
        return models

    def _get_by_pk_expression(self, db_obj: ModelType):
        pk_name = getattr(db_obj, "pk_name", "id")
        pk_column = getattr(self.model, pk_name)
        pk_value = getattr(db_obj, pk_name)
        return [pk_column == pk_value]

    async def create(
        self, session: AsyncSession, *, obj_in: dict | CreateSchemaType
    ) -> ModelType:
        obj_in_data = obj_in
        if isinstance(obj_in_data, BaseModel):
            obj_in_data = obj_in.model_dump_json(
                exclude_unset=True, exclude_none=True
            )
        db_obj = self._model(**obj_in_data)  # type: ignore
        session.add(db_obj)
        await session.flush([db_obj])
        if not self._has_custom_base:
            return db_obj

        return await self.get_one_raw(
            session, operator_expressions=self._get_by_pk_expression(db_obj)
        )

    @map_to_schema_result
    async def create_with_commit(
        self, session: AsyncSession, *, obj_in: dict | CreateSchemaType
    ) -> GetSchemaType:
        db_obj = await self.create(session, obj_in=obj_in)
        await session.commit()
        await session.refresh(db_obj)
        if not self._has_custom_base:
            return db_obj
        res = await self.get_one_raw(
            session, operator_expressions=self._get_by_pk_expression(db_obj)
        )
        return res

    async def update(
        self,
        session: AsyncSession,
        *,
        update_filter: UpdateFilter,
        update_values: dict[str, Any],
        is_patch=True,
    ) -> int:
        """If is_patch = True - update only not nullable fields
        in other case set possible null values"""

        if is_patch:
            update_values = {
                k: v for k, v in update_values.items() if v is not None
            }
        operator_expressions = self._resolve_filter(update_filter)
        update_stmt = (
            update(self._model)
            .where(*operator_expressions)
            .values(**update_values)
        )
        result: CursorResult = await session.execute(update_stmt)
        return result.rowcount

    async def upsert_an_obj(
        self,
        session,
        filter_fields: list[str],
        obj_in: dict | CreateSchemaType,
    ) -> ModelType:
        if isinstance(obj_in, BaseModel):
            obj_in = obj_in.model_dump(exclude_none=True)
        filter_dict = {k: v for k, v in obj_in.items() if k in filter_fields}
        if not filter_dict:
            loguru.logger.warning("Got empty filter dict - force insert")
            return await self.create(session, obj_in=obj_in)
        else:
            try:
                exist_model = await self.get_one_raw(session, **filter_dict)
                for field, value in obj_in.items():
                    setattr(exist_model, field, value)
                await session.flush([exist_model])
                return exist_model
            except NoResultFound:
                return await self.create(session, obj_in=obj_in)

    async def get_or_create(
        self,
        session,
        filter_fields: list[str],
        obj_in: dict | CreateSchemaType,
    ) -> ModelType:
        if isinstance(obj_in, BaseModel):
            obj_in = obj_in.model_dump(exclude_none=True)
        filter_dict = {k: v for k, v in obj_in.items() if k in filter_fields}
        if not filter_dict:
            loguru.logger.warning("Got empty filter dict - ERROR")
            raise ValueError(
                f"Got empty filter dict in CRUD={self.__class__.__name__}"
            )
        try:
            return await self.get_one_raw(session, **filter_dict)
        except NoResultFound:
            return await self.create(session, obj_in=obj_in)

    async def bump_last_modified(
        self, session: AsyncSession, *, row_filter
    ) -> int:
        return await self.update(
            session, update_filter=row_filter, update_values={}
        )

    async def delete(
        self,
        session: AsyncSession,
        operator_expressions: list[OperatorExpression] | None = None,
        **filter_dict: ...,
    ) -> int:
        stmt = delete(self._model)
        if operator_expressions is not None:
            operator_expressions = self._resolve_filter(operator_expressions)
            stmt = stmt.where(*operator_expressions)
        if filter_dict:
            operator_expressions = self._resolve_filter(filter_dict)
            stmt = stmt.where(*operator_expressions)

        result: CursorResult = await session.execute(stmt)
        await session.flush()
        return result.rowcount
