
from pathlib import Path
import shutil
import zipfile

from huggingface_hub import hf_hub_download
BASE_DIR = Path(__file__).resolve().parent

REPO_ID = "LojainOS/MIZAN"

IMAGE_MODELS = {
    "m1_final.pth": Path("finalprojup/m1_final.pth"),
    "m2_final.pth": Path("finalprojup/m2_final.pth"),
}

TEXT_MODELS = {
    "MODFnew_model_arabertV02.zip": (
        "MODFnew_model_arabertV02/",
        Path("MODFnew_model_arabertV02"),
    ),
    "title_version.zip": (
        "title_version/",
        Path("title_version/kaggle/working/title_version"),
    ),
}

REQUIRED_FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
)


def download(filename):
    return hf_hub_download(
        repo_id=REPO_ID,
        filename=filename,
        repo_type="model",
    )


def main():
    import os
    os.chdir(BASE_DIR)
    for remote, destination in IMAGE_MODELS.items():
        if destination.exists():
            print(f"Already exists: {destination}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {remote}...")
        shutil.copy2(download(remote), destination)

    for archive_name, (prefix, destination) in TEXT_MODELS.items():
        if all((destination / name).is_file() for name in REQUIRED_FILES):
            print(f"Already extracted: {destination}")
            continue

        print(f"Downloading {archive_name}...")
        archive_path = download(archive_name)

        with zipfile.ZipFile(archive_path) as archive:
            for filename in REQUIRED_FILES:
                member_name = prefix + filename

                if member_name not in archive.namelist():
                    raise FileNotFoundError(
                        f"Missing in {archive_name}: {member_name}"
                    )

                destination.mkdir(parents=True, exist_ok=True)
                target = destination / filename

                if target.exists():
                    continue

                with archive.open(member_name) as source:
                    with target.open("wb") as output:
                        shutil.copyfileobj(source, output)

                print(f"Extracted: {target}")

    print("All MIZAN models are ready.")


if __name__ == "__main__":
    main()
