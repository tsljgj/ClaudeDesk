"""PyInstaller 入口（打包成 ClaudeDesk.exe）。"""
import sys

from claudedesk.app import main

if __name__ == "__main__":
    sys.exit(main())
