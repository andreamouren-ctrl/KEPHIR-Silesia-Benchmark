from pathlib import Path
import argparse
import os
import subprocess

PROFILES = {
    "streaming4k": (24, 12),
    "balanced": (48, 24),
    "maxcompression": (64, 32),
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", choices=PROFILES)
    ap.add_argument("--output", default="KEPHIR_SPEED_D_SOURCE.cpp")
    ap.add_argument("--match-prefilter", choices=["auto","none"], default="auto")
    args = ap.parse_args()

    chain, lazy = PROFILES[args.profile]
    env = os.environ.copy()
    env["K2_CHAIN_DEPTH_VALUE"] = str(chain)
    env["K2_LAZY_DEPTH_VALUE"] = str(lazy)
    env["K2_PRED_MASK_VALUE"] = "255"

    subprocess.run(["python3", "make_speed1_source.py"], check=True, env=env)
    subprocess.run(["python3", "make_fastd_source.py"], check=True)

    if args.match_prefilter == "auto" and args.profile == "balanced":
        subprocess.run([
            "python3", "make_fastd_match_prefilter_source.py",
            "tail8_mid8", "--output", "KEPHIR_SPEED_D_SOURCE.cpp"
        ], check=True)

    src = Path("KEPHIR_SPEED_D_SOURCE.cpp")
    out = Path(args.output)
    if out != src:
        out.write_bytes(src.read_bytes())

    print(
        f"FAST_D_VIDEO_PROFILE_OK profile={args.profile} "
        f"chain={chain} lazy={lazy} pred_mask=255 "
        f"prefilter={'tail8_mid8' if args.match_prefilter == 'auto' and args.profile == 'balanced' else 'none'} "
        f"output={out}"
    )

if __name__ == "__main__":
    main()
