"""Open Notebook catalog and SurrealDB channel bindings."""

from .courses import ChannelRef, Subject, SubjectId
from .http import JsonHttp, ServiceError


class OpenNotebookSubjects:
    def __init__(self, http: JsonHttp):
        self._http = http

    def list_subjects(self) -> tuple[Subject, ...]:
        entries = self._http.request("GET", "/api/notebooks")
        if not isinstance(entries, list):
            raise ValueError("Open Notebook must return a notebook array.")
        subjects = tuple(self._parse_subject(entry) for entry in entries)
        if len({subject.id for subject in subjects}) != len(subjects):
            raise ValueError("Open Notebook returned duplicate notebook IDs.")
        return subjects

    @staticmethod
    def _parse_subject(entry: object) -> Subject:
        if not isinstance(entry, dict) or "id" not in entry or "name" not in entry:
            raise ValueError("Each notebook requires an id and name.")
        return Subject(SubjectId(entry["id"]), entry["name"])


class SurrealBindings:
    def __init__(self, http: JsonHttp):
        self._http = http

    def for_guild(self, guild_id: int) -> dict[int, SubjectId]:
        rows = self._query(
            "SELECT channel_id, notebook_id FROM queryfi_channel_binding "
            "WHERE guild_id = $guild_id ORDER BY channel_id;",
            {"guild_id": str(guild_id)},
        )
        return {int(row["channel_id"]): SubjectId(row["notebook_id"]) for row in rows}

    def bind(self, channel: ChannelRef, subject_id: SubjectId) -> None:
        # A deterministic record ID makes repeated bindings replace one record.
        rows = self._query(
            "UPSERT type::thing('queryfi_channel_binding', $binding_id) "
            "SET guild_id = $guild_id, channel_id = $channel_id, notebook_id = $notebook_id "
            "RETURN AFTER;",
            {"binding_id": f"{channel.guild_id}_{channel.channel_id}",
             "guild_id": str(channel.guild_id), "channel_id": str(channel.channel_id),
             "notebook_id": subject_id.value},
        )
        if len(rows) != 1 or rows[0].get("notebook_id") != subject_id.value:
            raise ServiceError("SurrealDB did not confirm the channel binding.")

    def _query(self, query: str, variables: dict[str, str]) -> list[dict]:
        response = self._http.request("POST", "/rpc", {
            "id": 1, "method": "query", "params": [query, variables],
        })
        if not isinstance(response, dict) or "error" in response:
            raise ServiceError("SurrealDB rejected the request; check database access.")
        results = response.get("result")
        if not isinstance(results, list) or len(results) != 1:
            raise ServiceError("SurrealDB returned an invalid query response.")
        statement = results[0]
        if not isinstance(statement, dict) or statement.get("status") != "OK":
            raise ServiceError("SurrealDB query failed; check database permissions and version.")
        rows = statement.get("result")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ServiceError("SurrealDB returned invalid records.")
        return rows
