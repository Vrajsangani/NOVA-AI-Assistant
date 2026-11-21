# AetherAI Modern Futuristic UI (functional)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QScrollArea, QFrame
)
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush
from PyQt5.QtCore import Qt, QTimer, QPointF, pyqtSignal
import random



class AetherAIModernUI(QWidget):
    reply_signal = pyqtSignal(str)
    def __init__(self, assistant):
        super().__init__()
        # Reply label to display assistant responses
        self.reply_label = QLabel("", self)
        self.reply_label.setGeometry(50, 500, 600, 30)  # adjust position and size as needed
        self.reply_label.setStyleSheet("color: white; font-size: 16px;")

        self.assistant = assistant
        self.particles = [QPointF(random.randint(-100, 100), random.randint(-100, 100)) for _ in range(120)]
        self._build()

        # Hook UI to assistant replies (for wake word background responses)
        try:
            self.reply_signal.connect(self._set_reply_text)
            self.assistant.set_reply_handler(self._emit_reply)
        except Exception:
            pass

        # animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(50)
    
    def add_message(self, text, sender="assistant"):
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(500)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)

        if sender == "assistant":
            bubble.setStyleSheet("""
                QLabel {
                    background-color: #0f0fff;
                    color: white;
                    padding: 10px;
                    border-radius: 15px;
                    margin: 5px;
                }
            """)
            alignment = Qt.AlignLeft
        else:
            bubble.setStyleSheet("""
                QLabel {
                    background-color: #333;
                    color: white;
                    padding: 10px;
                    border-radius: 15px;
                    margin: 5px;
                }
            """)
            alignment = Qt.AlignRight

        # Add to chat
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble, alignment=alignment)

        # Auto-scroll to bottom
        self.chat_area.verticalScrollBar().setValue(
            self.chat_area.verticalScrollBar().maximum()
        )

    def speak_reply(self):
        text = self.reply_label.text().strip()
        if text:
            self.assistant.speak(text)


    def _build(self):
        self.setWindowTitle("N.O.V.A Assistant")
        self.setStyleSheet("background-color: black; color: white;")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # --- Chat Area ---
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.addStretch(1)
        self.chat_area.setWidget(self.chat_content)
        layout.addWidget(self.chat_area)

        # --- Input Row ---
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type your message...")
        self.input.setFixedHeight(40)
        self.input.setStyleSheet("""
            QLineEdit {
                background: #111;
                border: 2px solid #3a6cff;
                border-radius: 20px;
                padding: 0 15px;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #5a8cff;
            }
        """)

        self.btn_mic = QPushButton("🎤")
        self.btn_mic.setFixedSize(40, 40)
        self._style_button(self.btn_mic)
        self.btn_mic.clicked.connect(self.handle_mic)

        self.btn_voice = QPushButton("🔊")
        self.btn_voice.setFixedSize(40, 40)
        self._style_button(self.btn_voice)
        self.btn_voice.clicked.connect(self.toggle_voice)

        input_row.addWidget(self.input)
        input_row.addWidget(self.btn_mic)
        input_row.addWidget(self.btn_voice)
        layout.addLayout(input_row)

        # Enter key → handle text
        self.input.returnPressed.connect(self.handle_text)

    def _set_reply_text(self, text: str):
        # Update reply label from assistant callback
        self.reply_label.setText(text or "")
        # Force relayout to show full wrapped text
        self.reply_label.adjustSize()
        self.update()

    def _emit_reply(self, text: str):
        # Emit from any thread; Qt will deliver to the GUI thread
        try:
            self.reply_signal.emit(text or "")
        except Exception:
            pass

    def _style_button(self, btn):
        btn.setStyleSheet("""
            QPushButton {
                background: #111;
                border: 2px solid #0f0fff;
                border-radius: 20px;
                font-size: 18px;
                color: white;
            }
            QPushButton:hover {
                background: #222;
                border: 2px solid #3a6cff;
            }
        """)

    # ---------- Event Handlers ----------
    def handle_text(self):
        user_text = self.input.text().strip()
        if not user_text:
            return

        # Display user message bubble
        self.add_message(user_text, sender="user")
        self.input.clear()

        # Process assistant response
        reply = self.assistant.process_command(user_text)
        self.add_message(reply, sender="assistant")

        if self.assistant.voice_enabled:
            self.assistant.speak(reply)

    def handle_mic(self):
        self.add_message("🎙️ Listening...", sender="assistant")
        query = self.assistant.listen()

        if not query:
            self.add_message("I didn’t catch that. Try again.", sender="assistant")
            if self.assistant.voice_enabled:
                self.assistant.speak("I didn’t catch that. Try again.")
            return

        # Display what user said
        self.add_message(query, sender="user")

        # Process command
        reply = self.assistant.process_command(query)
        self.add_message(reply, sender="assistant")

        # Speak the response
        if self.assistant.voice_enabled:
            self.assistant.speak(reply)
    
    def toggle_voice(self):
        self.assistant.voice_enabled = not self.assistant.voice_enabled
        state = "on" if self.assistant.voice_enabled else "off"
        self.add_message(f"Voice turned {state}.", sender="assistant")
        self.assistant.speak(f"Voice turned {state}.")


    def insert_emoji(self):
        self.input.insert("😀")

    def open_settings(self):
        QMessageBox.information(self, "Settings", "Settings menu coming soon!")

    # ---------- Draw glowing orb + particles ----------
    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # Center coordinates
        cx, cy = self.width() // 2, self.height() // 2 - 50

        # Glowing orb
        gradient_color = QColor(0, 0, 255, 150)
        for r in range(200, 100, -10):
            gradient_color.setAlpha(200 - r)
            qp.setBrush(QBrush(gradient_color))
            qp.setPen(Qt.NoPen)
            qp.drawEllipse(cx - r // 2, cy - r // 2, r, r)

        # Particle dots around orb
        qp.setBrush(QBrush(QColor(100, 150, 255)))
        for p in self.particles:
            x = int(cx + p.x())
            y = int(cy + p.y())
            qp.drawEllipse(x, y, 3, 3)

    def update_animation(self):
        # simple particle jitter
        self.particles = [
            QPointF(p.x() + random.randint(-2, 2), p.y() + random.randint(-2, 2))
            for p in self.particles
        ]
        self.update()
