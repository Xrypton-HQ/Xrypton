"""steals emojis from bleed support"""
import os
import re
import requests

# add more here if you want (and uncomment)
# EMOJI_TEXT = """
# <:skipto:905600797037973575>
# <:approve:743005300801404938>
# <:deny:743005185365901342>
# <:warning:743006201981173831>
# <:left:905600769376530443>
# <:right:905600782437589032><:cancel:905600891497906217>
# """
EMOJI_TEXT = "<:cooldown:743092875939807302>"

OUTPUT_DIR = os.path.join("emojis")


def parse_emojis(text):
    """Extract (name, id, animated) tuples from Discord emoji tags."""
    pattern = r"<(a?):(\w+):(\d+)>"
    matches = re.findall(pattern, text)
    return [(name, emoji_id, bool(animated)) for animated, name, emoji_id in matches]


def download_emojis(emojis, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for name, emoji_id, animated in emojis:
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
        filepath = os.path.join(output_dir, f"{name}.{ext}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"Downloaded: {name} -> {filepath}")
        except requests.RequestException as e:
            print(f"Failed to download {name} ({url}): {e}")


if __name__ == "__main__":
    emojis = parse_emojis(EMOJI_TEXT)
    if not emojis:
        print("No emoji tags found in EMOJI_TEXT.")
    else:
        print(f"Found {len(emojis)} emoji(s). Downloading to '{OUTPUT_DIR}'...")
        download_emojis(emojis, OUTPUT_DIR)