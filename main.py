"""ModeSwitch — entry point."""
import sys
from modeswitch.app import App

if __name__ == "__main__":
    app = App()
    sys.exit(app.run())
