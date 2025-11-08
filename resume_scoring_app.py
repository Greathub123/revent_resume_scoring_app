"""
Resume Scoring Tool for CTO (Founder-Track) Role
================================================

This script implements a complete scoring engine and web‑based user interface
for evaluating a set of resumes against the criteria defined for a
Chief Technology Officer (co‑founder track) position.  It reflects the
weightings and keyword clusters described in the provided framework
and generates both a ranked CSV file and per‑candidate explanation
cards.

Dependencies
------------

The application requires a few third‑party libraries to parse common
resume formats and to provide an interactive user interface:

* **streamlit** – powers the web UI (``pip install streamlit``)
* **pandas** – tabular data handling (``pip install pandas``)
* **PyPDF2** – reading text from PDF documents (``pip install PyPDF2``)
* **python‑docx** – reading text from Microsoft Word documents (``pip install python-docx``)

If any of these packages are missing, you can install them with pip
before running this script.  For example:

```
pip install streamlit pandas PyPDF2 python-docx
```

Running the application
-----------------------

To launch the scoring tool, execute the following command from a
terminal in the same directory as this script:

```
streamlit run resume_scoring_app.py
```

You will be presented with a web page where you can upload multiple
resume files (PDF, DOCX or plain text).  Once uploaded, click the
``Process resumes`` button to generate scores.  A ranked table will
appear, and you can download a CSV file containing the results.  Each
candidate’s explanation card is accessible via expandable sections
below the table.
"""

import base64
import io
import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import pandas as pd

# Attempt imports that may not be installed.  These try/except blocks
# allow the script to inform the user about missing dependencies
try:
    import PyPDF2  # type: ignore
except ImportError:
    PyPDF2 = None  # type: ignore

try:
    import docx  # type: ignore
except ImportError:
    docx = None  # type: ignore

try:
    import streamlit as st  # type: ignore
except ImportError:
    st = None  # type: ignore


# ---------------------------------------------------------------------------
# Scoring configuration
#
# The following dictionary encodes the weighting model and keyword clusters
# described in the earlier one‑pager.  Feel free to adjust these lists
# to better align with your hiring priorities.

