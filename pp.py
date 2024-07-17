import warnings

# Ignore deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import signal
import sys
import asyncio
import aiohttp
import os
import time
from pytube import YouTube
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QLineEdit, QProgressBar
from PyQt5.QtCore import QThread, pyqtSignal

class DownloadThread(QThread):
    progress_update = pyqtSignal(str)
    progress_percent = pyqtSignal(int)

    def __init__(self, video_url, num_parts):
        super(DownloadThread, self).__init__()
        self.video_url = video_url
        self.num_parts = num_parts
        self.total_downloaded = 0
        self.last_update_time = 0
        self.video_title = ""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def fetch_segment(self, session, url, start, end, part, total_size, progress):
        headers = {
            "Range": f"bytes={start}-{end}"
        }
        async with session.get(url, headers=headers) as response:
            content = await response.read()
            segment_size = len(content)
            progress[part] = segment_size
            with open(f"part_{part}.mp4", "wb") as f:
                f.write(content)
            self.progress_update.emit(f"Segment {part} téléchargé : {segment_size} octets ({(segment_size / total_size) * 100:.2f}%)")

    async def download_video_in_parts(self):
        self.progress_update.emit("Récupération du lien...")
        yt = YouTube(self.video_url)
        self.video_title = yt.title
        self.progress_update.emit("Connexion au serveur...")
        stream = yt.streams.get_highest_resolution()
        total_size = stream.filesize
        segment_size = total_size // self.num_parts
        progress = [0] * self.num_parts

        tasks = []
        async with aiohttp.ClientSession() as session:
            for i in range(self.num_parts):
                start = i * segment_size
                end = start + segment_size - 1
                if i == self.num_parts - 1:
                    end = total_size - 1  # Télécharger jusqu'à la fin du fichier
                task = asyncio.create_task(self.fetch_segment(session, stream.url, start, end, i, total_size, progress))
                tasks.append(task)

            async def print_progress():
                start_time = time.time()
                while any(not task.done() for task in tasks):
                    self.total_downloaded = sum(progress)
                    elapsed_time = time.time() - start_time
                    speed = self.total_downloaded / elapsed_time if elapsed_time > 0 else 0
                    percentage = (self.total_downloaded / total_size) * 100
                    remaining_time = (total_size - self.total_downloaded) / speed if speed > 0 else 0
                    current_time = time.time()
                    if current_time - self.last_update_time >= 0.1:
                        self.progress_update.emit(
                            f"Téléchargement global... {percentage:.2f}% à {speed / 1024:.2f} KB/s, "
                            f"Temps restant estimé : {remaining_time:.2f} secondes")
                        self.progress_percent.emit(int(percentage))
                        self.last_update_time = current_time
                    await asyncio.sleep(0.1)

            await asyncio.gather(*tasks, print_progress())

        self.progress_update.emit("Assemblage des segments...")
        video_filename = f"{self.video_title}.mp4"
        with open(video_filename, "wb") as f:
            for i in range(self.num_parts):
                with open(f"part_{i}.mp4", "rb") as part_file:
                    f.write(part_file.read())
                os.remove(f"part_{i}.mp4")

        self.progress_update.emit("Téléchargement terminé avec succès.")
        self.progress_percent.emit(100)

    def run(self):
        try:
            self.loop.run_until_complete(self.download_video_in_parts())
        finally:
            self.loop.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.setWindowTitle("Téléchargeur YouTube")
        self.setGeometry(100, 100, 600, 150)

        self.layout = QVBoxLayout()

        self.label = QLabel("Entrez le lien de la vidéo YouTube :")
        self.layout.addWidget(self.label)

        self.url_input = QLineEdit()
        self.layout.addWidget(self.url_input)

        self.button = QPushButton("Démarrer le téléchargement")
        self.button.clicked.connect(self.start_download)
        self.layout.addWidget(self.button)

        self.progress_label = QLabel("En attente ...")
        self.layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.container = QWidget()
        self.container.setLayout(self.layout)
        self.setCentralWidget(self.container)

    def start_download(self):
        video_url = self.url_input.text()
        if not video_url:
            self.progress_label.setText("Le lien de la vidéo ne peut pas être vide.")
            return

        num_parts = 4  # Par défaut à 4 segments
        try:
            num_parts = int(num_parts)
            if num_parts <= 0:
                raise ValueError
        except ValueError:
            self.progress_label.setText("Le nombre de segments doit être un entier positif.")
            return

        self.thread = DownloadThread(video_url, num_parts)
        self.thread.progress_update.connect(self.update_progress)
        self.thread.progress_percent.connect(self.update_progress_bar)
        self.thread.start()

    def update_progress(self, message):
        self.progress_label.setText(message)

    def update_progress_bar(self, percentage):
        self.progress_bar.setValue(percentage)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Graceful exit handling
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    sys.exit(app.exec_())
