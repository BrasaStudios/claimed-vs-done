"""Upload the folder built by build_dataset.py to the Hugging Face Hub as a dataset repo.

Usage: python scripts/upload_dataset.py [--repo BrasaStudios/claimed-vs-done]
                                        [--token-env BRASA_HF_WRITE_TOKEN] [--make-public]
A new repo is created PRIVATE. --make-public flips an existing repo to public and uploads
nothing. The token is read from the named environment variable (or the Windows user
environment) and is never printed.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cvd.config import KeyMissing, get_key  # noqa: E402

MARKER = ".built-by-build_dataset"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="BrasaStudios/claimed-vs-done")
    parser.add_argument("--folder", type=Path, default=ROOT / "dist" / "hf-dataset")
    parser.add_argument("--token-env", default="BRASA_HF_WRITE_TOKEN")
    parser.add_argument("--make-public", action="store_true")
    args = parser.parse_args()
    try:
        token = get_key(args.token_env)
    except KeyMissing:
        print(f"No token in {args.token_env}; create it first", file=sys.stderr)
        return 2
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    if args.make_public:
        api.update_repo_settings(args.repo, private=False, repo_type="dataset")
    else:
        if not (args.folder / MARKER).is_file():
            print(f"{args.folder} was not built by build_dataset.py", file=sys.stderr)
            return 1
        api.create_repo(args.repo, repo_type="dataset", private=True, exist_ok=True)
        api.upload_folder(repo_id=args.repo, repo_type="dataset", folder_path=str(args.folder),
                          ignore_patterns=[MARKER], commit_message="Upload Claimed vs. Done")
    info = api.repo_info(args.repo, repo_type="dataset")
    print(f"https://huggingface.co/datasets/{args.repo} is {'PRIVATE' if info.private else 'PUBLIC'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
