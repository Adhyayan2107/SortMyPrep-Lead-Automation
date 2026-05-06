"""
Master pipeline orchestrator.

Usage:
    python pipeline.py              # run all steps
    python pipeline.py --reset      # clear state and start fresh

State is saved to Outputs/pipeline_state.json after each step completes,
so the pipeline resumes from the last completed step if it crashes.
"""

import argparse
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CONFIG_PATH = "config.json"
STATE_PATH  = "Outputs/pipeline_state.json"

DEFAULT_STATE = {
    "step1_done": False,
    "step2_done": False,
    "step3_done": False,
    "step4_done": False,
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return dict(DEFAULT_STATE)


def save_state(state):
    os.makedirs("Outputs", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def reset_state():
    if os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
    logging.info("Pipeline state cleared — will restart from Step 1.")


def main():
    parser = argparse.ArgumentParser(description="Run the full Google Maps → contacts pipeline")
    parser.add_argument("--reset", action="store_true", help="Clear saved state and restart from Step 1")
    args = parser.parse_args()

    if args.reset:
        reset_state()

    config = load_config()
    state  = load_state()

    import step1_matrix
    import step2_llm_filter
    import step3_rocketreach
    import step4_export

    steps = [
        ("step1_done", "STEP 1: Scraping Google Maps",          step1_matrix.run),
        ("step2_done", "STEP 2: LLM Filtering (Groq)",          step2_llm_filter.run),
        ("step3_done", "STEP 3: Contact Lookup (RocketReach)",   step3_rocketreach.run),
        ("step4_done", "STEP 4: Final Export",                   step4_export.run),
    ]

    for key, label, fn in steps:
        if state[key]:
            logging.info(f"[SKIP] {label} already done.")
            continue
        logging.info(f"\n{'='*60}\n{label}\n{'='*60}")
        fn(config)
        state[key] = True
        save_state(state)

    logging.info("\nPipeline complete!  Final output → Outputs/final.csv")


if __name__ == "__main__":
    main()