SCORING_CONFIG: Dict[str, Dict[str, Dict[str, List[str] or int]]] = {
    "weights": {
        "core": 40,
        "product": 25,
        "leadership": 20,
        "domain": 10,
        "innovation": 5,
    },
    "core": {
        "fullstack": {
            "w": 10,
            "terms": [
                "react",
                "next.js",
                "typescript",
                "node",
                "express",
                "python",
                "django",
                "fastapi",
                "graphql",
                "rest",
            ],
        },
        "arch_cloud_devops": {
            "w": 10,
            "terms": [
                "aws",
                "gcp",
                "azure",
                "docker",
                "kubernetes",
                "terraform",
                "ci/cd",
                "microservices",
                "kafka",
                "sqs",
                "event-driven",
                "devops",
                "cloud",
            ],
        },
        "ai_llm_data": {
            "w": 12,
            "terms": [
                "openai",
                "claude",
                "hugging face",
                "langchain",
                "llamaindex",
                "rag",
                "vector db",
                "faiss",
                "pinecone",
                "weaviate",
                "mlflow",
                "sagemaker",
                "vertex ai",
                "airflow",
                "dbt",
                "mlops",
            ],
        },
        "automation": {
            "w": 4,
            "terms": [
                "automation",
                "rpa",
                "playwright",
                "puppeteer",
                "zapier",
                "internal tooling",
                "scripting",
            ],
        },
        "sec_scale": {
            "w": 4,
            "terms": [
                "oauth",
                "oidc",
                "owasp",
                "encryption",
                "kms",
                "rate limit",
                "redis",
                "caching",
                "load testing",
                "cost optimization",
                "security",
            ],
        },
    },
    "product": {
        "e2e": {
            "w": 10,
            "phrases": [
                "mvp",
                "prototype",
                "launched",
                "go-live",
                "production",
                "observability",
                "product launch",
                "rollout",
            ],
        },
        "speed_quality": {
            "w": 6,
            "phrases": [
                "lean",
                "iterative",
                "build vs buy",
                "time-box",
                "tech debt",
                "scrum",
                "agile",
            ],
        },
        "hands_on": {
            "w": 5,
            "phrases": [
                "hands-on",
                "coding",
                "pair programming",
                "code review",
                "on-call",
                "pair reviews",
            ],
        },
        "biz_tech": {
            "w": 4,
            "phrases": [
                "roadmap",
                "business goals",
                "founders",
                "investors",
                "partners",
            ],
        },
    },
    "leadership": {
        "team_mentorship": {
            "w": 8,
            "phrases": [
                "hired",
                "mentored",
                "grew team",
                "engineering culture",
                "best practices",
                "managed",
                "led",
            ],
        },
        "owner_mindset": {
            "w": 6,
            "phrases": [
                "co-founded",
                "equity",
                "0-1",
                "bootstrapped",
                "ownership",
                "founding engineer",
            ],
        },
        "xfn": {
            "w": 4,
            "phrases": [
                "product",
                "design",
                "ops",
                "marketing",
                "sales",
                "cross-functional",
            ],
        },
        "grit": {
            "w": 2,
            "phrases": [
                "pivot",
                "shutdown",
                "postmortem",
                "rationale",
                "constraints",
                "resilience",
            ],
        },
    },
    "domain": {
        "commerce_supply_subs": {
            "w": 6,
            "terms": [
                "subscription",
                "billing",
                "inventory",
                "reverse logistics",
                "rma",
                "refurb",
                "marketplace",
                "catalog",
                "device lifecycle",
            ],
        },
        "sme_auto_green": {
            "w": 4,
            "terms": [
                "device management",
                "smb automation",
                "b2b saas",
                "sustainability",
                "circular",
                "green",
                "recommerce",
            ],
        },
    },
    "innovation": {
        "learn": {
            "w": 3,
            "phrases": [
                "hackathon",
                "open-source",
                "blog",
                "talk",
                "github",
                "conference",
            ],
        },
        "experiments": {
            "w": 2,
            "phrases": [
                "langchain",
                "rag",
                "agents",
                "vector db",
                "evals",
                "proof of concept",
            ],
        },
    },
}


# A list of common action verbs used to identify substantive contributions in a resume.
ACTION_VERBS: List[str] = [
    "built",
    "designed",
    "implemented",
    "developed",
    "integrated",
    "created",
    "launched",
    "architected",
    "constructed",
    "founded",
    "scaled",
    "optimized",
    "drove",
    "led",
    "owned",
    "delivered",
    "initiated",
    "invented",
]


def ensure_dependencies():
    """Check that required third‑party libraries are available.

    If any import failed above, raise a RuntimeError with guidance on
    installing the missing package.  This function is called only
    within the Streamlit run to provide user feedback in the UI.
    """
    missing = []
    if PyPDF2 is None:
        missing.append("PyPDF2")
    if docx is None:
        missing.append("python-docx")
    if st is None:
        missing.append("streamlit")
    if missing:
        raise RuntimeError(
            f"The following required packages are missing: {', '.join(missing)}.\n"
            "Please install them with: pip install " + " ".join(missing)
        )


def extract_text_from_pdf(file_stream: io.BytesIO) -> str:
    """Extract raw text from a PDF file using PyPDF2.

    Parameters
    ----------
    file_stream : io.BytesIO
        A binary stream representing the PDF document.

    Returns
    -------
    str
        The extracted text concatenated from all pages.
    """
    if PyPDF2 is None:
        return ""
    reader = PyPDF2.PdfReader(file_stream)
    text = []
    for page in reader.pages:
        try:
            page_text = page.extract_text()
        except Exception:
            page_text = ""
        if page_text:
            text.append(page_text)
    return "\n".join(text)


