import json
from pathlib import Path

RAW_DIR = Path("data/raw")
OUT_PATH = Path("data/processed/chunks.jsonl")


def clean_text(text: str) -> str:
    # Normalize raw markdown/text files into paragraph blocks before chunking.
    text = text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines()]
    paragraphs = [line for line in lines if line]
    return "\n\n".join(paragraphs).strip()


def chunk_by_chars(text: str, chunk_size: int = 350, overlap: int = 60):
    # Create overlapping character chunks so retrieval can preserve nearby context.
    chunks = []
    n = len(text)

    step = max(1, chunk_size - overlap)

    start = 0
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start += step

    return chunks


def iter_raw_files(raw_dir: Path) -> list[Path]:
    # Limit the knowledge base builder to plain text and markdown source files.
    return sorted(list(raw_dir.glob("*.txt")) + list(raw_dir.glob("*.md")))


def main():
    # Read every raw document, extract optional source/title headers, and write chunk records as JSONL.
    files = iter_raw_files(RAW_DIR)
    if not files:
        raise RuntimeError("No raw files found in data/raw/. Please add .txt or .md files first.")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_chunks = 0
    chunk_id = 0

    with OUT_PATH.open("w", encoding="utf-8") as f_out:
        for fp in files:
            raw = fp.read_text(encoding="utf-8", errors="ignore")
            raw = clean_text(raw)

            lines = raw.splitlines()
            source_hint = ""
            title = fp.stem
            body_lines = [line for line in lines if line.strip()]

            # The first lines may carry lightweight metadata for source URLs and display titles.
            if body_lines and (body_lines[0].lower().startswith("source:") or "http" in body_lines[0].lower()):
                source_hint = body_lines.pop(0).strip()
            if body_lines and body_lines[0].lower().startswith("title:"):
                title = body_lines.pop(0).split(":", 1)[1].strip() or title

            body_text = "\n\n".join(body_lines).strip()
            if not body_text:
                continue

            chunks = chunk_by_chars(body_text, chunk_size=350, overlap=60)
            for idx, ch in enumerate(chunks):
                rec = {
                    "chunk_id": f"{title}-{idx}",
                    "title": title,
                    "source": source_hint,
                    "path": str(fp),
                    "text": ch,
                }
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total_chunks += 1
                chunk_id += 1

    print(f"Done. Wrote {total_chunks} chunks to {OUT_PATH}")


if __name__ == "__main__":
    main()
