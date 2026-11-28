"""Compatibility entry point for the every-ply attacker analysis."""
if __package__:
    from scripts.classify_blockade import main
else:
    from classify_blockade import main


if __name__ == "__main__":
    raise SystemExit(main())