def extract_text_from_docx(file_stream: io.BytesIO) -> str:
    """Extract raw text from a DOCX file using python-docx.

    Parameters
    ----------
    file_stream : io.BytesIO
        A binary stream representing the DOCX document.

    Returns
    -------
    str
        The extracted text concatenated from paragraphs.
    """
    if docx is None:
        return ""
    # python‑docx can open file-like objects directly
    document = docx.Document(file_stream)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def clean_and_tokenize(text: str) -> List[str]:
    """Preprocess text: lowercase and split into tokens.

    A simple whitespace tokenizer is used to avoid heavy dependencies.
    Punctuation is stripped for keyword matching.
    """
    text_lower = text.lower()
    # Replace punctuation with spaces
    text_no_punct = re.sub(r"[^a-z0-9]+", " ", text_lower)
    tokens = text_no_punct.split()
    return tokens


def contextual_hits(tokens: List[str], terms: List[str]) -> List[int]:
    """Compute hits where a term appears near an action verb.

    This heuristic scans the tokenized resume and returns indices of
    occurrences where a keyword/phrase appears within a small window
    (preceding 5 tokens) of one of the predefined action verbs.  It
    reduces the impact of skill dumps by focusing on contextual usage.

    Parameters
    ----------
    tokens : List[str]
        The tokenized resume text.
    terms : List[str]
        A list of single tokens or space separated phrases to match.

    Returns
    -------
    List[int]
        A list of indices (positions) where a term match was found
        alongside an action verb in the preceding window.
    """
    hits: List[int] = []
    # Create a set of action verbs for quick lookup
    action_set = set(ACTION_VERBS)
    # Pre‑join tokens into a single string for phrase matching
    text_str = " ".join(tokens)
    for term in terms:
        term_tokens = term.lower().split()
        if len(term_tokens) == 1:
            for idx, token in enumerate(tokens):
                if token == term_tokens[0]:
                    # Check preceding window for action verb
                    window_start = max(0, idx - 5)
                    if any(t in action_set for t in tokens[window_start:idx]):
                        hits.append(idx)
        else:
            # Multiword phrase search using regex
            # Build a regex to match the phrase with word boundaries
            phrase_pattern = r"\\b" + re.escape(" ".join(term_tokens)) + r"\\b"
            for match in re.finditer(phrase_pattern, text_str):
                # Convert character index to token index by counting spaces
                char_pos = match.start()
                token_index = text_str[:char_pos].count(" ")
                window_start = max(0, token_index - 5)
                if any(t in action_set for t in tokens[window_start:token_index]):
                    hits.append(token_index)
    return hits


def compute_bucket_score(tokens: List[str], terms: List[str], weight: int) -> Tuple[float, float]:
    """Compute the raw and normalized score for a bucket of terms.

    The raw score is proportional to the number of contextual hits of
    keywords/phrases found in the resume.  A logistic function is
    applied to map the raw count into a [0, 1] range.  This prevents
    runaway scores for resumes that mention a term excessively.

    Parameters
    ----------
    tokens : List[str]
        Tokenized resume text.
    terms : List[str]
        Keywords or phrases for this bucket.
    weight : int
        Weight assigned to this bucket (used only for explanation).

    Returns
    -------
    Tuple[float, float]
        The first element is the normalized bucket score in [0, 1].
        The second element is the raw hit count for explanation.
    """
    hits = contextual_hits(tokens, terms)
    count = len(hits)
    # Logistic transform: adjust k to tweak sensitivity (here k=0.5)
    normalized = 1.0 - math.exp(-0.5 * count) if count > 0 else 0.0
    return normalized, float(count)


