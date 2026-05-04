import subprocess
import sys
from pathlib import Path

# Allow the build helper to import project modules when run directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Run one build step at a time so a failed preprocessing, embedding, or indexing command stops the pipeline clearly.
def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")


# Build the local knowledge base artifacts from raw documents through FAISS index output.
def main():
    raw_dir = Path("data/raw")
    if not raw_dir.exists() or not any(raw_dir.iterdir()):
        raise RuntimeError("data/raw is empty. Please add raw .txt/.md files first.")

    run([sys.executable, "scripts/preprocess.py"])
    run([sys.executable, "scripts/embed_corpus.py"])
    run([sys.executable, "scripts/build_index.py"])

    print("\nKnowledge base build complete.")
    print("Artifacts:")
    print(" - data/processed/chunks.jsonl")
    print(" - data/processed/chunk_meta.jsonl")
    print(" - data/processed/embeddings.npy")
    print(" - data/index/faiss.index")


if __name__ == "__main__":
    main()
