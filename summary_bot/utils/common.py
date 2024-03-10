import datetime
import re
from functools import cache
from typing import Any, TypeVar

import loguru
from sqlalchemy import BinaryExpression
from sqlalchemy.orm import InstrumentedAttribute
from pydantic.json_schema import GetJsonSchemaHandler
from pydantic_core import core_schema


FilterType = TypeVar(
    "FilterType",
    list[str],
    list[tuple[InstrumentedAttribute, "ComparisonType", Any]],  # type: ignore
    list[BinaryExpression],
    BinaryExpression,
)


class EnumDescriptionMixin:

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ):
        schema = handler(core_schema)
        schema["description"] = ";\t".join(
            [f"`{vi.value}-{vi.name}`" for vi in list(cls)]
        )

        return schema


def snake_to_camel(snake_case_string: str) -> str:
    return "".join(
        word if not index else word.capitalize()
        for index, word in enumerate(snake_case_string.split("_"))
    )


REGULAR_COMP = re.compile(r"((?<=[a-z\d])[A-Z]|(?!^)[A-Z](?=[a-z]))")


def camel_to_snake(camel_string):
    return REGULAR_COMP.sub(r"_\1", camel_string).lower()


@cache
def convert_time(time_str: str) -> float:
    def parse_float(value):
        return float(value)

    def parse_humanreadable_suffixes(value):
        """<1h2m> or <1h{any_sep}2m>, allowed suffixes <w,d,h,m,s>"""
        units = {
            "w": datetime.timedelta(days=7),
            "d": datetime.timedelta(days=1),
            "h": datetime.timedelta(hours=1),
            "m": datetime.timedelta(minutes=1),
            "s": datetime.timedelta(seconds=1),
        }
        raw_parsed_dict = {
            u: v for v, u in (re.findall(r"(\d+)([wdhms])", value))
        }
        if not raw_parsed_dict:
            raise ValueError("incorrect pattern")
        return sum(
            (
                units[u].total_seconds() * int(v)
                for u, v in raw_parsed_dict.items()
            )
        )

    convertors = {
        "float": parse_float,
        "humanreadable_suffixes": parse_humanreadable_suffixes,
    }

    for convertor_name, convertor_func in convertors.items():
        try:
            converted_value = convertor_func(time_str)
            loguru.logger.debug(
                f'"{time_str}" convert with {convertor_name} '
                f"to {converted_value}"
            )
            return converted_value
        except ValueError:
            continue
    raise ValueError(f"Can't parse {time_str} value")


@cache
def utc_offset():
    return datetime.datetime.now() - datetime.datetime.utcnow()