def compute_category_scores(tokens: List[str]) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """Compute scores for each high‑level category and breakdown details.

    The function iterates over each category and its buckets in
    ``SCORING_CONFIG``, computes a normalized score per bucket, and
    aggregates them using the specified weights.  It also records
    detailed hit counts for explanation cards.

    Parameters
    ----------
    tokens : List[str]
        Tokenized resume text.

    Returns
    -------
    Tuple[Dict[str, float], Dict[str, Dict[str, float]]]
        A mapping from category to its overall (weighted) score, and
        a nested mapping of bucket names to hit counts.
    """
    category_scores: Dict[str, float] = {}
    detail_counts: Dict[str, Dict[str, float]] = {}

    for cat in ["core", "product", "leadership", "domain", "innovation"]:
        cat_config = SCORING_CONFIG[cat]
        weights = SCORING_CONFIG["weights"]
        cat_weight = float(weights[cat])
        cat_score = 0.0
        detail_counts[cat] = {}
        # Sum of bucket weights for normalization
        total_bucket_weight = sum(item["w"] for item in cat_config.values())
        for bucket_name, bucket_data in cat_config.items():
            keylist = bucket_data.get("terms") or bucket_data.get("phrases") or []
            bucket_weight = float(bucket_data["w"])
            normalized_score, hit_count = compute_bucket_score(tokens, keylist, bucket_weight)
            detail_counts[cat][bucket_name] = hit_count
            # Weighted by bucket weight relative to total for category
            cat_score += (bucket_weight / total_bucket_weight) * normalized_score
        category_scores[cat] = cat_score * cat_weight
    return category_scores, detail_counts


def score_resume(text: str) -> Tuple[float, Dict[str, float], Dict[str, Dict[str, float]]]:
    """Compute the final composite score and breakdown for a resume.

    This wraps tokenization and calls ``compute_category_scores``.  The
    final score is the sum of category scores divided by the sum of
    all weights (100).  Breakdown scores per category are also
    provided for display.

    Parameters
    ----------
    text : str
        The raw resume text extracted from the file.

    Returns
    -------
    Tuple[float, Dict[str, float], Dict[str, Dict[str, float]]]
        The composite score in the range [0, 100], the per‑category
        scores, and detailed hit counts per bucket.
    """
    tokens = clean_and_tokenize(text)
    category_scores, detail_counts = compute_category_scores(tokens)
    total_weight = sum(SCORING_CONFIG["weights"].values())
    final_score = sum(category_scores.values()) / total_weight * 100.0
    # Normalize per-category scores to the 0–100 scale for presentation
    normalized_breakdown = {
        cat: (score / SCORING_CONFIG["weights"][cat]) * 100.0 for cat, score in category_scores.items()
    }
    return final_score, normalized_breakdown, detail_counts


