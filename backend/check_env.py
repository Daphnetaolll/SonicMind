import sys

import transformers
import faiss

# Print runtime versions used by the deployment smoke check.
print("Python:", sys.version)
print("transformers:", transformers.__version__)
print("faiss:", faiss.__version__ if hasattr(faiss, "__version__") else "ok")
# Keep this checker aligned with requirements.txt so it validates the deployable app environment.
print("ALL IMPORTS OK ✅")
