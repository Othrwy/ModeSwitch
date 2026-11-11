"""ModeSwitch — entry point."""
import sys
from modeswitch import autostart

if __name__ == "__main__":
    if not autostart.single_instance():
        sys.exit(0)   # already running: autostart fires on every unlock and wake
    from modeswitch.app import App
    app = App()
    sys.exit(app.run())
