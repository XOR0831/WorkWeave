"""Runs the AI engineer's ingestion for one approved source version. Executed by HER Python
environment (INGESTION_PYTHON) with her vector_embedding folder as the working directory, so her
own .env supplies the Gemini embedding settings; the backend passes only the database URL and the
job's IDs (environment, never argv). Not imported by the backend.

Exit 0 on success. On failure the last stderr line is "INGESTION_ERROR: <type>: <short message>";
the backend keeps only that summary (no document content).
"""

import json
import os
import sys


def main() -> int:
    job = json.loads(os.environ["WORKWEAVE_INGEST"])
    sys.path.insert(0, os.getcwd())
    try:
        import database  # her module

        database.configure(os.environ["WORKWEAVE_DATABASE_URL"])
        from ingestion import Document  # her module (no work on import since the approved diff)

        Document(job["document_code"], job["curriculum_id"], job["workspace_id"], save_json=False).ingest()
    except Exception as e:  # noqa: BLE001 - report any failure as a short summary
        print(f"INGESTION_ERROR: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
