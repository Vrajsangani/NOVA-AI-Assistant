# AetherAI - Entry point
import sys
from PyQt5.QtWidgets import QApplication
from assistant import Assistant
from ui import AetherAIModernUI

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("N.O.V.A")

    assistant = Assistant(voice_rate=176, voice_enabled=True)
    # Start hands-free wake word listener ("Aris") automatically
    try:
        assistant.start_wake_word()
    except Exception:
        pass
    win = AetherAIModernUI(assistant)
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
