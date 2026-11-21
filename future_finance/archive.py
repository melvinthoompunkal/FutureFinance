"""Store immutable inputs and publish complete sessions through a local catalog."""

from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import duckdb
import pandas as pd

from .archive_inputs import ALIAS_FILE, prepare_export
from .inputs import BAR_FIELDS, BUNDLE_FILES, MEMBER_FIELDS, STRESS_FIELDS, Inputs, read_files, source_metadata
from .issuer_inputs import EARNINGS_FIELDS, FILING_FIELDS
from .market_calendar import WINDOWS, capture_cutoff, exchange
from .research_inputs import EXPORTS, RESEARCH_FILES, ResearchInputs, local_date, parse_research
from .scope import NEW_YORK

ARCHIVE_SCHEMA = 1
TABLE_FIELDS = {"bars": BAR_FIELDS, "members": MEMBER_FIELDS, "stress": STRESS_FIELDS,
                "filings": FILING_FIELDS, "earnings": EARNINGS_FIELDS, "stock_sectors": MEMBER_FIELDS}
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    session TEXT NOT NULL,
    window TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS runs_by_window ON runs (session, window, id);
CREATE TABLE IF NOT EXISTS publications (
    run_id INTEGER PRIMARY KEY REFERENCES runs (id),
    session TEXT NOT NULL,
    signature TEXT NOT NULL,
    manifest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS publications_by_session ON publications (session, run_id);
CREATE TABLE IF NOT EXISTS preopen_options (
    run_id INTEGER PRIMARY KEY REFERENCES runs (id),
    label TEXT NOT NULL,
    synthetic INTEGER NOT NULL,
    paths TEXT NOT NULL,
    raw_path TEXT NOT NULL
);
"""


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Archive:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.catalog = self.root / "catalog.sqlite3"

    @contextmanager
    def _connect(self, write: bool = False):
        uri = f"{self.catalog.as_uri()}?mode={'rwc' if write else 'ro'}"
        with closing(sqlite3.connect(uri, uri=True, timeout=15)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection

    def _start(self, session: date, window: str, now: datetime, scheduled: bool) -> int | None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._connect(write=True) as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            if scheduled and connection.execute(
                "SELECT 1 FROM runs WHERE session = ? AND window = ?", (session.isoformat(), window)
            ).fetchone():
                return None
            return connection.execute(
                "INSERT INTO runs (session, window, started_at, status) VALUES (?, ?, ?, 'started')",
                (session.isoformat(), window, now.isoformat()),
            ).lastrowid

    @staticmethod
    def _finish(connection: sqlite3.Connection, run_id: int, status: str, detail: str = "") -> dict:
        connection.execute("UPDATE runs SET finished_at = ?, status = ?, detail = ? WHERE id = ? AND status = 'started'",
                           (datetime.now(NEW_YORK).isoformat(), status, detail, run_id))
        return dict(connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

    def _record(self, run_id: int, status: str, detail: str = "") -> dict:
        with self._connect(write=True) as connection:
            return self._finish(connection, run_id, status, detail)

    def _store(self, path: Path, writer) -> str:
        target = self.root / path
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = target.with_name(f".{uuid4().hex}.tmp")
            try:
                writer(staging)
                # The staged file and its destination are on the same volume.
                try:
                    staging.replace(target)
                except PermissionError:
                    if not target.is_file():
                        raise
            finally:
                staging.unlink(missing_ok=True)
        return path.as_posix()

    def _raw(self, name: str, payload: bytes) -> str:
        digest = sha256(payload).hexdigest()
        path = Path("raw") / name / f"{digest}.gz"
        return self._store(path, lambda staging: staging.write_bytes(gzip.compress(payload, mtime=0)))

    def _partitions(self, connection, table: str, frame: pd.DataFrame) -> list[str]:
        if frame.empty:
            return []
        paths = []
        dates = frame["session"] if "session" in frame else frame["available_at"].dt.tz_convert(NEW_YORK)
        for month, rows in frame.groupby(dates.dt.strftime("%Y-%m")):
            canonical = rows.to_csv(index=False, lineterminator="\n").encode()
            digest = sha256(canonical).hexdigest()
            path = Path("normalized") / f"v{ARCHIVE_SCHEMA}" / table / f"month={month}" / f"{digest}.parquet"
            paths.append(self._store(path, lambda staging: connection.from_df(rows).write_parquet(
                str(staging), compression="zstd"
            )))
        return paths

    def _publish(self, run_id: int, session: date, manifest: dict) -> dict:
        normalized = {key: value for key, value in manifest.items() if key != "raw"}
        signature = sha256(_json(normalized).encode()).hexdigest()
        day = session.isoformat()
        with self._connect(write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            newer = connection.execute(
                """SELECT id FROM runs WHERE session = ? AND id > ?
                   AND status IN ('published', 'unchanged') LIMIT 1""", (day, run_id)
            ).fetchone()
            if newer:
                return self._finish(connection, run_id, "superseded", f"Later capture {newer['id']} completed.")
            latest = connection.execute(
                "SELECT run_id, signature FROM publications WHERE session = ? ORDER BY run_id DESC LIMIT 1", (day,)
            ).fetchone()
            if latest and latest["signature"] == signature:
                return self._finish(connection, run_id, "unchanged", f"Publication {latest['run_id']}.")
            connection.execute(
                "INSERT INTO publications (run_id, session, signature, manifest) VALUES (?, ?, ?, ?)",
                (run_id, day, signature, _json(manifest)),
            )
            return self._finish(connection, run_id, "published")

    def _capture_preopen(self, folder: Path, run_id: int, session: date, now: datetime) -> dict:
        files = read_files(folder, ("source.json", "options.csv"))
        if "options.csv" not in files:
            return self._record(run_id, "waiting", "Awaiting a permitted pre-open options export.")
        metadata = source_metadata(files)
        research = parse_research(files, metadata)
        source = research.sources["options"]
        if source["status"] != "loaded":
            return self._record(run_id, "failed", source["detail"])
        synthetic = metadata.get("synthetic", False)
        if not isinstance(synthetic, bool):
            raise ValueError("synthetic in source.json must be true or false.")
        opening = exchange().session_open(session)
        known = research.known("options", min(now, opening))
        rows = known if known.empty else known.loc[
            local_date(known["observed_at"]).eq(pd.Timestamp(session))
            & known["observed_at"].lt(opening) & known["oi_session"].notna()
        ]
        if rows.empty:
            return self._record(run_id, "waiting", "No dated open interest available before the opening bell.")
        with duckdb.connect(config={"threads": 2}) as connection:
            paths = self._partitions(connection, "preopen_options", rows)
        raw = self._raw("options.csv", files["options.csv"])
        with self._connect(write=True) as connection:
            connection.execute("INSERT INTO preopen_options VALUES (?, ?, ?, ?, ?)",
                               (run_id, source["label"], synthetic, _json(paths), raw))
            return self._finish(connection, run_id, "captured", f"{len(rows)} pre-open contract observations.")

    def _research_history(self, files: dict[str, bytes], session: date) -> dict[str, pd.DataFrame]:
        metadata = source_metadata(files)
        configured = metadata.get("research_sources")
        synthetic = metadata.get("synthetic", False)
        if not isinstance(configured, dict) or not isinstance(synthetic, bool):
            return {}
        histories = {}
        with self._connect() as catalog, duckdb.connect(config={"threads": 2}) as storage:
            for name in ("options", "estimates"):
                source = configured.get(name)
                if (not isinstance(source, dict) or source.get("permitted") is not True
                        or not isinstance(source.get("label"), str) or not source["label"].strip()):
                    continue
                label = source["label"].strip()
                latest = catalog.execute(
                    """SELECT json_extract(manifest, ?) AS paths FROM publications
                       WHERE session <= ? AND json_extract(manifest, '$.synthetic') = ?
                         AND json_extract(manifest, ?) = ? AND json_type(manifest, ?) = 'array'
                       ORDER BY session DESC, run_id DESC LIMIT 1""",
                    (f"$.tables.{name}", session.isoformat(), synthetic, f"$.sources.{name}.label",
                     label, f"$.tables.{name}"),
                ).fetchone()
                paths = json.loads(latest["paths"]) if latest else []
                if name == "options":
                    start = session - timedelta(days=380)
                    captures = catalog.execute(
                        """SELECT p.paths FROM preopen_options p JOIN runs r ON p.run_id = r.id
                           WHERE p.label = ? AND p.synthetic = ? AND r.session BETWEEN ? AND ? ORDER BY r.id""",
                        (label, synthetic, start.isoformat(), session.isoformat()),
                    ).fetchall()
                    paths.extend(path for row in captures for path in json.loads(row["paths"]))
                if paths:
                    files_to_read = [str(self.root / path) for path in dict.fromkeys(paths)]
                    frame = storage.read_parquet(files_to_read, hive_partitioning=False, union_by_name=True).df()
                    for column in frame.select_dtypes(include="datetimetz"):
                        frame[column] = frame[column].astype("datetime64[ns, UTC]")
                    histories[name] = frame.reindex(columns=EXPORTS[name].columns)
        return histories

    def capture(self, folder: Path, session: date, window: str, *,
                now: datetime | None = None, scheduled: bool = False) -> dict | None:
        now = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
        if window not in WINDOWS or not exchange().is_session(session):
            raise ValueError("Provide a capture window and a valid New York exchange session.")
        if window != "pre-open" and now < capture_cutoff(session):
            raise ValueError("The requested session has not reached its post-close cutoff.")
        run_id = self._start(session, window, now, scheduled)
        if run_id is None:
            return None
        try:
            if window == "pre-open":
                return self._capture_preopen(folder, run_id, session, now)
            files = read_files(folder, (*BUNDLE_FILES, ALIAS_FILE))
            if not files:
                return self._record(run_id, "waiting", "Awaiting a permitted price export.")
            prior = self._research_history(files, session) if "source.json" in files else None
            inputs, metadata = prepare_export(files, session, now, prior)
            with duckdb.connect(config={"threads": 2}) as connection:
                tables = {name: self._partitions(connection, name, getattr(inputs, name))
                          for name in TABLE_FIELDS
                          if name in ("bars", "members") or not getattr(inputs, name).empty}
                tables.update({name: self._partitions(connection, name, frame)
                               for name, frame in inputs.research.tables.items() if not frame.empty})
            approved = {f"{name}.csv" for name in inputs.research.tables
                        if "detail" not in inputs.research.sources[name]}
            if "headlines.csv" in approved:
                approved.add("headline_dictionary.csv")
            manifest = {
                "schema": ARCHIVE_SCHEMA,
                "session": session.isoformat(),
                "cutoff": capture_cutoff(session).isoformat(),
                "tables": tables,
                "raw": {name: self._raw(name, payload) for name, payload in files.items()
                        if name not in RESEARCH_FILES or name in approved},
                **({"headline_dictionary": inputs.research.dictionary} if inputs.research.dictionary else {}),
                **metadata,
            }
            for source in ("filings", "earnings", "options", "estimates"):
                manifest["sources"].setdefault(source, {"status": "not configured"})
            if not inputs.stress_sources:
                manifest["sources"]["volatility"] = {"status": "not configured"}
            return self._publish(run_id, session, manifest)
        except KeyboardInterrupt:
            self._record(run_id, "interrupted", "Capture stopped before publication.")
            raise
        except (OSError, ValueError, duckdb.Error, sqlite3.Error) as error:
            return self._record(run_id, "failed", str(error))

    def runs(self) -> list[dict]:
        if not self.catalog.is_file():
            return []
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY id")]

    def published_sessions(self) -> dict[date, int]:
        if not self.catalog.is_file():
            return {}
        with self._connect() as connection:
            return {date.fromisoformat(row["session"]): row["version"] for row in connection.execute(
                "SELECT session, MAX(run_id) AS version FROM publications GROUP BY session ORDER BY session DESC"
            )}

    def publication(self, version: int) -> dict:
        if self.catalog.is_file():
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT p.manifest, r.started_at, r.finished_at FROM publications p
                       JOIN runs r ON p.run_id = r.id WHERE p.run_id = ?""", (version,)
                ).fetchone()
                if row:
                    manifest = json.loads(row["manifest"])
                    if manifest["schema"] != ARCHIVE_SCHEMA:
                        raise ValueError(f"Unsupported archive schema {manifest['schema']}.")
                    return {**manifest, "version": version, "collected_at": row["started_at"],
                            "archive_published_at": row["finished_at"]}
        raise ValueError(f"Publication {version} does not exist.")

    def load(self, version: int) -> tuple[Inputs, dict]:
        manifest = self.publication(version)
        names = manifest["display_symbols"]
        tables = {}
        research = ResearchInputs(
            sources={name: manifest["sources"][name] for name in EXPORTS if name in manifest["sources"]},
            dictionary=manifest.get("headline_dictionary", {}),
        )
        with duckdb.connect(config={"threads": 2}) as connection:
            for name, fields in (TABLE_FIELDS | {name: export.columns for name, export in EXPORTS.items()}).items():
                paths = [str(self.root / path) for path in manifest["tables"].get(name, [])]
                if paths:
                    frame = connection.read_parquet(paths, hive_partitioning=False).df()
                    if "symbol" in fields:
                        frame["symbol"] = frame["security_id"].map(names).fillna(frame["symbol"])
                    target = research.tables if name in EXPORTS else tables
                    target[name] = frame.reindex(columns=fields)
                elif name not in EXPORTS:
                    tables[name] = pd.DataFrame(columns=fields)
        return Inputs(**tables, source=manifest["sources"]["prices"]["label"],
                      membership_source=manifest["sources"]["membership"]["label"],
                      demo=manifest["synthetic"], research=research, stress_sources={
                          name: source["label"] for name, source in manifest["sources"].get("stress", {}).items()
                      }, issuer_sources={name: manifest["sources"][name] for name in ("filings", "earnings")
                                         if name in manifest["sources"]}), manifest
