import uuid
import argparse

def generate_keys(prefix: str, count: int):
    """Generates a specified number of unique, non-guessable keys."""
    print(f"--- Generating {count} key(s) with prefix '{prefix}' ---")
    for i in range(count):
        # We combine the prefix with a UUID to ensure the key is unique.
        # .upper() makes it look cleaner and easier for users to type.
        # [-12:] takes the last 12 characters of the UUID for a shorter, yet still very unique key.
        key = f"{prefix}-{uuid.uuid4().hex.upper()[-12:]}"
        print(key)
    print("--- Generation complete ---")

if __name__ == "__main__":
    # This allows you to run the script from your computer's terminal with options.
    parser = argparse.ArgumentParser(description="Generate activation keys for your bot service.")
    parser.add_argument(
        "-p", "--prefix", 
        type=str, 
        required=True, 
        help="The prefix for the keys (e.g., '1MONTH', '6MONTH', 'LIFETIME')."
    )
    parser.add_argument(
        "-c", "--count", 
        type=int, 
        default=1, 
        help="The number of keys to generate."
    )
    
    args = parser.parse_args()
    generate_keys(args.prefix, args.count)