def run_app():
    """Launch the Streamlit user interface for scoring resumes."""
    ensure_dependencies()
    st.set_page_config(page_title="Resume Scoring Tool", layout="wide")
    st.title("CTO (Co‑Founder Track) Resume Scoring Tool")
    st.write(
        "This application evaluates resumes against the criteria defined "
        "for the Revent CTO (co‑founder track) role and computes a "
        "score from 0–100.  Upload PDF, DOCX or plain text files and "
        "click *Process resumes* to view the ranking and download a CSV."
    )

    uploaded_files = st.file_uploader(
        "Upload one or more resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True
    )

    if st.button("Process resumes"):
        if not uploaded_files:
            st.warning("Please upload at least one resume before processing.")
            return
        results: List[Dict[str, object]] = []
        explanations: Dict[str, Dict[str, Dict[str, float]]] = {}

        for file in uploaded_files:
            filename = file.name
            data = file.read()
            file_stream = io.BytesIO(data)
            # Determine file type based on extension
            ext = os.path.splitext(filename)[1].lower()
            text = ""
            if ext == ".pdf":
                text = extract_text_from_pdf(file_stream)
            elif ext == ".docx":
                text = extract_text_from_docx(file_stream)
            else:
                # Treat other types as plain text
                try:
                    text = data.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            # Compute score
            final_score, breakdown, detail_counts = score_resume(text)
            # Build result record
            result_record = {
                "Filename": filename,
                "Score": round(final_score, 2),
                "Core (0–100)": round(breakdown["core"], 1),
                "Product (0–100)": round(breakdown["product"], 1),
                "Leadership (0–100)": round(breakdown["leadership"], 1),
                "Domain (0–100)": round(breakdown["domain"], 1),
                "Innovation (0–100)": round(breakdown["innovation"], 1),
            }
            results.append(result_record)
            explanations[filename] = detail_counts

        # Create DataFrame and sort by score
        df = pd.DataFrame(results)
        df_sorted = df.sort_values(by="Score", ascending=False).reset_index(drop=True)
        st.success(f"Processed {len(uploaded_files)} resumes.")
        st.subheader("Ranked Candidates")
        st.dataframe(df_sorted, use_container_width=True)

        # Provide CSV download
        csv_data = df_sorted.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv_data, file_name="resume_scores.csv", mime="text/csv")

        # Explanation cards
        st.subheader("Explanation Cards")
        for idx, row in df_sorted.iterrows():
            filename = row["Filename"]
            st.markdown(f"**{idx + 1}. {filename} — Score: {row['Score']}**")
            with st.expander("View details"):
                detail_counts = explanations[filename]
                st.markdown("### Per‑Category Hit Counts")
                # Build a table of bucket hit counts
                for cat in ["core", "product", "leadership", "domain", "innovation"]:
                    st.markdown(f"**{cat.capitalize()}**")
                    hits_table = []
                    for bucket, count in detail_counts[cat].items():
                        hits_table.append((bucket, int(count)))
                    hits_df = pd.DataFrame(hits_table, columns=["Bucket", "Hit count"])
                    st.table(hits_df)
                st.markdown(
                    "These counts reflect the number of times keywords or phrases "
                    "appeared near action verbs in the resume. Higher counts "
                    "indicate stronger evidence for that aspect."
                )


# Entrypoint for standalone execution (e.g., ``python resume_scoring_app.py``)
if __name__ == "__main__":
    if "streamlit" in os.environ.get("RUN_MAIN", ""):
        # When executed through streamlit, this branch prevents accidental
        # direct runs inside the streamlit server.  Streamlit sets RUN_MAIN
        # when reloading the script.  We call run_app() only once per load.
        run_app()
    else:
        # Provide a CLI fallback: allow scoring of a directory of resumes
        import argparse

        parser = argparse.ArgumentParser(
            description="Score resumes in a directory and output a CSV."
        )
        parser.add_argument(
            "input_dir", help="Path to a directory containing resume files"
        )
        parser.add_argument(
            "output_csv", help="Path where the ranked CSV should be written"
        )
        args = parser.parse_args()

        input_dir = args.input_dir
        output_csv = args.output_csv

        files = [
            f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))
        ]
        records: List[Dict[str, object]] = []
        for fname in files:
            full_path = os.path.join(input_dir, fname)
            with open(full_path, "rb") as fh:
                data = fh.read()
            ext = os.path.splitext(fname)[1].lower()
            text = ""
            if ext == ".pdf" and PyPDF2 is not None:
                text = extract_text_from_pdf(io.BytesIO(data))
            elif ext == ".docx" and docx is not None:
                text = extract_text_from_docx(io.BytesIO(data))
            else:
                try:
                    text = data.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            final_score, breakdown, _ = score_resume(text)
            records.append(
                {
                    "Filename": fname,
                    "Score": round(final_score, 2),
                    "Core (0–100)": round(breakdown["core"], 1),
                    "Product (0–100)": round(breakdown["product"], 1),
                    "Leadership (0–100)": round(breakdown["leadership"], 1),
                    "Domain (0–100)": round(breakdown["domain"], 1),
                    "Innovation (0–100)": round(breakdown["innovation"], 1),
                }
            )
        df_out = pd.DataFrame(records).sort_values(by="Score", ascending=False)
        df_out.to_csv(output_csv, index=False)
        print(f"Wrote {len(records)} scored resumes to {output_csv}")