import sqlite3

import pytest

from app.agent.state import ProjectDraftRepository


@pytest.fixture
def draft_repo(tmp_path):
    connection = sqlite3.connect(
        str(tmp_path / "orchestrator-state.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    repo = ProjectDraftRepository(connection=connection)
    try:
        yield repo
    finally:
        connection.close()
