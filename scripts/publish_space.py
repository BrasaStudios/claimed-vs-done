"""Upload a folder to a public static Hugging Face Space, creating the Space if needed.

Usage: python scripts/publish_space.py --repo BrasaStudios/claimed-vs-done --folder space
                                       [--token-env BRASA_HF_WRITE_TOKEN]
The folder must hold README.md with the Space's front matter (sdk: static). The same script
publishes the organization card: the README Space, e.g. --repo BrasaStudios/README.
The token is read from the named environment variable (or the Windows user environment) and
is never printed.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cvd.config import KeyMissing, get_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--token-env", default="BRASA_HF_WRITE_TOKEN")
    args = parser.parse_args()
    readme = args.folder / "README.md"
    if not readme.is_file() or "sdk: static" not in readme.read_text(encoding="utf-8"):
        print(f"{readme} is missing or has no 'sdk: static' front matter", file=sys.stderr)
        return 1
    try:
        token = get_key(args.token_env)
    except KeyMissing:
        print(f"No token in {args.token_env}", file=sys.stderr)
        return 2
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(args.repo, repo_type="space", space_sdk="static", private=False, exist_ok=True)
    # Mirror the folder exactly: a new static Space starts with a template index.html and
    # style.css, and on the README Space a leftover index.html replaces the org card.
    api.upload_folder(repo_id=args.repo, repo_type="space", folder_path=str(args.folder),
                      delete_patterns=["*"], commit_message="Update the page")
    info = api.space_info(args.repo)
    print(f"https://huggingface.co/spaces/{args.repo} is {'PRIVATE' if info.private else 'PUBLIC'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
