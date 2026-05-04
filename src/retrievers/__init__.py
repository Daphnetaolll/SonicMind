from __future__ import annotations


def retrieve_local_evidence(*args, **kwargs):
    """
    Explanation:
    Keep package imports lightweight.
    Local retrieval imports FAISS/numpy dependencies only when the local retriever is actually called.
    """
    from src.retrievers.local_retriever import retrieve_local_evidence as _retrieve_local_evidence

    return _retrieve_local_evidence(*args, **kwargs)


def retrieve_site_evidence(*args, **kwargs):
    from src.retrievers.site_retriever import retrieve_site_evidence as _retrieve_site_evidence

    return _retrieve_site_evidence(*args, **kwargs)


def retrieve_web_evidence(*args, **kwargs):
    from src.retrievers.web_retriever import retrieve_web_evidence as _retrieve_web_evidence

    return _retrieve_web_evidence(*args, **kwargs)

__all__ = [
    "retrieve_local_evidence",
    "retrieve_site_evidence",
    "retrieve_web_evidence",
]
