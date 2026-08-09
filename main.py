import sys

from image_tool.app_modern import configure_runtime, run


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        configure_runtime()
        from image_tool.self_test import run_self_test

        raise SystemExit(run_self_test(require_gpu="--require-gpu" in sys.argv))
    if "--ui-smoke-test" in sys.argv:
        configure_runtime()
        from image_tool.app_modern import run_ui_smoke_test

        raise SystemExit(run_ui_smoke_test())
    run()
