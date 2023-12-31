import datetime as dt
import logging
from types import TracebackType
from typing import AsyncGenerator, Type, Optional

import asyncpg
from typing_extensions import Self

from common.decorators import raise_on_error
from common.exceptions import PostgresConnectionError
from .datatypes import PersonRecord, FilmWorkRecord, InfoRecord
from .iextractor import BaseExtractor


class Extractor(BaseExtractor):
    BATCH_SIZE = 100

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._logger = logging.getLogger(__name__)

    async def __aenter__(self) -> Self:
        self._logger.debug("Connecting to %s...", self._dsn)
        self._connection: asyncpg.connection.Connection = await asyncpg.connect(self._dsn)
        self._logger.info("Connected to PostgreSQL successfully.")
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._logger.debug("Closing connection to PostgreSQL...")
        await self._connection.close()
        self._logger.info("Connection to PostgreSQL closed.")

    async def extract_records(self, newer_than: dt.datetime) -> AsyncGenerator[InfoRecord, None]:
        self._logger.info("Extracting records modified since '%s'...", newer_than)
        modified_persons = await self._extract_modified_persons(newer_than)
        modified_film_works = await self._extract_film_work_ids_by_related_person(modified_persons)
        async for records in self._extract_records_by_related_film_works(modified_film_works):
            self._logger.debug("Fetched %s records.", len(records))
            yield records

    @raise_on_error(PostgresConnectionError("Failed to extract persons from PostgreSQL"))
    async def _extract_modified_persons(self, newer_than: dt.datetime) -> list[PersonRecord]:
        statement = f"""
            SELECT id FROM content.person WHERE modified > '{newer_than}';
        """
        person_ids = await self._connection.fetch(statement)
        self._logger.debug("Found %s modified persons since '%s'.", len(person_ids), newer_than)
        return person_ids

    @raise_on_error(PostgresConnectionError("Failed to extract film works from PostgreSQL"))
    async def _extract_film_work_ids_by_related_person(self, persons: list[PersonRecord]) -> list[FilmWorkRecord]:
        persons = ", ".join([f"'{record['id']}'" for record in persons])
        statement = f"""
            SELECT fw.id
            FROM content.film_work AS fw
            LEFT JOIN content.person_film_work AS pfw ON pfw.film_work_id = fw.id
            WHERE pfw.person_id IN ({persons});
        """
        film_work_ids = await self._connection.fetch(statement)
        self._logger.debug("Found %s modified film works by related persons.", len(film_work_ids))
        return film_work_ids

    async def _extract_records_by_related_film_works(
        self,
        film_works: list[FilmWorkRecord],
    ) -> AsyncGenerator[InfoRecord, None]:
        film_works = ", ".join([f"'{record['id']}'" for record in film_works])
        statement = f"""
            SELECT
                fw.id AS film_work_id,
                fw.title AS film_work_title,
                fw.description AS film_work_description,
                fw.rating AS film_work_rating,
                fw.type AS film_work_type,
                pfw.role AS person_film_work_role,
                p.id AS person_id,
                p.full_name AS person_full_name,
                g.name AS genre_name
            FROM content.film_work AS fw
                LEFT JOIN content.person_film_work AS pfw ON pfw.film_work_id = fw.id
                LEFT JOIN content.person AS p ON p.id = pfw.person_id
                LEFT JOIN content.genre_film_work AS gfw ON gfw.film_work_id = fw.id
                LEFT JOIN content.genre AS g ON g.id = gfw.genre_id
            WHERE fw.id IN ({film_works});
        """
        async with self._connection.transaction():
            result = await self._connection.cursor(statement)
            while records := await result.fetch(self.BATCH_SIZE):
                yield records
