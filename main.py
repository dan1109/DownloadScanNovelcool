import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout, \
    QMessageBox, QProgressBar, QTextEdit
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import requests
from bs4 import BeautifulSoup
import os
import re
import logging
from tqdm import tqdm

# Configura il logger
logging.basicConfig(filename='download_errors.log', level=logging.ERROR, format='%(asctime)s - %(message)s')


class DownloadThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)

    def __init__(self, start_chapter, end_chapter, index_url):
        super().__init__()
        self.start_chapter = start_chapter
        self.end_chapter = end_chapter
        self.index_url = index_url

    def run(self):
        try:
            root_folder = re.sub(r'[-_]', ' ', self.index_url.rstrip('/').split('/')[-1].replace('.html', ''))
            chapter_urls = get_chapter_urls(self.index_url, self.start_chapter, self.end_chapter)
            total_chapters = len(chapter_urls)
            for i, url in enumerate(chapter_urls):
                try:
                    download_images_from_url(url, root_folder, self.log)
                except Exception as e:
                    logging.error(f'Errore durante il download delle immagini per il capitolo {url}: {e}')
                    self.log.emit(f'Errore durante il download delle immagini per il capitolo {url}: {e}')
                    continue
                self.progress.emit(int((i + 1) / total_chapters * 100))
            self.log.emit("Download completato con successo!")
        except Exception as e:
            logging.error(f'Errore generale: {e}')
            self.log.emit(f'Errore generale: {e}')
            QMessageBox.critical(None, "Errore", f"Si è verificato un errore: {e}")


def get_chapter_urls(index_url, start_chapter, end_chapter=None):
    print("Recupero degli URL dei capitoli...")
    response = requests.get(index_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    chapters = soup.find_all('a', href=True, title=True)

    chapter_urls = []
    for chapter in chapters:
        href = chapter['href']
        match = re.search(r'chapter/(\d+)-', href)
        if match:
            chapter_number = int(match.group(1))
            if chapter_number >= start_chapter and (end_chapter is None or chapter_number <= end_chapter):
                chapter_urls.append(href)
                print(f"Trovato capitolo {chapter_number}: {href}")

    chapter_urls.sort(key=lambda x: int(re.search(r'chapter/(\d+)-', x).group(1)))
    print(f"Trovati {len(chapter_urls)} capitoli tra {start_chapter} e {end_chapter}.")
    return chapter_urls


def download_images_from_url(base_url, root_folder, log_signal):
    log_signal.emit(f"Scaricamento immagini da: {base_url}")
    chapter_number = re.search(r'chapter/(\d+)-', base_url).group(1)
    print(f"Scaricamento immagini per il capitolo {chapter_number}")

    chapter_folder = os.path.join(root_folder, f'chapter_{chapter_number}')
    if not os.path.exists(chapter_folder):
        os.makedirs(chapter_folder)

    page_num = 1
    while True:
        page_url = f"{base_url.rsplit('/', 1)[0]}/{chapter_number}-{page_num}.html"
        print(f"Scaricamento pagina: {page_url}")
        response = requests.get(page_url)

        if response.status_code != 200:
            print(f"Pagina {page_num} del capitolo {chapter_number} non trovata. Passaggio al capitolo successivo.")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        images = soup.find_all('img', class_='mangaread-manga-pic')

        if not images:
            print(
                f"Nessuna immagine trovata nella pagina {page_num} del capitolo {chapter_number}. Passaggio al capitolo successivo.")
            break

        for index, img in enumerate(images):
            img_url = img.get('src')
            if img_url and img_url.startswith('http'):
                img_filename = f'{chapter_number}_{page_num}_{index}.jpg'
                img_path = os.path.join(chapter_folder, img_filename)

                if not os.path.exists(img_path):
                    attempts = 3
                    while attempts > 0:
                        img_data = requests.get(img_url).content
                        if len(img_data) > 1024:  # Verifica se il file è maggiore di 1KB
                            with open(img_path, 'wb') as handler:
                                handler.write(img_data)
                            print(
                                f'Scaricata immagine {index + 1} della pagina {page_num} del capitolo {chapter_number}')
                            break
                        else:
                            attempts -= 1
                            print(f'Immagine {img_filename} troppo piccola, riprovando... ({3 - attempts}/3)')

                    if attempts == 0:
                        logging.error(f"Impossibile scaricare {img_url} dopo 3 tentativi")
                        print(f"Impossibile scaricare {img_url} dopo 3 tentativi")
                        log_signal.emit(f"Impossibile scaricare {img_url} dopo 3 tentativi")
                else:
                    print(f'Immagine {img_filename} già presente. Skipping.')
            else:
                print(f'URL non valido trovato: {img_url}')

        page_num += 1


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scarica Immagini da Novelcool")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # URL
        url_layout = QHBoxLayout()
        url_label = QLabel("URL della Home:")
        url_layout.addWidget(url_label)
        self.url_entry = QLineEdit()
        url_layout.addWidget(self.url_entry)
        layout.addLayout(url_layout)

        # Capitolo di inizio
        start_chapter_layout = QHBoxLayout()
        start_chapter_label = QLabel("Capitolo di Inizio:")
        start_chapter_layout.addWidget(start_chapter_label)
        self.start_chapter_entry = QLineEdit()
        start_chapter_layout.addWidget(self.start_chapter_entry)
        layout.addLayout(start_chapter_layout)

        # Capitolo di fine
        end_chapter_layout = QHBoxLayout()
        end_chapter_label = QLabel("Capitolo di Fine (opzionale):")
        end_chapter_layout.addWidget(end_chapter_label)
        self.end_chapter_entry = QLineEdit()
        end_chapter_layout.addWidget(self.end_chapter_entry)
        layout.addLayout(end_chapter_layout)

        # Pulsante di download
        self.download_button = QPushButton("Avvia Download")
        self.download_button.clicked.connect(self.start_download)
        layout.addWidget(self.download_button)

        # Progress bar e log
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def start_download(self):
        start_chapter = int(self.start_chapter_entry.text())
        end_chapter = int(self.end_chapter_entry.text()) if self.end_chapter_entry.text() else None
        index_url = self.url_entry.text()

        self.download_thread = DownloadThread(start_chapter, end_chapter, index_url)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.log.connect(self.log_text.append)
        self.download_thread.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
