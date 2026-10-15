"""Embeds texts for the backend's KT indexer (ADR-053). Executed by the AI environment's Python
(INGESTION_PYTHON, which has google-genai) with the vector_embedding folder as the working directory,
so locally the AI engineer's .env supplies the same embedding settings her ingestion uses; in the
container the backend passes the deployment's Gemini settings instead. Not imported by the backend.

stdin: {"texts": [...]}. stdout: {"model": ..., "dimension": ..., "vectors": [[...], ...]}.
Exit 0 on success. On failure the last stderr line is "EMBEDDING_ERROR: <type>: <short message>".
"""

import json
import os
import sys


def main() -> int:
    try:
        try:
            from dotenv import find_dotenv, load_dotenv

            load_dotenv(find_dotenv(usecwd=True))  # her .env above the working directory; never overrides what the backend passed
        except ImportError:
            pass
        from google import genai
        from google.genai import types

        texts = json.load(sys.stdin)["texts"]
        model, dim = os.environ["GEMINI_EMBED_MODEL"], int(os.environ["GEMINI_EMBED_DIM"])
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))  # Vertex AI when GOOGLE_GENAI_USE_VERTEXAI is set
        vectors = []
        for t in texts:  # one text per request, as her ingestion does
            r = client.models.embed_content(model=model, contents=t, config=types.EmbedContentConfig(output_dimensionality=dim))
            v = r.embeddings[0].values if r.embeddings else None
            if not v or len(v) != dim:
                raise ValueError("the embedding is missing or has the wrong size")
            vectors.append(list(v))
        json.dump({"model": model, "dimension": dim, "vectors": vectors}, sys.stdout)
    except Exception as e:  # noqa: BLE001 - report any failure as a short summary
        print(f"EMBEDDING_ERROR: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
